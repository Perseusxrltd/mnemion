"""Complete v3 profile snapshots, strict recovery, and portable import evidence.

All legacy writers and Obsidian must be stopped for a snapshot. SQLite's backup
API captures WAL state; before/after hashes also reject files that changed during
the snapshot. Updated writer entry points honor the persistent pause marker.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from .archives import (
    _member,
    canonical_json,
    file_hash,
    private_json,
    verified_archive,
    write_archive,
)
from .legacy_freeze import MARKER, freeze_profile
from .version import __version__

FORMAT = "mnemion-legacy-profile"
LEDGER_FORMAT = "mnemion-legacy-deletions"
EXCLUDED_DIRECTORIES = {".git", ".venv", "node_modules", "__pycache__"}
LIFECYCLE_TABLES = (
    "drawer_trust",
    "drawer_trust_history",
    "drawer_conflicts",
    "drawer_deletions",
    "drawer_ingest_jobs",
    "core_memories",
    "raw_sources",
    "source_chunks",
    "wiki_pages",
    "wiki_claims",
    "wiki_links",
    "wiki_jobs",
    "triples",
    "entities",
    "cognitive_units",
    "cognitive_edges",
    "cognitive_consolidated_drawers",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(path: Path):
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _config(profile: Path) -> dict:
    path = profile / "config.json"
    value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(value, dict):
        raise ValueError("Legacy configuration must be a JSON object")
    return value


def _profile_id(profile: Path) -> str:
    return str(_config(profile).get("profile_id") or uuid5(NAMESPACE_URL, profile.as_uri()))


def layout(profile: Path, *, vault: Path | None = None) -> dict[str, Path]:
    profile = profile.expanduser().resolve()
    if not profile.is_dir():
        raise ValueError("Legacy profile does not exist")
    config = _config(profile)
    result = {"profile": profile}
    for name, setting, default in (
        ("anaktoron", "anaktoron_path", "anaktoron"),
        ("sources", "source_path", "sources"),
        ("wiki", "wiki_path", "wiki"),
        ("vault", "obsidian_vault_path", "obsidian-vault"),
    ):
        configured = config.get(setting) or (
            config.get("palace_path") if name == "anaktoron" else None
        )
        path = (
            vault
            if name == "vault" and vault
            else Path(configured).expanduser()
            if configured
            else profile / default
        )
        if not path.is_absolute():
            path = profile / path
        result[name] = path.resolve()
    result["sidecar"] = result["anaktoron"].parent / "knowledge_graph.sqlite3"
    return result


def _roots(locations: dict[str, Path]) -> tuple[dict[str, Path], dict[str, str]]:
    roots = {"profile": locations["profile"]}
    prefixes = {"profile": "profile"}
    for name, path in locations.items():
        if name == "profile":
            continue
        prefix = next(
            (
                str(Path(key) / path.relative_to(parent)).replace(os.sep, "/")
                for key, parent in roots.items()
                if path.is_relative_to(parent)
            ),
            None,
        )
        if prefix is None:
            prefix = "external/" + name
            roots[prefix] = path
        prefixes[name] = prefix
    return roots, prefixes


def _inputs(roots: dict[str, Path]) -> dict[str, Path]:
    result = {}
    for prefix, root in roots.items():
        if not root.exists():
            continue
        if root.is_file():
            result[prefix] = root
            continue
        for directory, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRECTORIES)
            for name in [*dirs, *sorted(names)]:
                path = Path(directory) / name
                if path.is_symlink():
                    raise ValueError(
                        "Replace profile symlinks with explicit configured paths before backing up"
                    )
                if (
                    not path.is_file()
                    or name.endswith("-shm")
                    or (name.endswith("-wal") and path.stat().st_size == 0)
                ):
                    continue
                result[prefix + "/" + path.relative_to(root).as_posix()] = path
    return result


def _fingerprint(inputs: dict[str, Path]) -> dict:
    return {
        name: {"size": path.stat().st_size, "sha256": file_hash(path)}
        for name, path in sorted(inputs.items())
    }


def _sqlite(path: Path) -> bool:
    with path.open("rb") as file:
        return file.read(16) == b"SQLite format 3\x00"


def _copy_snapshot(inputs: dict[str, Path], target: Path) -> None:
    for name, source in inputs.items():
        if name.endswith("-wal"):
            continue
        output = target / name
        output.parent.mkdir(parents=True, exist_ok=True)
        if _sqlite(source):
            with _connect(source) as conn, sqlite3.connect(output) as destination:
                conn.backup(destination)
                if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("SQLite integrity check failed")
        else:
            shutil.copyfile(source, output)


def _json_value(value):
    if isinstance(value, bytes):
        return {"encoding": "base64", "data": base64.b64encode(value).decode()}
    return value


def read_sidecar(path: Path) -> dict:
    if not path.exists():
        return {}
    with _connect(path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {
            name: [
                {key: _json_value(value) for key, value in dict(row).items()}
                for row in conn.execute(f'SELECT * FROM "{name}"')
            ]
            for name in LIFECYCLE_TABLES
            if name in tables
        }


def export_chroma_sqlite(path: Path, destination: Path) -> list[dict]:
    """Read canonical Chroma metadata without loading models or legacy pickle files."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        destination.write_bytes(b"")
        return []
    with _connect(path) as conn, destination.open("wb") as output:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"collections", "segments", "embeddings", "embedding_metadata"} <= tables:
            raise ValueError(
                "Unsupported legacy Chroma schema; use its matching release to export first"
            )
        columns = {r[1] for r in conn.execute("PRAGMA table_info(embedding_metadata)")}
        values = [
            name
            for name in ("string_value", "int_value", "float_value", "bool_value")
            if name in columns
        ]
        query = (
            """SELECT c.id AS collection_id,c.name AS collection_name,e.id AS row_id,
                 e.embedding_id,m.key,"""
            + ",".join("m." + v for v in values)
            + """
                 FROM collections c JOIN segments s ON s.collection=c.id AND s.scope='METADATA'
                 JOIN embeddings e ON e.segment_id=s.id LEFT JOIN embedding_metadata m ON m.id=e.id
                 ORDER BY c.id,e.embedding_id,m.key"""
        )
        collections = {
            str(r["id"]): {"id": str(r["id"]), "name": r["name"], "count": 0}
            for r in conn.execute("SELECT id,name FROM collections ORDER BY id")
        }
        current, identity = None, None

        def emit(record):
            output.write(canonical_json(record) + b"\n")
            collections[record["collection_id"]]["count"] += 1

        for row in conn.execute(query):
            key = (row["collection_id"], row["embedding_id"])
            if key != identity:
                if current is not None:
                    emit(current)
                current = {
                    "collection_id": key[0],
                    "collection_name": row["collection_name"],
                    "id": key[1],
                    "content": None,
                    "meta": {},
                }
                identity = key
            value = next(
                (
                    bool(row[n]) if n == "bool_value" else row[n]
                    for n in values
                    if row[n] is not None
                ),
                None,
            )
            if row["key"] == "chroma:document":
                current["content"] = value
            elif row["key"] and not row["key"].startswith("chroma:"):
                current["meta"][row["key"]] = value
        if current is not None:
            emit(current)
    return list(collections.values())


def _ledger(profile: Path, locations: dict[str, Path]) -> dict:
    rows = read_sidecar(locations["sidecar"]).get("drawer_deletions", [])
    payload = {
        "format": LEDGER_FORMAT,
        "version": 1,
        "profile_id": _profile_id(profile),
        "snapshot_at": _now(),
        "deletions": rows,
    }
    return {**payload, "sha256": hashlib.sha256(canonical_json(payload)).hexdigest()}


def export_legacy_ledger(profile: Path, output: Path) -> dict:
    profile = profile.expanduser().resolve()
    result = _ledger(profile, layout(profile))
    private_json(output, result)
    return {
        "ledger_file": str(output),
        "profile_id": result["profile_id"],
        "snapshot_at": result["snapshot_at"],
        "deletions": len(result["deletions"]),
    }


def read_legacy_ledger(path: Path) -> dict:
    if path.stat().st_size > 256 * 1024**2:
        raise ValueError("Legacy deletion ledger is too large")
    data = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("format") != LEDGER_FORMAT
        or data.get("version") != 1
    ):
        raise ValueError("Unsupported legacy deletion ledger")
    digest = data.pop("sha256", None)
    if hashlib.sha256(canonical_json(data)).hexdigest() != digest:
        raise ValueError("Legacy deletion ledger checksum mismatch")
    if (
        not isinstance(data["deletions"], list)
        or datetime.fromisoformat(data["snapshot_at"]).tzinfo is None
    ):
        raise ValueError("Invalid legacy deletion ledger")
    for row in data["deletions"]:
        if not all(
            isinstance(row.get(k), str) and row[k]
            for k in ("collection_id", "drawer_id", "requested_at")
        ):
            raise ValueError("Invalid legacy deletion identity")
    return {**data, "sha256": digest}


def create_legacy_backup(
    profile: Path, output: Path, *, writers_stopped: bool, vault: Path | None = None
) -> dict:
    if not writers_stopped:
        raise ValueError(
            "Stop MCP, Studio, hooks, miners, sweepers, capture, sync jobs, and Obsidian; then use --writers-stopped"
        )
    profile = profile.expanduser().resolve()
    locations = layout(profile, vault=vault)
    roots, prefixes = _roots(locations)
    if any(output.resolve().is_relative_to(root) for root in roots.values() if root.is_dir()):
        raise ValueError("Write the backup outside every captured profile/vault directory")
    if output.exists():
        raise FileExistsError("Backup output already exists")
    before = _fingerprint(_inputs(roots))
    snapshot_at = _now()
    with tempfile.TemporaryDirectory(prefix="mnemion-v3-snapshot-") as directory:
        root = Path(directory)
        _copy_snapshot(_inputs(roots), root)
        after = _fingerprint(_inputs(roots))
        if before != after:
            raise ValueError("Legacy files changed during backup; stop all writers and retry")
        logical = root / "logical"
        logical.mkdir()
        collections = export_chroma_sqlite(
            root / prefixes["anaktoron"] / "chroma.sqlite3", logical / "drawers.jsonl"
        )
        sidecar = read_sidecar(root / prefixes["sidecar"])
        (logical / "lifecycle.json").write_bytes(canonical_json(sidecar))
        (logical / "collections.json").write_bytes(canonical_json(collections))
        payload = {
            "format": LEDGER_FORMAT,
            "version": 1,
            "profile_id": _profile_id(profile),
            "snapshot_at": snapshot_at,
            "deletions": sidecar.get("drawer_deletions", []),
        }
        ledger = {**payload, "sha256": hashlib.sha256(canonical_json(payload)).hexdigest()}
        (logical / "deletions.json").write_bytes(canonical_json(ledger))
        manifest = write_archive(
            output,
            {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file()},
            {
                "format": FORMAT,
                "version": 1,
                "application_version": __version__,
                "profile_id": _profile_id(profile),
                "backup_id": str(uuid4()),
                "snapshot_at": snapshot_at,
                "layout": prefixes,
                "original_paths": {name: str(path) for name, path in locations.items()},
                "source_inventory": before,
                "collections": collections,
                "sidecar_counts": {name: len(rows) for name, rows in sidecar.items()},
                "excluded_directories": sorted(EXCLUDED_DIRECTORIES),
                "consistency": "writers-stopped; sqlite-backup-api; unchanged-source-hashes",
            },
        )
    return {
        "backup_file": str(output),
        "backup_id": manifest["backup_id"],
        "profile_id": manifest["profile_id"],
        "collections": collections,
        "sidecar_counts": manifest["sidecar_counts"],
        "files": len(manifest["files"]),
    }


def _relocate_string(value: str, original: dict[str, str], final: dict[str, str]) -> str:
    for name, old in sorted(original.items(), key=lambda pair: len(pair[1]), reverse=True):
        if value == old or value.startswith(old + "/") or value.startswith(old + "\\"):
            return final[name] + value[len(old) :].replace("\\", os.sep).replace("/", os.sep)
    return value


def relocate_profile(root: Path, final_root: Path, manifest: dict) -> dict[str, Path]:
    final, staging = {}, {}
    for name, prefix in manifest["layout"].items():
        relative = (
            Path(prefix).relative_to("profile")
            if prefix == "profile" or prefix.startswith("profile/")
            else Path("_external") / Path(prefix).relative_to("external")
        )
        final[name], staging[name] = final_root / relative, root / relative
    original = manifest["original_paths"]
    final_strings = {key: str(value) for key, value in final.items()}
    config = _config(root)
    for key, name in (
        ("anaktoron_path", "anaktoron"),
        ("source_path", "sources"),
        ("wiki_path", "wiki"),
        ("obsidian_vault_path", "vault"),
    ):
        config[key] = str(final[name])
    config.pop("palace_path", None)
    config["profile_id"] = manifest["profile_id"]
    (root / "config.json").write_bytes(canonical_json(config))
    if staging["sidecar"].exists():
        with sqlite3.connect(staging["sidecar"]) as conn:
            tables = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            for table, columns in (
                ("raw_sources", ("file_path", "raw_text_path")),
                ("wiki_pages", ("path",)),
                ("wiki_jobs", ("diff_path",)),
            ):
                if table not in tables:
                    continue
                for column in columns:
                    for row_id, value in conn.execute(
                        f'SELECT rowid,"{column}" FROM "{table}" WHERE "{column}" IS NOT NULL'
                    ).fetchall():
                        conn.execute(
                            f'UPDATE "{table}" SET "{column}"=? WHERE rowid=?',
                            (_relocate_string(value, original, final_strings), row_id),
                        )
    return staging


def _reconcile_legacy_copy(profile: Path, locations: dict[str, Path], ledger: dict) -> None:
    # Chroma owns its binary indexes. Use its maintained delete operation in an
    # isolated process, which releases every handle before the directory rename.
    config = {
        "palace": str(locations["anaktoron"]),
        "sidecar": str(locations["sidecar"]),
        "deletions": ledger["deletions"],
        "collection_name": _config(profile).get("collection_name", "mnemion_drawers"),
    }
    with tempfile.TemporaryDirectory(prefix="mnemion-legacy-reconcile-") as directory:
        command = Path(directory) / "input.json"
        command.write_bytes(canonical_json(config))
        result = subprocess.run(
            [sys.executable, "-m", "mnemion.legacy_archive", "reconcile", str(command)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                "Legacy reconciliation failed; install this release with the legacy extra and inspect the isolated profile before retrying"
            )


def restore_legacy_backup(archive: Path, destination: Path, *, deletion_ledger: Path) -> dict:
    destination = destination.expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Restore only into a new legacy profile directory")
    ledger = read_legacy_ledger(deletion_ledger)
    with verified_archive(archive, FORMAT) as (manifest, extracted):
        expected = {"profile", "anaktoron", "sources", "wiki", "vault", "sidecar"}
        if (
            set(manifest.get("layout", {})) != expected
            or set(manifest.get("original_paths", {})) != expected
        ):
            raise ValueError("Incomplete legacy profile layout")
        for name, prefix in manifest["layout"].items():
            _member(prefix)
            if not (
                prefix == "profile"
                or prefix.startswith("profile/")
                or prefix.startswith("external/")
            ):
                raise ValueError("Invalid legacy archive layout")
            if not isinstance(manifest["original_paths"][name], str):
                raise ValueError("Invalid legacy path mapping")
        if ledger["profile_id"] != manifest["profile_id"] or datetime.fromisoformat(
            ledger["snapshot_at"]
        ) < datetime.fromisoformat(manifest["snapshot_at"]):
            raise ValueError("Use a current deletion ledger for the same legacy profile")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".mnemion-legacy-restore-", dir=destination.parent
        ) as directory:
            staged = Path(directory) / "profile"
            if (extracted / "profile").exists():
                shutil.copytree(extracted / "profile", staged)
            else:
                staged.mkdir()
            if (extracted / "external").exists():
                shutil.copytree(extracted / "external", staged / "_external")
            # Restore stays paused until explicitly resumed. Temporarily remove
            # a copied marker only inside this unpublished maintenance directory.
            (staged / MARKER).unlink(missing_ok=True)
            locations = relocate_profile(staged, destination, manifest)
            _reconcile_legacy_copy(staged, locations, ledger)
            paused = freeze_profile(staged)
            if destination.exists():
                raise FileExistsError("Restore destination appeared while preparing the copy")
            staged.rename(destination)
    return {
        "profile": str(destination),
        "backup_id": manifest["backup_id"],
        "profile_id": manifest["profile_id"],
        "paused": True,
        "freeze_id": paused["freeze_id"],
        "deletions_reconciled": len(ledger["deletions"]),
    }


def _reconcile_command(path: Path) -> None:
    from .chroma_client import persistent_client
    from .ingestion import SCHEMA, LegacyMemoryWriter

    args = json.loads(path.read_text(encoding="utf-8"))
    # Persist negative identities even when their collection or positive row
    # did not exist in the older snapshot (for example an unindexed raw source).
    Path(args["sidecar"]).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args["sidecar"]) as conn:
        conn.executescript(SCHEMA)
        for row in args["deletions"]:
            conn.execute(
                "INSERT OR IGNORE INTO drawer_deletions(collection_id,drawer_id,requested_at) VALUES(?,?,?)",
                (row["collection_id"], row["drawer_id"], row["requested_at"]),
            )
    if not (Path(args["palace"]) / "chroma.sqlite3").exists():
        return
    client = persistent_client(args["palace"])
    by_collection = {}
    for deletion in args["deletions"]:
        by_collection.setdefault(deletion["collection_id"], []).append(deletion["drawer_id"])
    for entry in client.list_collections():
        name = str(entry) if isinstance(entry, str) else entry.name
        collection = client.get_collection(name, embedding_function=None)
        deleted = by_collection.get(str(collection.id), []) + by_collection.get(collection.name, [])
        if collection.name == args["collection_name"]:
            writer = LegacyMemoryWriter(collection, args["sidecar"])
            for drawer in deleted:
                writer.delete(drawer)
            writer.reconcile()
        elif deleted:
            collection.delete(ids=deleted)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "reconcile":
        raise SystemExit("Internal legacy reconciliation command")
    _reconcile_command(Path(sys.argv[2]))
