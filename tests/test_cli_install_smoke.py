import pytest

from mnemion import cli


def test_cli_version_flag(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["mnemion", "--version"])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 0
    assert "mnemion 3.5.5" in capsys.readouterr().out


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
