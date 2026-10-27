"""MCP discovery must remain visible without importing or running a server."""

import json
from pathlib import Path
import shutil

import pytest

from deploy import telemetry_actions, telemetry_coverage


ROOT = Path(__file__).resolve().parents[1]
MCP_INPUTS = ("mnemion/service/mcp.py", "mnemion/mcp_server.py")


@pytest.fixture
def interfaces(tmp_path):
    inputs = [telemetry_coverage.OUTPUT]
    inputs.extend(telemetry_coverage.OUTPUT.parent / name for name in telemetry_coverage.INPUTS)
    inputs.extend(Path(name) for name in (*telemetry_actions.INPUTS, *MCP_INPUTS))
    for name in set(inputs):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return tmp_path


@pytest.mark.parametrize("gateway", [True, False])
def test_future_registered_mcp_tool_stays_visible_before_it_has_a_mapping(interfaces, gateway):
    path = interfaces / MCP_INPUTS[0 if gateway else 1]
    original = path.read_text()
    if gateway:
        changed = (
            original
            + '\n@server.tool(name="future_memory_tool")\nasync def future_handler():\n    raise AssertionError("Never execute discovery input")\n'
        )
    else:
        changed = original.replace(
            "TOOLS = {", 'TOOLS = {\n    "future_memory_tool": {"handler": not_executed()},', 1
        )
    path.write_text(changed)
    coverage = telemetry_coverage.build(interfaces)
    assert {
        "owner": "local_stdio",
        "action": ("gateway." if gateway else "legacy.") + "future_memory_tool",
        "state": "unmeasured",
        "workflows": [],
    } in coverage["action_coverage"]["actions"]
    with pytest.raises(ValueError, match="Telemetry coverage is stale"):
        telemetry_coverage.verify(interfaces)


def test_gateway_invocation_aliases_are_discovered_from_actual_calls(interfaces):
    path = interfaces / MCP_INPUTS[0]
    path.write_text(
        path.read_text().replace('_tool="legacy_search"', '_tool="future_search_route"')
    )
    origins = interfaces / telemetry_coverage.OUTPUT.parent / "mcp-origins.json"
    document = json.loads(origins.read_text())
    del document["gateway"]["legacy_search"]
    origins.write_text(json.dumps(document))
    actions = telemetry_coverage.build(interfaces)["action_coverage"]["actions"]
    assert {
        "owner": "local_stdio",
        "action": "gateway.future_search_route",
        "state": "unmeasured",
        "workflows": [],
    } in actions


@pytest.mark.parametrize(
    "declaration",
    [
        "@server.tool(name=dynamic_name)\nasync def future_handler():\n    pass\n",
        "@server.tool(**dynamic_options)\nasync def future_handler():\n    pass\n",
        "server.add_tool(future_handler)\n",
        "@server.tool\nasync def future_handler():\n    pass\n",
    ],
)
def test_changed_gateway_registration_syntax_requires_review(interfaces, declaration):
    path = interfaces / MCP_INPUTS[0]
    path.write_text(path.read_text() + "\n" + declaration)
    with pytest.raises(ValueError, match="MCP"):
        telemetry_coverage.build(interfaces)


def test_missing_legacy_registry_entry_cannot_keep_its_mapping(interfaces):
    path = interfaces / MCP_INPUTS[1]
    path.write_text(
        path.read_text().replace('    "mnemion_telemetry": {', '    "future_privacy": {', 1)
    )
    with pytest.raises(ValueError, match="absent interface action"):
        telemetry_coverage.build(interfaces)
