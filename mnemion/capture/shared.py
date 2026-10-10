"""Opt-in session hook using the same selected-source connector as scheduled capture."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Request capture from an explicitly configured Mnemion connector"
    )
    parser.add_argument("--config", type=Path, default=os.environ.get("MNEMION_CONNECTOR_CONFIG"))
    parser.add_argument("--timeout", type=int, default=20, choices=range(1, 121), metavar="SECONDS")
    args = parser.parse_args(argv)
    try:
        if not args.config:
            raise ValueError("No connector configuration was selected")
        # Hook input cannot select a source path, tenant, credential, or command.
        raw = sys.stdin.read(65537)
        if len(raw) > 65536:
            raise ValueError("Hook input is too large")
        event = json.loads(raw or "{}")
        if not isinstance(event, dict):
            raise ValueError("Invalid hook input")
        if not event.get("stop_hook_active", False):
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mnemion.connectors.runner",
                    "--config",
                    str(args.config.expanduser().absolute()),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=args.timeout,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if completed.returncode:
                print(
                    "Mnemion capture did not complete; the selected source remains available for the next scan.",
                    file=sys.stderr,
                )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        print(
            "Mnemion capture was deferred. Check the configured connector with mnemion-connect.",
            file=sys.stderr,
        )
    # A failed capture must not block the conversation or create a recursive hook.
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
