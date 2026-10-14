"""Bounded process failure locations from disposable managed-service fixtures."""

import json
from pathlib import Path
import re


def failure_locations(content: str) -> dict:
    from deploy.installed_upgrade_diagnostics import public_status

    locations = []
    for path, line, function in re.findall(
        r'File "([^"\n]{1,2048})", line ([0-9]{1,7}), in ([A-Za-z_][A-Za-z0-9_]{0,63})',
        content,
    ):
        relative = path.replace("\\", "/").rpartition("/mnemion/")[2]
        if re.fullmatch(r"(?:[a-z_][a-z0-9_]*/){0,4}[a-z_][a-z0-9_]*\.py", relative):
            locations.append(
                {"file": "mnemion/" + relative, "line": int(line), "function": function}
            )
    errors = re.findall(r"(?m)^(?:[a-z_][a-z0-9_]*\.)*([A-Z][A-Za-z]{0,63}Error):", content)
    result = {"locations": locations[-12:], "errors": list(dict.fromkeys(errors))[-4:]}
    diagnostics = []
    for line in content.splitlines()[-32:]:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if diagnostic := public_status(record).get("diagnostic"):
            diagnostics.append(diagnostic)
    if diagnostics:
        result["diagnostics"] = diagnostics[-4:]
    return result


def report(state: Path, status: dict) -> None:
    import psutil
    from mnemion import process_identity
    from mnemion.service import supervision, update_state
    from mnemion.version import __version__

    result = {
        "status": {
            key: status[key]
            for key in (
                "running",
                "ready",
                "http_ready",
                "instance_matches",
                "children_initialized",
                "processes",
            )
            if key in status
        }
    }
    _, settings = supervision.settings(state)
    result["broker_address_published"] = (state / "model-broker/address.json").is_file()
    result["readiness"] = {}
    previous_models = None
    for role in ("api", "worker"):
        path = Path(settings["runtime"]) / (role + "-ready.json")
        checks = {"receipt_exists": path.is_file()}
        result["readiness"][role] = checks
        if not path.is_file():
            continue
        try:
            receipt = update_state.read(path)
            info = next(item for item in status["processes"] if item["name"] == "mnemion-" + role)
            process = psutil.Process(info["pid"])
            checks.update(
                instance_matches=receipt.get("instance") == settings["identifier"],
                role_matches=receipt.get("role") == role,
                pid_matches=receipt.get("pid") == info["pid"],
                birth_matches=process_identity.matches_record(
                    receipt, process, legacy_field="created"
                ),
                version_matches=receipt.get("version") == __version__,
                models_match=previous_models is None
                or previous_models == receipt.get("generations"),
            )
            previous_models = receipt.get("generations")
        except (OSError, ValueError, KeyError, StopIteration, psutil.Error):
            checks["inspection_failed"] = True
    for role in ("api", "worker"):
        path = state / "logs" / (role + ".log")
        if path.is_symlink() or not path.is_file():
            continue
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - 65536))
            result[role] = failure_locations(stream.read(65536).decode("utf-8", errors="replace"))
    print("Managed fixture startup diagnostics: " + json.dumps(result))
