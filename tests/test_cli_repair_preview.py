"""A rebuild preview may inspect the collection but must not replace stored data."""

from argparse import Namespace
import sys
from types import SimpleNamespace

from mnemion import cli


def test_rebuild_dry_run_does_not_back_up_delete_or_rewrite(tmp_path, monkeypatch, capsys):
    palace = tmp_path / "private-memory"
    palace.mkdir()
    original = palace / "unchanged.sqlite3"
    original.write_bytes(b"private fixture bytes")
    calls = []

    class Collection:
        def count(self):
            calls.append("count")
            return 1

        def get(self, **_kwargs):
            calls.append("read")
            return {"ids": ["private-id"], "documents": ["private text"], "metadatas": [{}]}

    class Client:
        def get_collection(self, _name):
            return Collection()

        def delete_collection(self, _name):
            raise AssertionError("A dry-run rebuild attempted to delete the collection")

    monkeypatch.setattr(cli, "MnemionConfig", lambda: SimpleNamespace(collection_name="fixture"))
    monkeypatch.setitem(
        sys.modules,
        "mnemion.chroma_client",
        SimpleNamespace(persistent_client=lambda _path: Client()),
    )
    cli.cmd_repair(Namespace(palace=str(palace), mode="rebuild", dry_run=True))
    assert calls == ["count"]
    assert not palace.with_suffix(".backup").exists()
    assert original.read_bytes() == b"private fixture bytes"
    assert "dry run" in capsys.readouterr().out.lower()
