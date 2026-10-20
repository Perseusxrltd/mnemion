import json
import os
from pathlib import Path

import pytest
import tomlkit

from mnemion import agent_setup


@pytest.mark.parametrize("profile", ["codex", "grok-build"])
def test_codex_setup_preserves_policies_comments_and_other_servers(tmp_path, profile):
    target = tmp_path / "config.toml"
    original = """# Keep local access and policy settings.
approval_policy = "never"
approvals_reviewer = "user"
sandbox_mode = "danger-full-access"

[mcp_servers.existing]
command = "existing-server"
# Keep this comment too.

[projects."/mnt/c"]
trust_level = "untrusted"
"""
    target.write_text(original, encoding="utf-8")
    credentials = tmp_path / "répertoire avec espaces" / "app.json"
    planned = agent_setup.plan(profile, target, credentials, python=r"C:\Apps\Python\python.exe")
    assert target.read_text() == original
    result = agent_setup.apply(planned)
    assert Path(result["backup"]).read_text() == original
    updated = target.read_text(encoding="utf-8")
    assert "# Keep this comment too." in updated
    settings = tomlkit.parse(updated)
    for key in ("approval_policy", "approvals_reviewer", "sandbox_mode", "projects"):
        assert settings[key] == tomlkit.parse(original)[key]
    assert settings["mcp_servers"]["existing"]["command"] == "existing-server"
    assert settings["mcp_servers"]["mnemion"]["args"][3] == str(credentials.absolute())
    assert settings["mcp_servers"]["mnemion"]["command"] == r"C:\Apps\Python\python.exe"
    if os.name != "nt":
        assert Path(result["backup"]).stat().st_mode & 0o777 == 0o600
        assert target.stat().st_mode & 0o777 == 0o600
    agent_setup.apply(agent_setup.plan(profile, target, credentials, remove=True))
    assert tomlkit.parse(target.read_text()) == tomlkit.parse(original)


def test_json_clients_preserve_unrelated_configuration_and_remove_only_mnemion(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(
        json.dumps({"other": {"enabled": True}, "mcpServers": {"mempalace": {"command": "palace"}}})
    )
    planned = agent_setup.plan("cursor", target, tmp_path / "not-read.json")
    agent_setup.apply(planned)
    data = json.loads(target.read_text())
    assert data["other"] == {"enabled": True}
    assert data["mcpServers"]["mempalace"] == {"command": "palace"}
    agent_setup.apply(agent_setup.plan("cursor", target, tmp_path / "not-read.json", remove=True))
    assert json.loads(target.read_text())["mcpServers"] == {"mempalace": {"command": "palace"}}
    zed = agent_setup.plan("zed", tmp_path / "zed.json", tmp_path / "app.json")
    assert isinstance(json.loads(zed.content)["context_servers"]["mnemion"]["command"], str)


@pytest.mark.parametrize(
    "client,original",
    [
        ("codex", b"broken = ["),
        ("cursor", b"{// comment\n}"),
        ("cursor", b"[]"),
        ("codex", b'mcp_servers = "wrong"'),
    ],
)
def test_invalid_existing_config_is_never_overwritten(tmp_path, client, original):
    target = tmp_path / "settings"
    target.write_bytes(original)
    with pytest.raises(ValueError):
        agent_setup.plan(client, target, tmp_path / "credentials.json")
    assert target.read_bytes() == original
    assert not list(tmp_path.glob("*.mnemion-backup-*"))


def test_changed_settings_reject_stale_preview_and_missing_remove_is_noop(tmp_path):
    target = tmp_path / "settings.json"
    credentials = tmp_path / "app.json"
    assert not agent_setup.apply(agent_setup.plan("cursor", target, credentials, remove=True))[
        "changed"
    ]
    assert not target.exists()
    planned = agent_setup.plan("cursor", target, credentials)
    target.write_text('{"edited": true}')
    with pytest.raises(ValueError, match="changed after preview"):
        agent_setup.apply(planned)
    assert json.loads(target.read_text()) == {"edited": True}


def test_setup_respects_current_platform_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-wsl"))
    assert agent_setup.default_path("codex") == tmp_path / "codex-wsl/config.toml"
    assert agent_setup.default_path("grok-build") == Path.home() / ".grok/config.toml"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "custom-config"))
    monkeypatch.setattr(agent_setup.sys, "platform", "linux")
    assert agent_setup.default_path("zed") == tmp_path / "custom-config/zed/settings.json"
    monkeypatch.setattr(agent_setup.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    assert agent_setup.default_path("zed") == tmp_path / "roaming/Zed/settings.json"
    assert (
        agent_setup.default_path("claude-desktop")
        == tmp_path / "roaming/Claude/claude_desktop_config.json"
    )


def test_named_standalone_setup_does_not_replace_a_different_workspace(tmp_path):
    target = tmp_path / "config.toml"
    target.write_text('[mcp_servers.mnemion]\ncommand = "existing-workspace"\n')
    plan = agent_setup.plan(
        "grok-build",
        target,
        tmp_path / "private.json",
        python="included-engine",
        standalone=True,
        server_name="mnemion-office",
    )
    assert not plan.replacing
    agent_setup.apply(plan)
    nodes = tomlkit.parse(target.read_text())["mcp_servers"]
    assert nodes["mnemion"]["command"] == "existing-workspace"
    assert nodes["mnemion-office"]["args"] == [
        "--credentials",
        str(tmp_path / "private.json"),
        "mcp",
    ]
    for name in ("../escape", "", "with space", "x" * 65):
        with pytest.raises(ValueError):
            agent_setup.plan("grok-build", target, tmp_path / "private.json", server_name=name)
    assert "mnemion-office" in tomlkit.parse(target.read_text())["mcp_servers"]


def test_failed_replacement_retains_exact_config_and_private_backup(tmp_path, monkeypatch):
    target = tmp_path / "settings.json"
    original = b'{"other":{"private":"retained"}}\n'
    target.write_bytes(original)
    planned = agent_setup.plan("cursor", target, tmp_path / "credentials.json")

    def interrupted(*args):
        raise OSError("Interrupted replacement")

    monkeypatch.setattr(agent_setup.os, "replace", interrupted)
    with pytest.raises(OSError, match="Interrupted"):
        agent_setup.apply(planned)
    assert target.read_bytes() == original
    backups = list(tmp_path.glob("settings.json.mnemion-backup-*"))
    assert len(backups) == 1 and backups[0].read_bytes() == original
    assert not list(tmp_path.glob(".mnemion-agent-*"))


def test_existing_staging_path_is_never_deleted_or_overwritten(tmp_path, monkeypatch):
    from uuid import UUID

    identifier = UUID("a06bc3ac-770f-46cc-9c40-b8f0576e9a8c")
    unrelated = tmp_path / (".mnemion-agent-" + identifier.hex)
    unrelated.write_bytes(b"Existing unrelated file")
    monkeypatch.setattr(agent_setup, "uuid4", lambda: identifier)
    target = tmp_path / "settings.json"
    planned = agent_setup.plan("cursor", target, tmp_path / "credentials.json")
    with pytest.raises(FileExistsError):
        agent_setup.apply(planned)
    assert unrelated.read_bytes() == b"Existing unrelated file"
    assert not target.exists()
