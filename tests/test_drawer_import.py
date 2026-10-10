import json
import sqlite3

import pytest

from mnemion.drawer_import import iter_drawers, restore_drawers
from mnemion.ingestion import LegacyMemoryWriter
from mnemion.trust_lifecycle import DrawerTrust


@pytest.mark.parametrize(
    "body",
    [
        "",
        "[",
        '[{"id":"a","content":"first"}',
        '[{"id":"a","content":"first"},',
        '[{"id":"a","content":"first"},]',
        '[{"id":"a","content":"first"}{"id":"b","content":"second"}]',
        '[{"id":"a","content":"first"}] trailing',
        '[{"id":"a","content":"first"},{"id":"a","content":"second"}]',
        '[{"id":"a","content":"first","meta":{"x":NaN}}]',
        '[{"id":"a","content":"first","meta":[]}]',
        'prefix [{"id":"a","content":"first"}]',
    ],
)
def test_invalid_json_never_opens_or_mutates_the_live_backend(tmp_path, body):
    source = tmp_path / "legacy.json"
    source.write_text(body)
    opened = []

    def backend(**kwargs):
        opened.append(kwargs)
        raise AssertionError("Backend opened before complete validation")

    with pytest.raises(ValueError):
        restore_drawers(
            source, tmp_path / "live/anaktoron", "mnemion_drawers", backend_factory=backend
        )
    assert opened == [] and not (tmp_path / "live").exists()


def test_streamed_json_enforces_boundaries_and_unicode(tmp_path):
    source = tmp_path / "valid.json"
    rows = [
        {
            "id": "one",
            "content": 'Mémoire: café, "citations" and a closing bracket ]',
            "meta": {"wing": "équipe"},
        },
        {"id": "two", "content": "Other decision"},
    ]
    source.write_text(json.dumps(rows, ensure_ascii=False))
    assert list(iter_drawers(source, read_size=3)) == [
        {**r, "meta": r.get("meta", {})} for r in rows
    ]


def test_import_without_metadata_has_explicit_uncategorized_scope(collection, tmp_path):
    source = tmp_path / "legacy.json"
    source.write_text('[{"id":"no-meta","content":"Original text"}]')

    class Backend:
        def get_collection(self, *a, **k):
            return collection

    result = restore_drawers(
        source, tmp_path / "anaktoron", "drawers", backend_factory=lambda **k: Backend()
    )
    assert result["state"] == "ready"
    record = collection.get(ids=["no-meta"], include=["metadatas"])
    assert record["metadatas"][0]["wing"] == "unknown"


def test_import_preserves_existing_trust_denials_and_recovers_interruption(
    collection, tmp_path, monkeypatch
):
    database = tmp_path / "knowledge_graph.sqlite3"
    writer = LegacyMemoryWriter(collection, database)
    writer.save("existing", "Old content", {"wing": "work", "room": "notes"})
    writer.save("deleted", "Removed content", {"wing": "work", "room": "notes"})
    writer.delete("deleted")
    DrawerTrust(str(database)).update_status("existing", "contested", reason="Keep this review")
    source = tmp_path / "legacy.json"
    source.write_text(
        json.dumps(
            [
                {"id": "existing", "content": "Updated content", "meta": {"wing": "work"}},
                {"id": "deleted", "content": "Must not return", "meta": {"wing": "work"}},
                {
                    "id": "new",
                    "content": "Imported evidence without lifecycle",
                    "meta": {"wing": "work"},
                },
            ]
        )
    )

    class Backend:
        def get_collection(self, *a, **k):
            return collection

    def factory(**kwargs):
        return Backend()

    original = LegacyMemoryWriter._write_indexes
    with monkeypatch.context() as patch:
        patch.setattr(
            LegacyMemoryWriter,
            "_write_indexes",
            lambda *a: (_ for _ in ()).throw(OSError("disk failure")),
        )
        with pytest.raises(OSError):
            restore_drawers(
                source, tmp_path / "anaktoron", "drawers", merge=True, backend_factory=factory
            )
    with sqlite3.connect(database) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM drawer_ingest_jobs WHERE state='pending'"
            ).fetchone()[0]
            == 2
        )
    assert LegacyMemoryWriter._write_indexes is original
    writer.recover()
    assert collection.get(ids=["deleted"])["ids"] == []
    assert collection.get(ids=["existing"])["documents"] == ["Updated content"]
    trust = DrawerTrust(str(database))
    assert trust.get("existing")["status"] == "contested"
    assert trust.get("new")["status"] == "quarantined"
    result = restore_drawers(
        source, tmp_path / "anaktoron", "drawers", merge=True, backend_factory=factory
    )
    assert result["skipped_deleted"] == 1 and result["state"] == "ready"
