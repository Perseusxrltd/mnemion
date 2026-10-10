"""Inspect managed-note preservation using synthetic Obsidian vaults.

Uses the repository's small synthetic exporter fixtures. Does not open Obsidian,
register a vault, read personal notes, or change desktop configuration.
"""

import argparse
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    sys.path.insert(0, str(repo))

    with tempfile.TemporaryDirectory(prefix="mnemion-obsidian-study-") as temp:
        root = Path(temp)
        os.environ.update(
            MNEMION_HOME=str(root / "profile"),
            MNEMION_ANAKTORON_PATH=str(root / "anaktoron"),
            MNEMION_OBSIDIAN_VAULT_PATH=str(root / "vault"),
        )
        fixture = runpy.run_path(str(repo / "tests/test_obsidian.py"))
        from mnemion.obsidian import sync_obsidian_vault
        from mnemion.wiki.obsidian_export import export_compiled_wiki_to_obsidian

        collection = fixture["_collection"]()
        database = fixture["_kg_db"](root)
        vault = root / "vault"
        sync_obsidian_vault(vault, collection, database)
        managed = vault / "Mnemion.md"
        managed.write_text(managed.read_text() + "\nHuman annotation STUDY_ANNOTATION\n")
        unmanaged = vault / "Personal.md"
        unmanaged.write_text("Personal note STUDY_PERSONAL\n")
        sync_obsidian_vault(vault, collection, database)

        wiki = root / "wiki"
        wiki.mkdir()
        (wiki / "source.md").write_text("---\ntitle: Synthetic source\n---\n# Source\n")
        export_compiled_wiki_to_obsidian(wiki, vault)
        exported = vault / "_Mnemion/Compiled Wiki/source.md"
        exported.write_text(exported.read_text() + "\nLocal annotation STUDY_WIKI_ANNOTATION\n")
        export_compiled_wiki_to_obsidian(wiki, vault)

        result = {
            "method": "synthetic export and refresh; no native Obsidian application launched",
            "unmanaged_note_preserved": "STUDY_PERSONAL" in unmanaged.read_text(),
            "manual_edit_in_managed_mirror_note_preserved": "STUDY_ANNOTATION"
            in managed.read_text(),
            "manual_edit_in_exported_wiki_note_preserved": "STUDY_WIKI_ANNOTATION"
            in exported.read_text(),
            "interpretation": "Owned exports are replaced on refresh; preservation in the wiki compiler does not preserve edits made in its exported copy.",
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
