"""Read-only action declarations, including absent mappings and exclusions.

Inspect shipped interfaces without importing an application or executing its
commands. These are source declarations, never observations of a user's work.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re

from .telemetry_cli_actions import command_names

INPUTS = (
    "mnemion/service/agent_contract.json",
    "studio/electron/desktop-actions.ts",
    "packages/client/src/index.ts",
    "studio/frontend/src/api/client.ts",
    "studio/electron/preload.ts",
    "mnemion/service/mcp.py",
    "mnemion/mcp_server.py",
    "mnemion/cli.py",
)
STUDIO_EXCLUSIONS = {
    "automatic_query": "Automatic queries, polling and saved state do not own a new action.",
    "configuration_preview": "Configuration previews do not establish a completed setup.",
    "continuation_transport": "The enclosing operation owns its upload or continuation steps.",
    "generic_transport": "Generic SDK requests have no inferred workflow or collection owner.",
    "transport_helper": "A transport helper does not own an additional user action.",
}


def _names(source: str, start: str, end: str, pattern: str) -> set[str]:
    """Read the repository's explicit interface syntax, checked against runtime exports in CI."""
    if source.count(start) != 1:
        raise ValueError("Review the changed telemetry action interface")
    body = source.split(start, 1)[1]
    finish = re.search(end, body, re.MULTILINE)
    if finish is None:
        raise ValueError("Review the changed telemetry action interface")
    names = re.findall(pattern, body[: finish.start()], re.MULTILINE)
    names = [
        next(part for part in name if part) if isinstance(name, tuple) else name for name in names
    ]
    if not names or len(names) != len(set(names)):
        raise ValueError("Review missing or duplicate telemetry interface declarations")
    return set(names) - {"constructor"}


def _mcp_name(value: ast.AST) -> str:
    if not isinstance(value, ast.Constant) or type(value.value) is not str or not value.value:
        raise ValueError("Review the changed MCP tool declaration")
    return value.value


def _gateway_names(source: str) -> set[str]:
    """Read fixed decorators and invocation aliases without importing the gateway."""
    tree = ast.parse(source)
    names, registrations = set(), set()
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        registered = False
        for decorator in function.decorator_list:
            if not (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "server"
                and decorator.func.attr == "tool"
            ):
                continue
            options = {item.arg: item.value for item in decorator.keywords}
            if None in options or len(decorator.args) > 1 or (decorator.args and "name" in options):
                raise ValueError("Review the changed MCP tool declaration")
            name = decorator.args[0] if decorator.args else options.get("name")
            names.add(
                function.name
                if name is None or isinstance(name, ast.Constant) and name.value is None
                else _mcp_name(name)
            )
            registrations.add(id(decorator.func))
            registered = True
        if registered:
            for call in ast.walk(function):
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == "invoke"
                ):
                    for option in call.keywords:
                        if option.arg == "_tool":
                            names.add(_mcp_name(option.value))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "server"
            and node.attr in {"tool", "add_tool"}
            and id(node) not in registrations
        ):
            raise ValueError("Review the changed MCP tool registration")
    if not names:
        raise ValueError("Missing MCP gateway tool declarations")
    return names


def _legacy_names(source: str) -> set[str]:
    """Read the fixed legacy registry's keys; handler expressions are never run."""
    tree = ast.parse(source)
    registries = []
    for node in ast.walk(tree):
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else [node.target]
            if isinstance(node, ast.AnnAssign)
            else []
        )
        if any(isinstance(target, ast.Name) and target.id == "TOOLS" for target in targets):
            registries.append(node.value)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "TOOLS"
            and node.func.attr not in {"get", "items", "keys", "values", "copy"}
        ) or (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "TOOLS"
            and isinstance(node.ctx, (ast.Store, ast.Del))
        ):
            raise ValueError("Review the changed MCP legacy registry")
    if len(registries) != 1 or not isinstance(registries[0], ast.Dict):
        raise ValueError("Review the changed MCP legacy registry")
    names = [_mcp_name(key) for key in registries[0].keys]
    if not names or len(names) != len(set(names)):
        raise ValueError("Missing or duplicate MCP legacy tool declaration")
    return set(names)


def build(root: Path, documents: dict) -> tuple[dict, dict]:
    raw = {name: (root / name).read_bytes() for name in INPUTS}
    contract = json.loads(raw[INPUTS[0]])
    if contract.get("schema_version") != 1:
        raise ValueError("Review the changed control interface version")
    operations = [item["name"] for item in contract["operations"]]
    if len(operations) != len(set(operations)):
        raise ValueError("Duplicate control interface declaration")
    interfaces = {
        "control_cli": set(operations),
        "native_commands": _names(
            raw[INPUTS[1]].decode(),
            "export const desktopActions = {",
            r"^} as const",
            r"^  (?:'([^']+)'|([A-Za-z][\w]*)): \{",
        ),
        "studio_actions": _names(
            raw[INPUTS[2]].decode(),
            "export class MnemionClient {",
            r"^}",
            r"^  (?:(?:private|public|protected|async|static)\s+)*([A-Za-z_$][\w$]*)(?:<[^\n]+>)?\(",
        ),
        "legacy_ui": _names(
            raw[INPUTS[3]].decode(),
            "export const api = measuredLegacyClient({",
            r"^}\)",
            r"^  ([A-Za-z_$][\w$]*):",
        ),
        "desktop_ipc": _names(
            raw[INPUTS[4]].decode(),
            "contextBridge.exposeInMainWorld('mnemion', {",
            r"^}\)",
            r"(?:\btransfer|\bipcRenderer\.invoke)\('([^']+)'",
        ),
        "local_stdio": {"gateway." + name for name in _gateway_names(raw[INPUTS[5]].decode())}
        | {"legacy." + name for name in _legacy_names(raw[INPUTS[6]].decode())},
        "classic_cli": command_names(raw[INPUTS[7]].decode()),
    }
    reasons = {}
    rows = []

    def reason(owner: str, name: str, exclusions: dict) -> str:
        if name not in exclusions:
            raise ValueError("Unknown telemetry action exclusion")
        key = owner + "." + name
        previous = reasons.setdefault(key, exclusions[name])
        if previous != exclusions[name]:
            raise ValueError("Conflicting telemetry action exclusion")
        return key

    def add(owner: str, action: str, entry: dict | None, exclusions: dict) -> None:
        base = {"owner": owner, "action": action}
        if entry is None:
            rows.append({**base, "state": "unmeasured", "workflows": []})
        elif entry.get("control") is True:
            rows.append({**base, "state": "delegated", "workflows": [], "delegate": "control_cli"})
        elif "exclusion" in entry:
            name = entry["exclusion"]
            rows.append(
                {
                    **base,
                    "state": "delegated" if name == "delegated_alias" else "excluded",
                    "workflows": [],
                    "reason": reason(owner, name, exclusions),
                }
            )
        elif "variants" in entry:
            variants = entry["variants"]
            excluded = entry.get("variant_exclusions", {})
            if not variants and not excluded:
                rows.append({**base, "state": "unmeasured", "workflows": []})
                return
            if set(variants) & set(excluded):
                raise ValueError("An action variant cannot be mapped and excluded")
            for variant in sorted(set(variants) | set(excluded)):
                row = {**base, "selector": entry["selector"], "variant": variant}
                if variant in variants:
                    row.update(state="mapped", workflows=[variants[variant]])
                else:
                    row.update(
                        state="excluded",
                        workflows=[],
                        reason=reason(owner, excluded[variant], exclusions),
                    )
                rows.append(row)
        else:
            rows.append({**base, "state": "mapped", "workflows": [entry["workflow"]]})

    def group(owner: str, entries: dict, exclusions: dict, *, prefix: str = "") -> None:
        names = (
            {name[len(prefix) :] for name in interfaces[owner] if name.startswith(prefix)}
            if owner in interfaces
            else set(entries)
        )
        if set(entries) - names:
            raise ValueError("Telemetry maps refer to an absent interface action")
        for action in sorted(names):
            add(owner, prefix + action, entries.get(action), exclusions)

    controls = documents["control-origins.json"]
    native = documents["desktop-origins.json"]
    studio = documents["studio-methods.json"]
    ui = documents["ui-origins.json"]
    mcp = documents["mcp-origins.json"]
    maintenance = documents["maintenance-origins.json"]
    classic = documents["cli-origins.json"]
    group("control_cli", controls["operations"], controls["exclusions"])
    group("classic_cli", classic["operations"], classic["exclusions"])
    group("native_commands", native["operations"], native["exclusions"])
    ipc = native.get("ipc", {})
    if set(ipc) - interfaces["desktop_ipc"]:
        raise ValueError("Telemetry maps refer to an absent desktop request channel")

    def ipc_action(channel: str, action: str) -> None:
        if action not in interfaces["native_commands"]:
            raise ValueError("Desktop telemetry refers to an absent native action")
        add("desktop_ipc", channel, native["operations"].get(action), native["exclusions"])

    for channel in sorted(interfaces["desktop_ipc"]):
        entry = ipc.get(channel)
        if entry is None:
            add("desktop_ipc", channel, None, native["exclusions"])
        elif set(entry) == {"exclusion"}:
            add("desktop_ipc", channel, entry, native["exclusions"])
        elif set(entry) == {"action"}:
            ipc_action(channel, entry["action"])
        elif set(entry) == {"actions"} and channel in {"hosts:action", "sources:control"}:
            if not entry["actions"]:
                add("desktop_ipc", channel, None, native["exclusions"])
            for variant, action in sorted(entry["actions"].items()):
                ipc_action(channel + "/" + variant, action)
        else:
            raise ValueError("Review the desktop telemetry channel declaration")
    if set(studio["methods"]) & set(studio["excluded"]):
        raise ValueError("A Studio action cannot be mapped and excluded")
    if set(studio["methods"].values()) - interfaces["control_cli"]:
        raise ValueError("A Studio action delegates to an absent control operation")
    studio_entries = {
        name: controls["operations"].get(operation) for name, operation in studio["methods"].items()
    }
    studio_entries.update(
        {name: {"exclusion": value} for name, value in studio["excluded"].items()}
    )
    group("studio_actions", studio_entries, {**controls["exclusions"], **STUDIO_EXCLUSIONS})
    group("browser_connections", ui["browser"], ui["exclusions"])
    if set(ui["legacy"]) & set(ui["legacy_excluded"]):
        raise ValueError("A legacy action cannot be mapped and excluded")
    group(
        "legacy_ui",
        {
            **ui["legacy"],
            **{name: {"exclusion": value} for name, value in ui["legacy_excluded"].items()},
        },
        ui["exclusions"],
    )
    for name in ("gateway", "legacy"):
        group("local_stdio", mcp[name], mcp["exclusions"], prefix=name + ".")
    for key, owner in (
        ("origins", "local_maintenance"),
        ("capture_controls", "headless_controls"),
        ("model_preparation", "headless_models"),
        ("host_updates", "host_updates"),
    ):
        group(owner, maintenance[key], maintenance["exclusions"])
    states = ("mapped", "excluded", "delegated", "unmeasured")
    result = {
        "scope": "declared_actions_and_variants",
        "qualification": (
            "Interface actions and reviewed source routes, including fixed variants. "
            "Missing interface mappings remain unmeasured even when their category has "
            "another owner. Declarations do not prove every screen, sensor or installed "
            "runtime; no private activity is inspected and no collection is authorized."
        ),
        "interface_checked_owners": list(interfaces),
        "summary": {
            "total": len(rows),
            **{state: sum(row["state"] == state for row in rows) for state in states},
        },
        "reasons": reasons,
        "actions": rows,
    }
    if len(json.dumps(result).encode()) > 128 * 1024:
        raise ValueError("Action coverage exceeds its bounded inspection budget")
    return result, {name: hashlib.sha256(data).hexdigest() for name, data in raw.items()}
