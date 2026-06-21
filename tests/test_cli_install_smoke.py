import pytest

from mnemion import cli


class FakeCollection:
    def get(self, **kwargs):
        return {
            "ids": ["drawer_one"],
            "documents": ["Obsidian mirror dry run content."],
            "metadatas": [{"wing": "project", "room": "notes"}],
        }


def test_cli_version_flag(capsys, monkeypatch):
    from mnemion.version import __version__

    monkeypatch.setattr("sys.argv", ["mnemion", "--version"])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 0
    assert f"mnemion {__version__}" in capsys.readouterr().out


def test_public_chroma_dependency_stays_on_known_good_line():
    pyproject = (cli.Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    assert '"chromadb>=0.6.3,<0.7"' in pyproject
    assert '"opentelemetry-exporter-otlp-proto-grpc>=1.40.0,<2.0"' in pyproject
    assert '"protobuf>=6.31.1,<7.0"' in pyproject


def test_configure_stdio_reconfigures_streams(monkeypatch):
    calls = []

    class FakeStream:
        def reconfigure(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(cli.sys, "stdout", FakeStream())
    monkeypatch.setattr(cli.sys, "stderr", FakeStream())

    cli._configure_stdio()

    assert calls == [
        {"encoding": "utf-8", "errors": "replace"},
        {"encoding": "utf-8", "errors": "replace"},
    ]


def test_cli_obsidian_status_uses_configured_vault(capsys, monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    monkeypatch.setenv("MNEMION_OBSIDIAN_VAULT_PATH", str(vault))
    monkeypatch.setattr("sys.argv", ["mnemion", "obsidian", "status"])

    cli.main()

    out = capsys.readouterr().out
    assert "Obsidian Mirror" in out
    assert str(vault) in out


def test_cli_obsidian_sync_dry_run_does_not_write(capsys, monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    monkeypatch.setattr(
        cli,
        "_obsidian_collection_and_db",
        lambda _args: (FakeCollection(), tmp_path / "missing.sqlite3"),
        raising=False,
    )
    monkeypatch.setattr(
        "sys.argv",
        ["mnemion", "obsidian", "sync", "--vault", str(vault), "--dry-run"],
    )

    cli.main()

    out = capsys.readouterr().out.lower()
    assert "dry_run" in out
    assert "would_write_files" in out
    assert not vault.exists()
