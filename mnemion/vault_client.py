"""Validate a service export before safely applying it to a local vault."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from .portable_paths import path_key
from .vault_refresh import BEGIN, END, VaultRefreshError, digest, refresh, safe_target, sections

MANIFEST = ".mnemion-obsidian-manifest.json"


def read_bundle(data: bytes, root: Path) -> tuple[dict[str, str], dict]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            if len(set(names)) != len(names) or MANIFEST not in names:
                raise VaultRefreshError("Duplicate files or missing export manifest")
            infos = archive.infolist()
            if len(infos) > 100_000 or sum(info.file_size for info in infos) > 250_000_000:
                raise VaultRefreshError("Export archive exceeds the local refresh limit")
            manifest = json.loads(archive.read(MANIFEST).decode("utf-8"))
            if not isinstance(manifest, dict):
                raise VaultRefreshError("The export manifest must be an object")
            if manifest.get("format_version") != 2 or manifest.get("completed") is not True:
                raise VaultRefreshError("The export is incomplete or uses an unsupported format")
            paths, entries = manifest.get("files"), manifest.get("entries")
            if (
                not isinstance(paths, list)
                or not all(isinstance(path, str) for path in paths)
                or not isinstance(entries, dict)
                or len({path_key(path) for path in paths}) != len(paths)
            ):
                raise VaultRefreshError("Invalid or ambiguous export file list")
            if set(names) != {*manifest["files"], MANIFEST}:
                raise VaultRefreshError("Archive file list differs from its manifest")
            files = {}
            for rel in manifest["files"]:
                safe_target(root, rel)
                if not rel.lower().endswith(".md") or any(
                    part.startswith(".") for part in rel.split("/")
                ):
                    raise VaultRefreshError("Exports may only contain visible Markdown notes")
                if not isinstance(entries.get(rel), dict):
                    raise VaultRefreshError("Missing note checksum entry")
                text = archive.read(rel).decode("utf-8")
                if digest(text) != manifest["entries"][rel]["file_sha256"]:
                    raise VaultRefreshError(f"Export checksum mismatch: {rel}")
                parts = sections(text)
                if parts is None:
                    raise VaultRefreshError(f"Missing generated-section markers: {rel}")
                body = parts[2][len(BEGIN) : -len(END)]
                if body.startswith("\n"):
                    body = body[1:]
                files[rel] = parts[0] + body
            return files, manifest
    except (zipfile.BadZipFile, KeyError, TypeError, ValueError, UnicodeError) as exc:
        raise VaultRefreshError("Invalid or truncated Obsidian export") from exc


def sync_bundle(data: bytes, root: str | Path, *, dry_run: bool = False) -> dict:
    root = Path(root).expanduser()
    files, manifest = read_bundle(data, root)
    metadata = {
        key: value
        for key, value in manifest.items()
        if key not in ("files", "entries", "id_paths", "format_version", "completed", "conflicts")
    }
    return {"vault_path": str(root), **refresh(root, files, metadata, MANIFEST, dry_run=dry_run)}
