"""Resolve binary-only service installs before consuming native release runners.

Checks lock-file wheel availability for the current Python version, without
installing packages, compiling code or creating a project environment. Actual
native installation, behavior and upgrade checks remain mandatory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

TARGETS = (
    "x86_64-apple-darwin",
    "aarch64-apple-darwin",
    "x86_64-unknown-linux-gnu",
    "aarch64-unknown-linux-gnu",
    # Both Windows desktop architectures currently package the x64 service.
    "x86_64-pc-windows-msvc",
)


def check(root: Path, uv: str | None = None) -> dict:
    uv = uv or os.environ.get("MNEMION_RELEASE_UV") or shutil.which("uv")
    if not uv or subprocess.check_output([uv, "--version"], text=True).split()[:2] != [
        "uv",
        "0.12.24",
    ]:
        raise ValueError("Install uv==0.12.24 or set MNEMION_RELEASE_UV to its executable")
    directory = root / "build-tmp"
    directory.mkdir(mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="binary-preflight-", dir=directory) as temporary:
        for target in TARGETS:
            result = subprocess.run(
                [
                    uv,
                    "sync",
                    "--locked",
                    "--dry-run",
                    "--no-dev",
                    "--extra",
                    "supervision",
                    "--no-install-project",
                    "--no-build",
                    "--no-python-downloads",
                    "--python",
                    sys.executable,
                    "--python-platform",
                    target,
                    # This dependency is separately built, source-checked and
                    # signed by the Intel Mac native runner. No other omission.
                    *(
                        ["--no-install-package", "cryptography"]
                        if target == "x86_64-apple-darwin"
                        else []
                    ),
                ],
                cwd=root,
                env={
                    **os.environ,
                    "UV_NO_CONFIG": "1",
                    # Match the ONNX wheels' declared platform floors, rather
                    # than uv's implicit macOS 13 default for both architectures.
                    "MACOSX_DEPLOYMENT_TARGET": "14.0"
                    if target == "aarch64-apple-darwin"
                    else "13.0",
                    "UV_PROJECT_ENVIRONMENT": str(Path(temporary) / "unused-venv"),
                },
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode:
                raise RuntimeError(
                    f"Binary dependency preflight failed for {target}:\n{result.stderr[-4000:]}"
                )
    return {
        "python": sys.version.split()[0],
        "targets": list(TARGETS),
        "lock_sha256": hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest(),
        "passed": len(TARGETS),
        "scope": "Lock resolution only; native execution remains a separate gate",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv")
    print(json.dumps(check(Path(__file__).resolve().parents[1], parser.parse_args().uv)))
