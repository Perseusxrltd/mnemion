import json

from mnemion.config import MnemionConfig
from mnemion.embedding import resolve_embedding_device


def test_embedding_device_config_and_env(monkeypatch, tmp_path):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "config.json").write_text(json.dumps({"embedding_device": "dml"}))

    assert MnemionConfig(config_dir=cfg_dir).embedding_device == "dml"

    monkeypatch.setenv("MNEMION_EMBEDDING_DEVICE", "cuda")
    assert MnemionConfig(config_dir=cfg_dir).embedding_device == "cuda"


def test_embedding_device_falls_back_when_provider_unavailable(monkeypatch):
    monkeypatch.setattr("mnemion.embedding._available_providers", lambda: ["CPUExecutionProvider"])

    resolved = resolve_embedding_device("dml")

    assert resolved.device == "cpu"
    assert resolved.providers == ["CPUExecutionProvider"]
    assert "fallback" in resolved.reason.lower()
