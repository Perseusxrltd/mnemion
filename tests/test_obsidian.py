import json
import hashlib
import sqlite3
import zipfile
from pathlib import Path

import pytest
import yaml

from mnemion.obsidian import (
    MANIFEST_NAME,
    ObsidianSafetyError,
    export_obsidian_zip,
    register_obsidian_vault,
    render_drawer_note,
    sync_obsidian_vault,
    vault_status,
)


class FakeCollection:
    def __init__(self, rows):
        self.rows = list(rows)

    def count(self):
        return len(self.rows)

    def get(self, **kwargs):
        ids = kwargs.get("ids")
        where = kwargs.get("where")
        if ids is not None:
            selected = [row for row in self.rows if row["id"] in ids]
        else:
            selected = self.rows
            if where:
                selected = [
                    row
                    for row in selected
                    if all(
                        (row.get("metadata") or {}).get(key) == value
                        for key, value in where.items()
                    )
                ]
            offset = kwargs.get("offset", 0) or 0
            limit = kwargs.get("limit")
            selected = selected[offset : None if limit is None else offset + limit]
        return {
            "ids": [row["id"] for row in selected],
            "documents": [row.get("document", "") for row in selected],
            "metadatas": [row.get("metadata", {}) for row in selected],
        }


def _collection():
    return FakeCollection(
        [
            {
                "id": "drawer:one/unsafe",
                "document": "Alice prefers local-first tools because cloud sync is risky.",
                "metadata": {
                    "wing": "Projects/AI",
                    "room": "Memory:Core",
                    "source_file": "notes.md",
                    "trust_status": "current",
                    "confidence": 0.95,
                    "created_at": "2026-05-01T10:00:00",
                    "entities": "Alice, Mnemion",
                },
            },
            {
                "id": "drawer_two",
                "document": "A quarantined note should still be browsable in the mirror.",
                "metadata": {
                    "wing": "security",
                    "room": "review",
                    "trust_status": "quarantined",
                },
            },
        ]
    )


def _kg_db(tmp_path: Path) -> Path:
    db = tmp_path / "knowledge_graph.sqlite3"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE entities (name TEXT PRIMARY KEY, type TEXT, aliases TEXT, created_at TEXT, updated_at TEXT);
        INSERT INTO entities VALUES ('Alice', 'person', '[]', 'now', 'now');
        INSERT INTO entities VALUES ('Mnemion', 'project', '[]', 'now', 'now');
        CREATE TABLE triples (
            subject TEXT, predicate TEXT, object TEXT, confidence REAL,
            source_drawer TEXT, valid_from TEXT, valid_to TEXT, created_at TEXT
        );
        INSERT INTO triples VALUES ('Alice', 'uses', 'Mnemion', 0.9, 'drawer:one/unsafe', NULL, NULL, 'now');
        CREATE TABLE cognitive_units (
            unit_id TEXT, drawer_id TEXT, unit_type TEXT, text TEXT, cues TEXT,
            source_file TEXT, timestamp TEXT, trust_status TEXT, created_at TEXT
        );
        INSERT INTO cognitive_units VALUES ('unit1', 'drawer:one/unsafe', 'preference', 'Alice prefers local-first tools.', 'alice local-first', 'notes.md', '2026-05-01', 'current', 'now');
        CREATE TABLE cognitive_edges (
            edge_id TEXT, drawer_id TEXT, edge_type TEXT, source_text TEXT, target_text TEXT, created_at TEXT
        );
        INSERT INTO cognitive_edges VALUES ('edge1', 'drawer:one/unsafe', 'cause', 'cloud sync', 'risky', 'now');
        CREATE TABLE memory_guard_findings (
            id INTEGER PRIMARY KEY, drawer_id TEXT, risk_type TEXT, score REAL, reason TEXT, created_at TEXT
        );
        INSERT INTO memory_guard_findings VALUES (1, 'drawer_two', 'privacy_exfiltration', 0.85, 'matched pattern: token', 'now');
        CREATE TABLE drawer_trust (
            drawer_id TEXT PRIMARY KEY, status TEXT, confidence REAL, valid_from TEXT, valid_to TEXT,
            created_at TEXT, updated_at TEXT, superseded_by TEXT, verifications INTEGER,
            challenges INTEGER, wing TEXT, room TEXT
        );
        INSERT INTO drawer_trust VALUES ('drawer:one/unsafe', 'current', 0.95, NULL, NULL, 'now', 'now', NULL, 0, 0, 'Projects/AI', 'Memory:Core');
        INSERT INTO drawer_trust VALUES ('drawer_two', 'quarantined', 0.0, NULL, NULL, 'now', 'now', NULL, 0, 1, 'security', 'review');
        """
    )
    conn.commit()
    conn.close()
    return db


def test_render_drawer_note_uses_flat_yaml_frontmatter_and_links():
    note = render_drawer_note(
        drawer_id="drawer:one/unsafe",
        document="Alice prefers local-first tools.",
        metadata={
            "wing": "Projects/AI",
            "room": "Memory:Core",
            "trust_status": "current",
            "confidence": 0.95,
            "entities": "Alice, Mnemion",
        },
        entities=["Alice", "Mnemion"],
        cognitive_units=[{"unit_type": "preference", "text": "Alice prefers local-first tools."}],
    )

    assert note.startswith("---\n")
    frontmatter = yaml.safe_load(note.split("---", 2)[1])
    assert frontmatter["id"] == "drawer:one/unsafe"
    assert frontmatter["wing"] == "Projects/AI"
    assert frontmatter["room"] == "Memory:Core"
    assert frontmatter["trust_status"] == "current"
    assert all(not isinstance(value, dict) for value in frontmatter.values())
    assert "[[Wings/Projects_AI/index|Projects/AI]]" in note
    assert "[[Wings/Projects_AI/Memory_Core/index|Memory:Core]]" in note
    assert "[[Trust/current|current]]" in note
    assert "[[Entities/Alice|Alice]]" in note
    assert "## Cognitive Evidence" in note


def test_sync_refuses_non_empty_non_managed_vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "human.md").write_text("not managed\n", encoding="utf-8")

    with pytest.raises(ObsidianSafetyError):
        sync_obsidian_vault(
            vault_path=vault,
            collection=_collection(),
            kg_db_path=tmp_path / "missing.sqlite3",
            force_existing=False,
        )

    assert (vault / "human.md").exists()


def test_sync_refuses_non_empty_vault_with_malformed_manifest(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / MANIFEST_NAME).write_text("{bad json", encoding="utf-8")
    (vault / "human.md").write_text("not managed\n", encoding="utf-8")

    with pytest.raises(ObsidianSafetyError):
        sync_obsidian_vault(
            vault_path=vault,
            collection=_collection(),
            kg_db_path=tmp_path / "missing.sqlite3",
            force_existing=False,
        )

    assert (vault / "human.md").exists()


def test_sync_refuses_vault_nested_inside_existing_obsidian_vault(tmp_path):
    parent_vault = tmp_path / "existing-vault"
    (parent_vault / ".obsidian").mkdir(parents=True)
    nested = parent_vault / "mnemion"

    with pytest.raises(ObsidianSafetyError):
        sync_obsidian_vault(
            vault_path=nested,
            collection=_collection(),
            kg_db_path=tmp_path / "missing.sqlite3",
        )


def test_sync_prunes_only_unchanged_manifest_files(tmp_path):
    vault = tmp_path / "vault"
    old_generated = vault / "Wings" / "old.md"
    old_generated.parent.mkdir(parents=True)
    old_generated.write_text("old\n", encoding="utf-8")
    keep = vault / "keep.md"
    keep.write_text("keep\n", encoding="utf-8")
    (vault / MANIFEST_NAME).write_text(
        json.dumps(
            {
                "files": ["Wings/old.md"],
                "entries": {"Wings/old.md": {"file_sha256": hashlib.sha256(b"old\n").hexdigest()}},
            }
        ),
        encoding="utf-8",
    )

    result = sync_obsidian_vault(
        vault_path=vault,
        collection=_collection(),
        kg_db_path=_kg_db(tmp_path),
    )

    assert result["drawer_count"] == 2
    assert not old_generated.exists()
    assert keep.exists()
    assert (vault / "Mnemion.md").exists()
    assert (vault / "Trust" / "current.md").exists()
    assert (vault / "Entities" / "Alice.md").exists()
    manifest = json.loads((vault / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert "keep.md" not in manifest["files"]


def test_export_obsidian_zip_reuses_managed_renderer(tmp_path):
    zip_path = tmp_path / "vault.zip"

    result = export_obsidian_zip(
        zip_path=zip_path,
        collection=_collection(),
        kg_db_path=_kg_db(tmp_path),
        wing="Projects/AI",
    )

    assert result["drawer_count"] == 1
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert "Mnemion.md" in names
        assert "Wings/Projects_AI/index.md" in names
        assert any(name.endswith(".md") and "drawer_one_unsafe" in name for name in names)


def test_register_obsidian_vault_backs_up_valid_config(tmp_path):
    config_dir = tmp_path / "Obsidian"
    config_dir.mkdir()
    obsidian_json = config_dir / "obsidian.json"
    obsidian_json.write_text(
        json.dumps({"vaults": {"existing": {"path": "C:/existing", "ts": 1}}}),
        encoding="utf-8",
    )

    result = register_obsidian_vault(tmp_path / "vault", obsidian_config_dir=config_dir)

    assert result["registered"] is True
    assert result["backup_path"]
    assert Path(result["backup_path"]).exists()
    data = json.loads(obsidian_json.read_text(encoding="utf-8"))
    assert "mnemion-owned-mirror" in data["vaults"]
    assert data["vaults"]["mnemion-owned-mirror"]["path"] == str(tmp_path / "vault")
    assert "existing" in data["vaults"]


def test_register_obsidian_vault_preserves_malformed_config(tmp_path):
    config_dir = tmp_path / "Obsidian"
    config_dir.mkdir()
    obsidian_json = config_dir / "obsidian.json"
    obsidian_json.write_text("{not json", encoding="utf-8")

    result = register_obsidian_vault(tmp_path / "vault", obsidian_config_dir=config_dir)

    assert result["registered"] is False
    assert "malformed" in result["error"].lower()
    assert obsidian_json.read_text(encoding="utf-8") == "{not json"


def test_vault_status_reports_counts_and_registration(tmp_path):
    vault = tmp_path / "vault"
    sync_obsidian_vault(vault, _collection(), _kg_db(tmp_path))

    status = vault_status(vault, obsidian_config_dir=tmp_path / "missing")

    assert status["exists"] is True
    assert status["file_count"] > 0
    assert status["drawer_count"] == 2
    assert status["registered"] is False
