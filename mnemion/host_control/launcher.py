"""Standalone copy run by the host's stable Supervisor Python installation.

Only the existing managed-runtime verifier is imported from that bootstrap.
The actual control service runs inside its pinned, independently verified slot.
This file is copied verbatim during explicit OS-owner adoption.
"""

import os
from pathlib import Path
import sys
from uuid import uuid4


def launch(root: Path):
    # Match the existing python -m Supervisor entry point: its protected
    # configuration chooses the bootstrap working directory. A copied script
    # otherwise searches the control state instead of that reviewed package.
    sys.path.insert(0, str(Path.cwd()))
    from mnemion.service import service_updates as updates
    from mnemion.service import supervision, update_state as state_io

    root = root.absolute()
    settings = state_io.read(root / "settings.json")
    service, config = supervision.settings(Path(settings["service_state"]))
    if config["identifier"] != settings["service_identity"] or not config.get("managed_updates"):
        raise ValueError("Adopted host identity changed")
    pins_path = service / "updates/host-control-runtime.json"
    with state_io.lock(root / "runtime-control"):
        pins = state_io.read(pins_path)
        if (
            type(pins["format"]) is not int
            or pins["format"] != 1
            or pins["host_id"] != settings["host_id"]
            or pins["state"] != str(root)
            or type(pins["pending"]) is not bool
            or type(pins["attempts"]) is not int
            or not 0 <= pins["attempts"] <= 3
        ):
            raise ValueError("Independent runtime belongs to another host")
        if pins["pending"]:
            if pins["attempts"] >= 2:
                if pins["previous"] is None:
                    raise ValueError("Independent runtime needs recovery")
                pins.update(
                    rejected_slot=pins["current"]["slot"],
                    current=pins["previous"],
                    previous=None,
                    pending=False,
                    attempts=0,
                    fallback=True,
                )
            else:
                pins["attempts"] += 1
            pins["revision"] = str(uuid4())
            state_io.write(pins_path, pins)
        runtime = updates.resolved_runtime(service, runtime=pins["current"])
    os.chdir(runtime["directory"])
    command = [
        runtime["python"],
        *(["-I"] if runtime["isolated"] else []),
        "-m",
        "mnemion.host_control.cli",
        "serve",
        "--state-dir",
        str(root),
    ]
    os.execve(runtime["python"], command, updates._environment())


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("Use one adopted host")
        launch(Path(sys.argv[1]))
    except Exception:
        print(
            "The independent host controller could not start; inspect its protected configuration.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
