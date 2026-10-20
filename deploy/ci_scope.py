"""Keep documentation-only pushes out of the native/service test queues."""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

METADATA = {
    "deploy/issue-releases.json",
    "deploy/maintenance-status.json",
    "deploy/published-release.json",
    "deploy/release-status.json",
    "deploy/research-watch.json",
}


def documentation(path: str) -> bool:
    parts = PurePosixPath(path).parts
    if not parts or path.startswith("/") or ".." in parts:
        return False
    return (
        path in METADATA
        or (len(parts) == 1 and path.endswith(".md"))
        or (parts[0] == "docs" and path.endswith(".md"))
        or bool(re.fullmatch(r"docs/validation/releases/\d+\.\d+\.\d+-status\.json", path))
    )


def scope(root: Path, event: dict, *, event_name: str, release: bool = False) -> dict:
    if release or event_name != "push":
        return {"runtime": True, "reason": "release_or_non_push"}
    before, after = event.get("before"), event.get("after")
    if any(
        not isinstance(value, str) or not re.fullmatch("[0-9a-f]{40}", value) or value == "0" * 40
        for value in (before, after)
    ):
        return {"runtime": True, "reason": "missing_revision"}
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, timeout=10, text=True
        ).strip()
        if head != after:
            return {"runtime": True, "reason": "different_checkout"}
        result = subprocess.run(
            ["git", "diff", "--no-renames", "--name-only", "-z", before, after, "--"],
            cwd=root,
            capture_output=True,
            timeout=15,
            check=True,
        )
        paths = result.stdout.decode("utf-8").rstrip("\0").split("\0")
    except (OSError, subprocess.SubprocessError, UnicodeError):
        # A shallow checkout or unavailable push base must retain every check.
        return {"runtime": True, "reason": "unavailable_diff"}
    only_docs = bool(paths) and all(documentation(path) for path in paths)
    return {
        "runtime": not only_docs,
        "reason": "documentation_only" if only_docs else "runtime_or_unknown_files",
    }


def main() -> None:
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        if not isinstance(event, dict):
            raise ValueError("Invalid event")
    except (KeyError, OSError, ValueError):
        event = {}
    result = scope(
        Path.cwd(),
        event,
        event_name=os.environ.get("GITHUB_EVENT_NAME", ""),
        release=os.environ.get("MNEMION_CI_RELEASE", "false") != "false",
    )
    print("runtime=" + str(result["runtime"]).lower())
    print("reason=" + result["reason"])


if __name__ == "__main__":
    main()
