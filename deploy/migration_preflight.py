"""Run and cache focused schema-upgrade checks before consuming native runners."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

TESTS = (
    "service_tests/test_author_withdrawal_upgrade.py",
    "service_tests/test_company_sign_in_upgrade.py",
    "service_tests/test_journal_folding_upgrade.py",
    "service_tests/test_capture_policy_upgrade.py",
    "service_tests/test_installed_upgrade_inventory.py",
)


def check(root: Path) -> dict:
    root = root.resolve()
    inputs = {
        *root.joinpath("mnemion").rglob("*.py"),
        *root.joinpath("mnemion/service/migrations").glob("*.sql"),
        *[root / name for name in TESTS],
        root / "service_tests/conftest.py",
        root / "deploy/installed_upgrade_probe.py",
        root / "deploy/migration_preflight.py",
        root / "pyproject.toml",
        root / "uv.lock",
    }
    digest = hashlib.sha256((sys.version + platform.platform()).encode())
    for path in sorted(inputs):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes())
    identity = digest.hexdigest()
    directory = root / "build-tmp"
    directory.mkdir(mode=0o700, exist_ok=True)
    receipt = directory / f"migration-preflight-{identity}.json"
    if receipt.is_file() and not receipt.is_symlink() and receipt.stat().st_size < 4096:
        saved = json.loads(receipt.read_text())
        if saved.get("fingerprint") == identity and saved.get("passed", 0) > 0:
            return {**saved, "cached": True}
    with tempfile.TemporaryDirectory(prefix="migration-preflight-", dir=directory) as temporary:
        report = Path(temporary) / "junit.xml"
        subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *TESTS, f"--junitxml={report}"],
            cwd=root,
            env={**os.environ, "MNEMION_STUDIO_ENABLED": "0"},
            check=True,
            timeout=600,
        )
        suites = ET.parse(report).getroot().findall("testsuite")
        count = sum(int(suite.get("tests", "0")) for suite in suites)
        incomplete = sum(
            int(suite.get(field, "0"))
            for suite in suites
            for field in ("skipped", "failures", "errors")
        )
        if not count or incomplete:
            raise ValueError(
                "Migration preflight needs passing PostgreSQL checks; skipped checks are not proof."
            )
    result = {"fingerprint": identity, "passed": count, "cached": False}
    receipt.write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(check(Path(__file__).resolve().parents[1])))
