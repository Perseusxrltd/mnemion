"""Portable, recoverable Markdown refresh with explicit generated ownership.

Only hashes establish ownership. A manifest filename alone does not authorize
overwriting an edited note. Unknown legacy content is kept with a proposed
replacement; outside-section annotations are preserved byte-for-byte.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from uuid import uuid4

import yaml

from .portable_paths import path_key, portable_part

BEGIN = "<!-- MNEMION_GENERATED_BEGIN_v1 -->"
END = "<!-- MNEMION_GENERATED_END_v1 -->"
MANUAL = "\n\n## Personal annotations\n\n"
FRONTMATTER = re.compile(r"\A---\r?\n.*?\r?\n---(?:\r?\n|$)", re.DOTALL)


class VaultRefreshError(RuntimeError):
    pass


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_target(root: Path, relative: str) -> Path:
    rel = PurePosixPath(relative)
    if (
        not relative
        or "\\" in relative
        or rel.is_absolute()
        or PureWindowsPath(relative).drive
        or any(
            not portable_part(part) or path_key(part) == ".obsidian" for part in relative.split("/")
        )
        or relative.endswith("/")
        or any(":" in part or "\0" in part for part in rel.parts)
    ):
        raise VaultRefreshError(f"Unsafe managed path: {relative}")
    target = root.joinpath(*rel.parts)
    resolved_root = root.resolve()
    if resolved_root not in target.resolve().parents:
        raise VaultRefreshError(f"Managed path escapes the vault: {relative}")
    for path in (target, *target.parents):
        if path == root.parent:
            break
        if path.is_symlink():
            raise VaultRefreshError(f"Managed path contains a symbolic link: {relative}")
    return target


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".mnemion-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def read_manifest(root: Path, name: str) -> dict[str, Any]:
    path = safe_target(root, name)
    if not path.exists():
        return {}
    try:
        result = json.loads(_read(path))
        if not isinstance(result, dict) or not isinstance(result.get("files", []), list):
            raise ValueError()
        for rel in result.get("files", []):
            if not isinstance(rel, str):
                raise ValueError()
            safe_target(root, rel)
        if not isinstance(result.get("entries", {}), dict):
            raise ValueError()
        return result
    except (ValueError, TypeError, UnicodeError) as exc:
        raise VaultRefreshError(f"Invalid export manifest: {name}") from exc


def _frontmatter(text: str) -> tuple[str, str]:
    match = FRONTMATTER.match(text)
    return (match.group(), text[match.end() :]) if match else ("", text)


def note_identity(text: str) -> str | None:
    prefix, _ = _frontmatter(text)
    if not prefix:
        return None
    try:
        values = yaml.safe_load(prefix.split("---", 2)[1])
    except yaml.YAMLError as exc:
        raise VaultRefreshError("A generated note contains invalid YAML") from exc
    if not isinstance(values, dict):
        return None
    kind = values.get("mnemion_type")
    if kind == "revision":
        value = values.get("revision_id")
    elif kind == "source":
        value = values.get("source_revision_id")
    elif kind == "space":
        value = values.get("space_id")
    else:
        value = values.get("memory_id") or values.get("id") or values.get("mnemion_page_id")
    return str(value) if value else None


def note_aliases(text: str) -> list[str]:
    prefix, _ = _frontmatter(text)
    if not prefix:
        return []
    values = yaml.safe_load(prefix.split("---", 2)[1])
    if not isinstance(values, dict):
        return []
    if values.get("mnemion_type") in ("revision", "source", "space"):
        identity = note_identity(text)
        return [identity] if identity else []
    aliases = [
        str(values[key]) for key in ("memory_id", "id", "mnemion_page_id") if values.get(key)
    ]
    legacy = values.get("legacy_ids", [])
    if isinstance(legacy, list):
        aliases.extend(item for item in legacy if isinstance(item, str))
    return list(dict.fromkeys(aliases))


def wrap_generated(text: str) -> str:
    # Captured Markdown may itself contain our literal delimiter. It remains
    # readable data; it cannot close the enclosing generated section.
    text = text.replace(BEGIN, BEGIN.replace("<", "&lt;")).replace(END, END.replace("<", "&lt;"))
    prefix, body = _frontmatter(text)
    return prefix + BEGIN + "\n" + body + ("" if body.endswith("\n") else "\n") + END + MANUAL


def sections(text: str) -> tuple[str, str, str, str] | None:
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        return None
    prefix, rest = _frontmatter(text)
    before, generated = rest.split(BEGIN, 1)
    if END not in generated:
        return None
    body, after = generated.split(END, 1)
    return prefix, before, BEGIN + body + END, after


def entry(text: str, source: str | None = None) -> dict:
    parts = sections(text)
    return {
        "file_sha256": digest(text),
        "generated_sha256": digest(parts[0] + parts[2]) if parts else None,
        "source_sha256": digest(source) if source is not None else None,
    }


def bundle(files: dict[str, str], metadata: dict) -> tuple[dict[str, str], dict]:
    """New ZIP exports use the same markers and hashes as local refresh."""
    wrapped = {rel: wrap_generated(content) for rel, content in files.items()}
    manifest = {
        **metadata,
        "format_version": 2,
        "files": sorted(files),
        "entries": {rel: entry(wrapped[rel], source) for rel, source in files.items()},
        "id_paths": {
            identity: rel for rel, text in files.items() if (identity := note_identity(text))
        },
        "conflicts": [],
        "completed": True,
    }
    return wrapped, manifest


def stable_paths(root: Path, files: dict[str, str], previous: dict) -> dict[str, str]:
    old_paths = dict(previous.get("id_paths", {}))
    # Legacy manifests lack a path map; discover IDs only in their listed files.
    for rel in previous.get("files", []):
        target = safe_target(root, rel)
        if target.is_file() and rel not in old_paths.values():
            identity = note_identity(_read(target))
            if identity:
                old_paths.setdefault(identity, rel)
    replacements = {}
    for rel, text in files.items():
        for identity in note_aliases(text):
            if identity in old_paths:
                safe_target(root, old_paths[identity])
                replacements[rel] = old_paths[identity]
                break
    result = {}
    folded = set()
    for rel, text in files.items():
        destination = replacements.get(rel, rel)
        safe_target(root, destination)
        folded_key = path_key(destination)
        if folded_key in folded:
            raise VaultRefreshError(f"Case-insensitive note path collision: {destination}")
        folded.add(folded_key)
        for source, target in replacements.items():
            if source != target:
                # Preserve path-qualified wikilinks, aliases, and block anchors.
                text = re.sub(
                    r"\[\[" + re.escape(source.removesuffix(".md")) + r"(?=[|#\]])",
                    lambda _: "[[" + target.removesuffix(".md"),
                    text,
                )
        result[destination] = text
    return result


@contextmanager
def _lock(root: Path):
    lock_path = safe_target(root, ".mnemion-refresh.lock")
    handle = lock_path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            if not handle.read(1):
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    except (BlockingIOError, PermissionError) as exc:
        raise VaultRefreshError("Another refresh is active, or the vault is not writable") from exc
    finally:
        handle.close()


def refresh(
    root: Path, files: dict[str, str], metadata: dict, manifest_name: str, *, dry_run: bool = False
) -> dict:
    if dry_run:
        return _refresh(root, files, metadata, manifest_name, dry_run=True)
    root.mkdir(parents=True, exist_ok=True)
    with _lock(root):
        return _refresh(root, files, metadata, manifest_name, dry_run=False)


def _refresh(
    root: Path, files: dict[str, str], metadata: dict, manifest_name: str, *, dry_run: bool
) -> dict:
    previous = read_manifest(root, manifest_name)
    pending_name = manifest_name + ".pending"
    pending = read_manifest(root, pending_name)
    if previous.get("scope") and metadata.get("scope") != previous["scope"]:
        raise VaultRefreshError(
            "Export scope changed; use a separate vault or explicitly migrate its scope"
        )
    ownership = {
        **previous,
        "files": sorted(set(previous.get("files", [])) | set(pending.get("files", []))),
        "id_paths": {**previous.get("id_paths", {}), **pending.get("id_paths", {})},
    }
    files = stable_paths(root, files, ownership)
    wrapped, manifest = bundle(files, metadata)
    writes, removals, expected_hashes, conflicts = {}, [], {}, []
    entries = {}
    for rel, proposed in wrapped.items():
        target = safe_target(root, rel)
        if target.exists() and not target.is_file():
            raise VaultRefreshError(f"Managed note is not a file: {rel}")
        current = _read(target) if target.exists() else None
        expected_hashes[rel] = digest(current) if current is not None else None
        old = previous.get("entries", {}).get(rel, {})
        interrupted = pending.get("entries", {}).get(rel, {})
        parts = sections(current) if current is not None else None
        allowed = {
            old.get("generated_sha256"),
            old.get("pending_generated_sha256"),
            interrupted.get("generated_sha256"),
        }
        owned = parts and digest(parts[0] + parts[2]) in (allowed - {None})
        if current is None:
            writes[rel] = proposed
        elif owned:
            new_parts = sections(proposed)
            writes[rel] = new_parts[0] + parts[1] + new_parts[2] + parts[3]
        elif current == files[rel] or (
            old.get("source_sha256") and digest(current) == old["source_sha256"]
        ):
            # An unchanged full-file v1 export can safely acquire v2 markers.
            writes[rel] = proposed
        elif current == proposed:
            writes[rel] = current
        else:
            code = "generated_section_edited" if parts else "legacy_or_unmanaged_note"
            conflicts.append({"path": rel, "reason": code, "action": "review_proposed_replacement"})
            entries[rel] = {**old, "pending_generated_sha256": entry(proposed)["generated_sha256"]}
            conflict_path = ".mnemion-conflicts/" + digest(rel)[:16] + ".proposed.md"
            writes[conflict_path] = proposed
            expected_hashes[conflict_path] = None
            continue
        entries[rel] = entry(writes[rel], files[rel])
    retained = []
    detached = {}
    for rel in sorted(set(ownership["files"]) - set(files)):
        target = safe_target(root, rel)
        if not target.exists():
            continue
        current = _read(target)
        current_hash = digest(current)
        expected_hashes[rel] = current_hash
        if current_hash == pending.get("detached_annotations", {}).get(rel):
            detached[rel] = current_hash
            continue
        parts = sections(current)
        old = previous.get("entries", {}).get(rel, {})
        interrupted = pending.get("entries", {}).get(rel, {})
        allowed = {old.get("generated_sha256"), interrupted.get("generated_sha256")} - {None}
        if parts and digest(parts[0] + parts[2]) in allowed:
            manual = parts[1] + parts[3]
            if manual.strip() == MANUAL.strip():
                removals.append(rel)
            else:
                # Withdraw generated evidence while retaining personal text and
                # its path. This note becomes unmanaged; future refreshes cannot
                # overwrite or prune it merely because it was once exported.
                writes[rel] = manual
                detached[rel] = digest(manual)
        elif old.get("file_sha256") == current_hash:
            removals.append(rel)
        else:
            conflicts.append(
                {
                    "path": rel,
                    "reason": "withdrawal_needs_review",
                    "action": "retain_original_until_resolved",
                }
            )
            retained.append(rel)
            entries[rel] = old
    manifest["files"] = sorted(set(files) | set(retained))
    manifest["entries"] = entries
    manifest["detached_annotations"] = detached
    manifest["conflicts"] = conflicts
    manifest["completed"] = not conflicts
    if conflicts:
        manifest["pending_synced_at"] = manifest.get("synced_at")
        manifest["synced_at"] = previous.get("synced_at")
    result = {
        "status": "conflicts" if conflicts else "synced",
        "file_count": len(files),
        "pruned_files": len(removals),
        "detached_annotations": sorted(detached),
        "conflicts": conflicts,
        "completed": not conflicts,
    }
    if dry_run:
        return {
            **result,
            "status": "dry_run",
            "would_write_files": len(writes) + 1,
            "would_prune_files": len(removals),
        }
    # Persist intended hashes before any target change. A subsequent refresh
    # recognizes writes from an interrupted run, then applies freshly authorized
    # content instead of blindly replaying an old export snapshot.
    atomic_text(
        safe_target(root, pending_name), json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    stage = safe_target(root, ".mnemion-staging/" + uuid4().hex)
    stage.mkdir(parents=True)
    try:
        for index, (rel, content) in enumerate(writes.items()):
            target = safe_target(root, rel)
            staged = stage / str(index)
            atomic_text(staged, content)
            target.parent.mkdir(parents=True, exist_ok=True)
            if rel in expected_hashes and not rel.startswith(".mnemion-conflicts/"):
                actual = digest(_read(target)) if target.exists() else None
                if actual != expected_hashes[rel]:
                    raise VaultRefreshError(
                        f"Note changed during refresh: {rel}; retry to reconcile"
                    )
            os.replace(staged, target)
        for rel in removals:
            target = safe_target(root, rel)
            if digest(_read(target)) != expected_hashes[rel]:
                raise VaultRefreshError(f"Note changed during refresh: {rel}; retry to reconcile")
            target.unlink()
        atomic_text(
            safe_target(root, manifest_name), json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        safe_target(root, pending_name).unlink()
    finally:
        for path in stage.iterdir():
            path.unlink()
        stage.rmdir()
    return result
