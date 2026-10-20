"""Catch desktop-bridge test/dependency drift before reserving native runners."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET


def check(root: Path, uv: str | None = None) -> dict:
    root = root.resolve()
    uv = uv or os.environ.get("MNEMION_RELEASE_UV") or shutil.which("uv")
    if not uv:
        raise ValueError("Install the release's pinned uv or set MNEMION_RELEASE_UV")
    command = [
        uv,
        "run",
        "--project",
        "studio/client",
        "--locked",
        "--no-python-downloads",
        "python",
    ]
    runtime = subprocess.check_output(
        [*command, "-c", "import sys,platform; print(sys.version); print(platform.platform())"],
        cwd=root,
        text=True,
        timeout=120,
    )
    digest = hashlib.sha256(runtime.encode())
    inputs = {
        *root.joinpath("client_tests").rglob("*.py"),
        *root.joinpath("mnemion").rglob("*.py"),
        root / "pyproject.toml",
        root / "studio/client/pyproject.toml",
        root / "studio/client/uv.lock",
        root / "deploy/client_preflight.py",
    }
    for path in sorted(inputs):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes())
    fingerprint = digest.hexdigest()
    directory = root / "build-tmp"
    directory.mkdir(mode=0o700, exist_ok=True)
    receipt = directory / f"client-preflight-{fingerprint}.json"
    if receipt.is_file() and not receipt.is_symlink() and receipt.stat().st_size < 4096:
        saved = json.loads(receipt.read_text())
        if saved.get("fingerprint") == fingerprint and saved.get("passed", 0) > 0:
            return {**saved, "cached": True}
    with tempfile.TemporaryDirectory(prefix="client-preflight-", dir=directory) as temporary:
        report = Path(temporary) / "junit.xml"
        subprocess.run(
            [*command, "-m", "pytest", "client_tests", "-q", f"--junitxml={report}"],
            cwd=root,
            check=True,
            timeout=180,
        )
        suites = ET.parse(report).getroot().findall("testsuite")
        tests = sum(int(suite.get("tests", "0")) for suite in suites)
        skipped = sum(int(suite.get("skipped", "0")) for suite in suites)
        failed = sum(int(suite.get(key, "0")) for suite in suites for key in ("failures", "errors"))
        if tests <= skipped or failed:
            raise ValueError("The lightweight client environment did not pass its tests")
    result = {
        "fingerprint": fingerprint,
        "passed": tests - skipped,
        "skipped": skipped,
        "cached": False,
        "scope": "Local locked desktop bridge; native acceptance remains mandatory",
    }
    receipt.write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(check(Path(__file__).resolve().parents[1])))
