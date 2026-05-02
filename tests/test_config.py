import os
import json
import tempfile
from mnemion.config import MnemionConfig


def test_default_config():
    cfg = MnemionConfig(config_dir=tempfile.mkdtemp())
    assert "anaktoron" in cfg.anaktoron_path
    assert cfg.collection_name == "mnemion_drawers"


def test_config_from_file():
    tmpdir = tempfile.mkdtemp()
    with open(os.path.join(tmpdir, "config.json"), "w") as f:
        json.dump({"anaktoron_path": "/custom/anaktoron"}, f)
    cfg = MnemionConfig(config_dir=tmpdir)
    assert cfg.anaktoron_path == "/custom/anaktoron"


def test_legacy_config_key():
    """Backward compat: config.json using old 'palace_path' key still works."""
    tmpdir = tempfile.mkdtemp()
    with open(os.path.join(tmpdir, "config.json"), "w") as f:
        json.dump({"palace_path": "/legacy/anaktoron"}, f)
    cfg = MnemionConfig(config_dir=tmpdir)
    assert cfg.anaktoron_path == "/legacy/anaktoron"


def test_env_override():
    os.environ["MNEMION_ANAKTORON_PATH"] = "/env/anaktoron"
    cfg = MnemionConfig(config_dir=tempfile.mkdtemp())
    assert cfg.anaktoron_path == "/env/anaktoron"
    del os.environ["MNEMION_ANAKTORON_PATH"]


def test_topic_tunnel_min_count_env_override():
    tmpdir = tempfile.mkdtemp()
    with open(os.path.join(tmpdir, "config.json"), "w") as f:
        json.dump({"topic_tunnel_min_count": 5}, f)
    os.environ["MNEMION_TOPIC_TUNNEL_MIN_COUNT"] = "3"
    try:
        cfg = MnemionConfig(config_dir=tmpdir)
        assert cfg.topic_tunnel_min_count == 3
    finally:
        del os.environ["MNEMION_TOPIC_TUNNEL_MIN_COUNT"]


def test_legacy_env_override():
    """Backward compat: old MNEMION_PALACE_PATH env var still works."""
    os.environ["MNEMION_PALACE_PATH"] = "/env/anaktoron"
    cfg = MnemionConfig(config_dir=tempfile.mkdtemp())
    assert cfg.anaktoron_path == "/env/anaktoron"
    del os.environ["MNEMION_PALACE_PATH"]


def test_init():
    tmpdir = tempfile.mkdtemp()
    cfg = MnemionConfig(config_dir=tmpdir)
    cfg.init()
    assert os.path.exists(os.path.join(tmpdir, "config.json"))
