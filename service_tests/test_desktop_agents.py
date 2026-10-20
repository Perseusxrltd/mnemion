"""Real application identity checks and native agent-configuration boundaries."""

import asyncio
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
from uuid import UUID, uuid4

from mcp import Client as MCPClient, StdioServerParameters
import pytest
import tomlkit

from mnemion import agent_setup, desktop_agents as agents
from mnemion.service.api import create_app
from mnemion.service.models import GrantInput, KeyInput, PrincipalInput
from service_tests.test_clients import running


def application(env):
    person = env.identities.create_principal(
        env.owner, PrincipalInput(name="Desktop agent fixture")
    )
    key = env.identities.create_key(env.owner, UUID(person["id"]), KeyInput(name="Desktop fixture"))
    return person, key


def definition(env, person, endpoint, target, client="codex"):
    return {
        "client": client,
        "server_name": "mnemion-team",
        "config_path": str(target),
        "endpoint": endpoint,
        "tenant_id": str(env.owner.tenant_id),
        "principal_id": person["id"],
    }


def install_request(preview, credential, **values):
    return {
        "operation": "install",
        "setup": preview["setup"],
        "configuration_hash": preview["configuration_hash"],
        "credential": credential,
        "confirm": True,
        "replace_existing": False,
        **values,
    }


@pytest.mark.parametrize("client", ["codex", "grok-build", "cursor", "hermes", "openclaw"])
def test_app_install_reopen_named_connections_and_removal_preserve_other_settings(
    env, tmp_path, client
):
    person, key = application(env)
    fmt = agent_setup.CLIENTS[client][0]
    suffix = {"toml": ".toml", "yaml": ".yaml", "json": ".json", "json5": ".json5"}[fmt]
    target = tmp_path / ("agent" + suffix)
    original = {
        "toml": b'# Preserve policy.\napproval_policy = "never"\nsandbox_mode = "danger-full-access"\n[mcp_servers.existing]\ncommand = "existing"\n',
        "json": b'{"policies":{"keep":true},"mcpServers":{"existing":{"command":"existing"}}}\n',
        "yaml": b"# Keep policy.\npolicies: {keep: true}\nmcp_servers:\n  existing: {command: existing}\n",
        "json5": b'{// Keep policy\n policies: {keep:true}, mcp: {servers: {existing: {command: "existing"},}},}\n',
    }[fmt]
    target.write_bytes(original)
    root, executable = tmp_path / "private", Path(sys.executable)
    with running(create_app(env.db, env.embedder)) as endpoint:
        preview = agents.perform(
            root,
            {"operation": "preview", "setup": definition(env, person, endpoint, target, client)},
            executable,
        )
        assert not root.exists() and target.read_bytes() == original
        assert not preview["replacing"] and key["api_key"] not in json.dumps(preview)
        for request in (
            install_request(preview, env.token),
            install_request(
                {**preview, "setup": {**preview["setup"], "tenant_id": str(uuid4())}},
                key["api_key"],
            ),
        ):
            with pytest.raises(agents.local_state.LocalSetupError, match="selected application"):
                agents.perform(root, request, executable)
        assert agents.records(root) == [] and target.read_bytes() == original
        installed = agents.perform(root, install_request(preview, key["api_key"]), executable)
        assert installed["installation"]["state"] == "installed"
        assert Path(installed["backup"]).read_bytes() == original
        record = agents.records(root)[0]
        key_file = agents.key_path(root, record.id)
        assert json.loads(key_file.read_text())["api_key"] == key["api_key"]
        if os.name != "nt":
            assert key_file.stat().st_mode & 0o077 == 0
            assert key_file.parent.stat().st_mode & 0o077 == 0
        view = agents.status(root)
        assert view["installations"][0]["state"] == "installed"
        assert key["api_key"] not in json.dumps(view) and key["api_key"] not in target.read_text()
        document = agent_setup.document(client, target.read_bytes())
        section = agent_setup.servers(client, document)
        assert section["existing"]["command"] == "existing"
        assert section["mnemion-team"]["args"] == ["--credentials", str(key_file), "mcp"]
        with pytest.raises(agents.local_state.LocalSetupError, match="changed"):
            agents.perform(
                root,
                {
                    "operation": "remove",
                    "id": str(record.id),
                    "configuration_hash": preview["configuration_hash"],
                    "confirm": True,
                },
                executable,
            )
        removed = agents.perform(
            root,
            {
                "operation": "remove",
                "id": str(record.id),
                "configuration_hash": view["installations"][0]["configuration_hash"],
                "confirm": True,
            },
            executable,
        )
        assert not removed["server_key_revoked"] and not key_file.exists()
        assert agents.status(root)["installations"] == []
        restored = agent_setup.document(client, target.read_bytes())
        assert restored == agent_setup.document(client, original)
        assert env.db.authenticate(key["api_key"]).principal_id == UUID(person["id"])


def test_stale_preview_and_unconfirmed_replacement_never_write_agent_credentials(env, tmp_path):
    person, key = application(env)
    target = tmp_path / "agent.json"
    target.write_text('{"mcpServers":{"mnemion-team":{"command":"previous"}}}')
    root, executable = tmp_path / "private", Path(sys.executable)
    with running(create_app(env.db, env.embedder)) as endpoint:
        preview = agents.preview(
            root, {"setup": definition(env, person, endpoint, target, "cursor")}, executable
        )
        assert preview["replacing"]
        with pytest.raises(ValueError, match="Confirm replacement"):
            agents.perform(root, install_request(preview, key["api_key"]), executable)
        target.write_text('{"edited":true,"mcpServers":{"mnemion-team":{"command":"previous"}}}')
        with pytest.raises(agents.local_state.LocalSetupError, match="changed"):
            agents.perform(
                root, install_request(preview, key["api_key"], replace_existing=True), executable
            )
        assert agents.records(root) == []
        assert json.loads(target.read_text())["edited"]


def test_failed_apply_keeps_recoverable_private_setup_and_removal_keeps_external_edits(
    env, tmp_path, monkeypatch
):
    person, key = application(env)
    target, root, executable = tmp_path / "agent.json", tmp_path / "private", Path(sys.executable)
    original = '{"mcpServers":{"existing":{"command":"original"}}}'
    target.write_text(original)
    with running(create_app(env.db, env.embedder)) as endpoint:
        preview = agents.preview(
            root, {"setup": definition(env, person, endpoint, target, "cursor")}, executable
        )
        apply = agent_setup.apply

        def fail(plan):
            raise OSError("Interrupted before replacement")

        monkeypatch.setattr(agent_setup, "apply", fail)
        with pytest.raises(OSError):
            agents.perform(root, install_request(preview, key["api_key"]), executable)
        assert target.read_text() == original
        view = agents.status(root)["installations"][0]
        assert view["state"] == "removed" and view["private_key_file_exists"]
        monkeypatch.setattr(agent_setup, "apply", apply)
        target.write_text('{"mcpServers":{"mnemion-team":{"command":"new-external-owner"}}}')
        view = agents.status(root)["installations"][0]
        assert view["state"] == "replaced"
        agents.perform(
            root,
            {
                "operation": "remove",
                "id": view["id"],
                "configuration_hash": view["configuration_hash"],
                "confirm": True,
            },
            executable,
        )
        assert (
            json.loads(target.read_text())["mcpServers"]["mnemion-team"]["command"]
            == "new-external-owner"
        )
        assert agents.records(root) == []


@pytest.mark.skipif(
    os.name == "nt", reason="The native installed-app probe covers the Windows executable"
)
@pytest.mark.parametrize("cached", [False, True])
def test_installed_standalone_command_discovers_scoped_tools_without_studio(env, tmp_path, cached):
    person, key = application(env)
    env.identities.grant(env.owner, env.space, UUID(person["id"]), GrantInput(role="reader"))
    bundle = tmp_path / "app-runtime"
    bundle.mkdir()
    executable = bundle / "mnemion-engine"
    executable.write_text(
        f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -m mnemion.service.cli "$@"\n'
    )
    executable.chmod(0o700)
    if cached:
        content = executable.read_bytes()
        (bundle / "mnemion-runtime.json").write_text(
            json.dumps(
                {
                    "format": 1,
                    "component": "service",
                    "version": "4.32.0",
                    "files": {
                        executable.name: {
                            "size": len(content),
                            "sha256": hashlib.sha256(content).hexdigest(),
                            "executable": True,
                        }
                    },
                }
            )
        )
    target, root = tmp_path / "agent.toml", tmp_path / "private"
    with running(create_app(env.db, env.embedder)) as endpoint:
        preview = agents.preview(
            root, {"setup": definition(env, person, endpoint, target, "grok-build")}, executable
        )
        agents.perform(root, install_request(preview, key["api_key"]), executable)
        node = tomlkit.parse(target.read_text())["mcp_servers"]["mnemion-team"]
        assert dict(node) == preview["command"]
        if cached:
            assert agents.status(root)["runtime_version"] == "4.32.0"
            bundle.rename(tmp_path / "appimage-mount-gone")

        async def discover():
            async with MCPClient(
                StdioServerParameters(command=node["command"], args=list(node["args"]))
            ) as client:
                tools = await client.list_tools()
                assert "memory_spaces" in {tool.name for tool in tools.tools}
                spaces = await client.call_tool("memory_spaces", {})
                assert not spaces.is_error
                assert [
                    (item["id"], item["role"]) for item in spaces.structured_content["items"]
                ] == [(str(env.space), "reader")]

        asyncio.run(discover())
