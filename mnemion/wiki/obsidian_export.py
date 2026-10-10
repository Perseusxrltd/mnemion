"""Managed Obsidian export for compiled wiki pages."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..vault_refresh import VaultRefreshError, refresh
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

    manifest = {
        "generated_by": "mnemion-wiki-export",
        "files": sorted(files),
        "file_count": len(files),
        "scope": {"type": "compiled-wiki", "include_sensitive": include_sensitive},
    }
    try:
        result = refresh(target_root, files, manifest, MANIFEST_NAME)
    except VaultRefreshError as exc:
        raise WikiObsidianExportError(str(exc)) from exc
    return {
        **result,
        "status": "exported" if result["completed"] else "conflicts",
        "target_path": str(target_root),
        "file_count": len(files),
        "manifest_path": str(manifest_path),
        "skipped_sensitive": skipped_sensitive,
        "skipped_quarantined": skipped_quarantined,
        "warnings": warnings,
    }
