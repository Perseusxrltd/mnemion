"""Bridge an older managed installation to the verified candidate's upgrade CLI.

Run with the existing managed installation's Python. This script does not replace
the bootstrap environment, create a second service, or accept a download URL.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--allow-migration", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    # Absolute imports deliberately use the caller's already installed updater.
    from mnemion.service import service_updates as updates
    from mnemion.service import update_state as state_io
    from mnemion.service.update_manifest import ManifestError, version_tuple

    try:
        if version_tuple(args.version) < (4, 2, 4):
            raise ManifestError("The guided upgrade requires a signed candidate from 4.2.4 onward")
        if args.resume and not args.allow_migration:
            raise ManifestError("Resuming a schema upgrade requires --allow-migration")
        state, root, settings = updates._root(args.state_dir)
        with state_io.lock(root):
            journal = root / "upgrade-journal.json"
            if journal.exists():
                runtime = updates.resolved_runtime(
                    state, runtime=state_io.read(journal)["candidate"]
                )
            elif args.resume:
                raise ManifestError("No interrupted schema upgrade is recorded")
            else:
                checked = updates._check(root)
                if checked.get("current_version") == args.version:
                    print(json.dumps({"status": "current", "version": args.version}))
                    return 0
                if checked.get("available_version") != args.version:
                    raise ManifestError(
                        "Choose the exact currently published version and review its upgrade plan"
                    )
                updates._stage(root, settings)
                release = updates._release(root)
                runtime = updates.resolved_runtime(
                    state,
                    runtime=state_io.read(updates._slot(root, release) / "ready.json")["runtime"],
                )
            if (
                runtime["version"] != args.version
                or not (Path(runtime["package"]) / "service/managed_upgrade.py").is_file()
            ):
                raise ManifestError("The verified candidate does not provide this upgrade command")
        arguments = [
            runtime["python"],
            "-I",
            "-m",
            "mnemion.service.cli",
            "updates",
            "upgrade" if args.allow_migration else "plan",
            "--state-dir",
            str(state),
        ]
        if args.allow_migration:
            arguments.extend(["--version", args.version, "--allow-migration"])
        if args.resume:
            arguments.append("--resume")
        return subprocess.call(arguments, cwd=runtime["directory"], env=updates._environment())
    except state_io.OperationBusy:
        print(
            json.dumps(
                {"status": "deferred", "reason": "operation_in_progress", "retry_after_seconds": 30}
            )
        )
        return 75
    except Exception as error:
        print(
            json.dumps(
                {
                    "error": str(error)
                    if isinstance(error, ManifestError)
                    else "Upgrade preparation failed; inspect the private managed update logs."
                }
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
