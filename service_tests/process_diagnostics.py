"""Bounded process failure locations from disposable managed-service fixtures."""

import json
from pathlib import Path
import re


def failure_locations(content: str) -> dict:
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
    return {"locations": locations[-12:], "errors": list(dict.fromkeys(errors))[-4:]}


def report(state: Path) -> None:
    result = {}
    for role in ("api", "worker"):
        path = state / "logs" / (role + ".log")
        if path.is_symlink() or not path.is_file():
            continue
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - 65536))
            result[role] = failure_locations(stream.read(65536).decode("utf-8", errors="replace"))
    print("Managed fixture startup diagnostics: " + json.dumps(result))
