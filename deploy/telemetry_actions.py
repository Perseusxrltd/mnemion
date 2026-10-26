"""Read-only action declarations, including absent mappings and exclusions.

Inspect shipped interfaces without importing an application or executing its
commands. These are source declarations, never observations of a user's work.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


INPUTS = (
    "mnemion/service/agent_contract.json",
    "studio/electron/desktop-actions.ts",
    "packages/client/src/index.ts",
    "studio/frontend/src/api/client.ts",
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
        names = interfaces.get(owner, set(entries))
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
    group("control_cli", controls["operations"], controls["exclusions"])
    group("native_commands", native["operations"], native["exclusions"])
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
