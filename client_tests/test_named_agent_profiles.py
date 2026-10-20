"""Native client formats must not change another connection or agent policy."""

import json

import json5
import pytest
from ruamel.yaml import YAML

from mnemion import agent_setup


def test_openclaw_nested_json5_retains_policy_connections_and_exact_backup(tmp_path):
    target = tmp_path / "openclaw.json"
    original = b"""{
      // Existing operator policy and connection must survive.
      gateway: {bind: 'loopback'},
      mcp: {servers: {existing: {url: 'https://example.com/mcp', auth: 'oauth'},}},
    }\n"""
    target.write_bytes(original)
    credentials = tmp_path / "private" / "workspace.json"
    planned = agent_setup.plan("openclaw", target, credentials, server_name="mnemion-team")
    assert target.read_bytes() == original
    installed = agent_setup.apply(planned)
    assert installed["changed"]
    from pathlib import Path

    assert Path(installed["backup"]).read_bytes() == original
    actual = json5.loads(target.read_text())
    assert actual["gateway"] == {"bind": "loopback"}
    assert actual["mcp"]["servers"]["existing"] == {
        "url": "https://example.com/mcp",
        "auth": "oauth",
    }
    assert "mcp.servers" not in actual
    assert str(credentials) in actual["mcp"]["servers"]["mnemion-team"]["args"]
    assert not agent_setup.apply(
        agent_setup.plan("openclaw", target, credentials, server_name="mnemion-team")
    )["changed"]
    agent_setup.apply(
        agent_setup.plan("openclaw", target, credentials, server_name="mnemion-team", remove=True)
    )
    assert json5.loads(target.read_text()) == json5.loads(original.decode())


def test_hermes_retains_comments_quotes_and_other_servers(tmp_path):
    target = tmp_path / "config.yaml"
    original = b"""# Keep this deployment note.
model:
  default: "local-model" # Selected by the operator.
mcp_servers:
  existing:
    command: "existing-tool"
    tools:
      include: [read]
"""
    target.write_bytes(original)
    credentials = tmp_path / "private.json"
    planned = agent_setup.plan("hermes", target, credentials, server_name="mnemion-team")
    agent_setup.apply(planned)
    text = target.read_text()
    assert "# Keep this deployment note." in text and "# Selected by the operator." in text
    assert '"local-model"' in text
    document = YAML(typ="safe").load(text)
    assert document["mcp_servers"]["existing"]["tools"] == {"include": ["read"]}
    assert str(credentials) in document["mcp_servers"]["mnemion-team"]["args"]
    agent_setup.apply(
        agent_setup.plan("hermes", target, credentials, server_name="mnemion-team", remove=True)
    )
    assert YAML(typ="safe").load(target.read_text()) == YAML(typ="safe").load(original)


def test_hermes_edit_does_not_mutate_settings_that_share_yaml_alias(tmp_path):
    target = tmp_path / "config.yaml"
    target.write_text(
        "shared: &existing\n  old: {command: old}\nmcp_servers: *existing\nother: *existing\n"
    )
    agent_setup.apply(agent_setup.plan("hermes", target, tmp_path / "private.json"))
    actual = YAML(typ="safe").load(target.read_text())
    assert actual["shared"] == actual["other"] == {"old": {"command": "old"}}
    assert set(actual["mcp_servers"]) == {"old", "mnemion"}


@pytest.mark.parametrize(
    "client,original",
    [
        ("hermes", "mcp_servers: {}\nmcp_servers: {hidden: {command: hidden}}\n"),
        ("openclaw", '{mcp: {servers: {}}, mcp: {servers: {hidden: {command: "hidden"}}}}'),
        ("cursor", '{"mcpServers":{},"mcpServers":{"hidden":{"command":"hidden"}}}'),
        ("openclaw", "{mcp: {servers: []}}"),
        ("hermes", "mcp_servers: [unexpected]"),
    ],
)
def test_ambiguous_or_invalid_client_settings_are_preserved(tmp_path, client, original):
    target = tmp_path / "settings"
    target.write_text(original)
    with pytest.raises(ValueError):
        agent_setup.plan(client, target, tmp_path / "private.json")
    assert target.read_text() == original
    assert not list(tmp_path.glob("*.mnemion-backup-*"))


def test_named_profiles_honor_explicit_environment_locations(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-team"))
    monkeypatch.setenv("OPENCLAW_STATE_DIR", str(tmp_path / "claw-team"))
    monkeypatch.delenv("OPENCLAW_CONFIG_PATH", raising=False)
    assert agent_setup.default_path("hermes") == tmp_path / "hermes-team/config.yaml"
    assert agent_setup.default_path("openclaw") == tmp_path / "claw-team/openclaw.json"
    monkeypatch.setenv("OPENCLAW_CONFIG_PATH", str(tmp_path / "custom.json5"))
    assert agent_setup.default_path("openclaw") == tmp_path / "custom.json5"


def test_identical_json5_entry_keeps_its_original_format(tmp_path):
    target = tmp_path / "openclaw.json"
    credentials = tmp_path / "private.json"
    node = json.dumps(agent_setup.server_config(credentials))
    original = "{// Keep formatting\n mcp: {servers: {mnemion: " + node + ",}},}\n"
    target.write_text(original)
    assert not agent_setup.apply(agent_setup.plan("openclaw", target, credentials))["changed"]
    assert target.read_text() == original


def test_openclaw_named_profile_does_not_target_the_default_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path / "operator"))
    monkeypatch.setenv("OPENCLAW_PROFILE", "Company-A")
    monkeypatch.delenv("OPENCLAW_CONFIG_PATH", raising=False)
    monkeypatch.delenv("OPENCLAW_STATE_DIR", raising=False)
    assert (
        agent_setup.default_path("openclaw")
        == tmp_path / "operator/.openclaw-Company-A/openclaw.json"
    )
    monkeypatch.setenv("OPENCLAW_STATE_DIR", "~/separate-state")
    assert (
        agent_setup.default_path("openclaw") == tmp_path / "operator/separate-state/openclaw.json"
    )
    monkeypatch.delenv("OPENCLAW_STATE_DIR")
    monkeypatch.setenv("OPENCLAW_PROFILE", "../other")
    with pytest.raises(ValueError, match="explicit configuration"):
        agent_setup.default_path("openclaw")
