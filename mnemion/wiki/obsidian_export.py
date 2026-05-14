"""Managed Obsidian export for compiled wiki pages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..sources.store import atomic_write_text
from .provenance import resolve_page_provenance
from .renderer import parse_frontmatter

MANIFEST_NAME = ".mnemion-compiled-wiki-manifest.json"
DEFAULT_SUBDIR = Path("_Mnemion") / "Compiled Wiki"


class WikiObsidianExportError(RuntimeError):
    pass


def export_compiled_wiki_to_obsidian(
    wiki_path: str | Path,
    vault_path: str | Path,
    include_sensitive: bool = False,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    wiki_root = Path(wiki_path).expanduser()
    vault = Path(vault_path).expanduser()
    target_root = vault / DEFAULT_SUBDIR
    manifest_path = target_root / MANIFEST_NAME
    previous = {}
    if manifest_path.exists():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise WikiObsidianExportError("compiled wiki manifest is malformed") from exc

    files: dict[str, str] = {}
    skipped_sensitive = 0
    skipped_quarantined = 0
    warnings: list[str] = []
    for source in sorted(wiki_root.rglob("*.md")):
        text = source.read_text(encoding="utf-8", errors="replace")
        rel = str(source.relative_to(wiki_root)).replace("\\", "/")
        fm = parse_frontmatter(text)
        privacy_class = fm.get("privacy_class", "")
        trust_status = fm.get("trust_status", "current")
        provenance = resolve_page_provenance(text, rel, db_path=db_path) if db_path else None
        live_quarantined = bool(provenance and provenance.quarantined_source_ids)
        live_sensitive = bool(provenance and provenance.sensitive_source_ids)
        if trust_status == "quarantined" or live_quarantined:
            skipped_quarantined += 1
            warnings.append(f"skipped quarantined page: {rel}")
            continue
        if not include_sensitive and (privacy_class == "sensitive" or live_sensitive):
            skipped_sensitive += 1
            warnings.append(f"skipped sensitive page: {rel}")
            continue
        if provenance and provenance.contested_source_ids:
            warnings.append(f"export includes contested source evidence: {rel}")
        files[rel] = text

    target_root.mkdir(parents=True, exist_ok=True)
    previous_files = set(previous.get("files") or [])
    current_files = set(files)
    pruned = 0
    for rel in sorted(previous_files - current_files):
        target = target_root / rel
        try:
            resolved = target.resolve()
            if target_root.resolve() in resolved.parents and target.is_file():
                target.unlink()
                pruned += 1
        except OSError:
            continue

    for rel, text in files.items():
        atomic_write_text(target_root / rel, text)
    manifest = {
        "generated_by": "mnemion-wiki-export",
        "files": sorted(files),
        "file_count": len(files),
    }
    atomic_write_text(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {
        "status": "exported",
        "target_path": str(target_root),
        "file_count": len(files),
        "pruned_files": pruned,
        "manifest_path": str(manifest_path),
        "skipped_sensitive": skipped_sensitive,
        "skipped_quarantined": skipped_quarantined,
        "warnings": warnings,
    }
