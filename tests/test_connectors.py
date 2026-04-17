"""Tests for studio.backend.connectors — MCP client install/detect/uninstall."""

import json
import sys
from pathlib import Path

import pytest

# Ensure repo root is on sys.path so `studio.backend.connectors` imports
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from studio.backend import connectors as C  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _connector(tmp_path, *, fmt="json", mcp_key="mcpServers", suffix=".json"):
    return C.Connector(
        id="test",
        name="Test",
        vendor="Test",
        category="cli",
        description="",
        config_path=str(tmp_path / f"config{suffix}"),
        fmt=fmt,
        mcp_key=mcp_key,
    )


# ── JSON format ───────────────────────────────────────────────────────────────

def test_install_json_creates_config(tmp_path):
    c = _connector(tmp_path)
    assert C.install(c)["success"]
    data = json.loads(Path(c.config_path).read_text())
    assert "mnemion" in data["mcpServers"]
    assert data["mcpServers"]["mnemion"]["args"] == ["-m", "mnemion.mcp_server"]


def test_install_json_preserves_other_servers(tmp_path):
    c = _connector(tmp_path)
    Path(c.config_path).write_text(json.dumps({
        "mcpServers": {"other": {"command": "node", "args": ["x"]}}
    }))
    assert C.install(c)["success"]
    data = json.loads(Path(c.config_path).read_text())
    assert "mnemion" in data["mcpServers"]
    assert "other" in data["mcpServers"]
    assert data["mcpServers"]["other"]["args"] == ["x"]


def test_install_json_replaces_legacy_mempalace(tmp_path):
    c = _connector(tmp_path)
    Path(c.config_path).write_text(json.dumps({
        "mcpServers": {"mempalace": {"command": "py", "args": ["-m", "mempalace.mcp_server"]}}
    }))
    status_before = C.detect(c)
    assert status_before["legacy_detected"]
    assert not status_before["mnemion_configured"]

    C.install(c)

    status_after = C.detect(c)
    assert status_after["mnemion_configured"]
    assert not status_after["legacy_detected"]
    data = json.loads(Path(c.config_path).read_text())
    assert "mempalace" not in data["mcpServers"]


def test_install_json_backs_up_existing_file(tmp_path):
    c = _connector(tmp_path)
    Path(c.config_path).write_text('{"mcpServers": {"other": {"command": "x"}}}')
    result = C.install(c)
    assert result["backup_path"]
    assert Path(result["backup_path"]).exists()


def test_install_json_handles_empty_file(tmp_path):
    c = _connector(tmp_path)
    Path(c.config_path).write_text("")
    assert C.install(c)["success"]
    data = json.loads(Path(c.config_path).read_text())
    assert "mnemion" in data["mcpServers"]


def test_install_json_handles_malformed_json(tmp_path):
    """Malformed input is overwritten with a valid config (backup preserved)."""
    c = _connector(tmp_path)
    Path(c.config_path).write_text("{not valid json")
    result = C.install(c)
    assert result["success"]
    assert result["backup_path"] and Path(result["backup_path"]).exists()
    assert "{not valid json" in Path(result["backup_path"]).read_text()


def test_uninstall_json_removes_only_mnemion(tmp_path):
    c = _connector(tmp_path)
    Path(c.config_path).write_text(json.dumps({
        "mcpServers": {
            "mnemion": {"command": "py"},
            "other":   {"command": "node"},
        }
    }))
    assert C.uninstall(c)["success"]
    data = json.loads(Path(c.config_path).read_text())
    assert "mnemion" not in data["mcpServers"]
    assert "other" in data["mcpServers"]


def test_uninstall_drops_empty_mcp_key(tmp_path):
    c = _connector(tmp_path)
    Path(c.config_path).write_text(json.dumps({
        "mcpServers": {"mnemion": {"command": "py"}}
    }))
    C.uninstall(c)
    data = json.loads(Path(c.config_path).read_text())
    assert "mcpServers" not in data


def test_detect_reports_other_servers(tmp_path):
    c = _connector(tmp_path)
    Path(c.config_path).write_text(json.dumps({
        "mcpServers": {"other": {"command": "x"}, "another": {"command": "y"}}
    }))
    status = C.detect(c)
    assert not status["mnemion_configured"]
    assert sorted(status["other_mcp_servers"]) == ["another", "other"]


def test_detect_flags_non_dict_mcp_servers(tmp_path):
    """Defensive: if mcpServers is malformed (list instead of dict), install should fail gracefully."""
    c = _connector(tmp_path)
    Path(c.config_path).write_text(json.dumps({"mcpServers": ["bad"]}))
    # Detect doesn't crash
    status = C.detect(c)
    assert not status["mnemion_configured"]
    # Install refuses and restores backup
    result = C.install(c)
    assert not result["success"]
    # The original bad-shape file is restored
    assert json.loads(Path(c.config_path).read_text())["mcpServers"] == ["bad"]


# ── TOML format (Codex) ──────────────────────────────────────────────────────

def test_install_toml_adds_block(tmp_path):
    c = _connector(tmp_path, fmt="toml", mcp_key="mcp_servers", suffix=".toml")
    assert C.install(c)["success"]
    text = Path(c.config_path).read_text()
    assert "[mcp_servers.mnemion]" in text
    assert 'args = ["-m", "mnemion.mcp_server"]' in text


def test_install_toml_replaces_legacy_mempalace(tmp_path):
    c = _connector(tmp_path, fmt="toml", mcp_key="mcp_servers", suffix=".toml")
    Path(c.config_path).write_text(
        '[other]\nkey = "value"\n\n'
        '[mcp_servers.mempalace]\n'
        'command = "py"\n'
        'args = ["-m", "mempalace.mcp_server"]\n'
    )
    C.install(c)
    text = Path(c.config_path).read_text()
    assert "[mcp_servers.mempalace]" not in text
    assert "[mcp_servers.mnemion]" in text
    # Unrelated [other] section is preserved
    assert "[other]" in text
    assert 'key = "value"' in text


def test_install_toml_idempotent(tmp_path):
    c = _connector(tmp_path, fmt="toml", mcp_key="mcp_servers", suffix=".toml")
    C.install(c)
    text_1 = Path(c.config_path).read_text()
    C.install(c)
    text_2 = Path(c.config_path).read_text()
    # Second install should not duplicate the block
    assert text_1.count("[mcp_servers.mnemion]") == 1
    assert text_2.count("[mcp_servers.mnemion]") == 1


def test_uninstall_toml_removes_mnemion(tmp_path):
    c = _connector(tmp_path, fmt="toml", mcp_key="mcp_servers", suffix=".toml")
    Path(c.config_path).write_text(
        '[other]\nkey = "v"\n\n[mcp_servers.mnemion]\ncommand = "py"\nargs = []\n'
    )
    C.uninstall(c)
    text = Path(c.config_path).read_text()
    assert "[mcp_servers.mnemion]" not in text
    assert "[other]" in text


# ── Snippet ──────────────────────────────────────────────────────────────────

def test_snippet_json_is_valid_json():
    c = C.Connector(id="x", name="x", vendor="x", category="cli", description="",
                    config_path="x", fmt="json", mcp_key="mcpServers")
    data = json.loads(C.snippet(c))
    assert "mcpServers" in data
    assert "mnemion" in data["mcpServers"]


def test_snippet_toml_contains_block_header():
    c = C.Connector(id="x", name="x", vendor="x", category="cli", description="",
                    config_path="x", fmt="toml", mcp_key="mcp_servers")
    assert "[mcp_servers.mnemion]" in C.snippet(c)


# ── Unknown format ───────────────────────────────────────────────────────────

def test_install_unknown_format_fails_gracefully(tmp_path):
    c = _connector(tmp_path, fmt="yaml", mcp_key="servers")
    result = C.install(c)
    assert not result["success"]
    assert "Unsupported" in result["error"]


# ── Registry sanity ──────────────────────────────────────────────────────────

def test_registry_has_known_clients():
    ids = [c.id for c in C.CONNECTORS]
    for expected in ("claude-code", "cursor", "codex", "gemini-cli"):
        assert expected in ids, f"{expected} missing from registry"


def test_registry_get_returns_connector():
    assert C.get("cursor") is not None
    assert C.get("does-not-exist") is None


def test_python_cmd_is_absolute():
    assert Path(C.PYTHON_CMD).is_absolute(), f"Python cmd not absolute: {C.PYTHON_CMD}"
