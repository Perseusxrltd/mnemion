"""Source checks for the hosted Firefox and WebKit journey. No browser is launched."""

import asyncio
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from deploy.probe_telemetry_browser import (
    CANARY,
    ENGINES,
    JOURNEY_ATTEMPTS,
    matching_report,
    require_diagnostic_limits,
    sensor_availability,
    stop_owned,
)
from deploy.telemetry_installed_fixture import assert_production_inactive, write_bake


ROOT = Path(__file__).resolve().parents[1]


def test_sensor_absence_is_unavailable_and_zero_is_refused():
    assert sensor_availability("unavailable") == "unavailable"
    assert sensor_availability("present") == "present"
    with pytest.raises(ValueError, match="never zero"):
        sensor_availability(0)
    with pytest.raises(ValueError, match="never zero"):
        sensor_availability(None)


def test_reviewed_body_must_match_the_received_25_byte_report():
    body = bytes(range(25))
    shown = __import__("base64").b64encode(body).decode()
    assert matching_report(shown, body.hex()) == body
    with pytest.raises(ValueError, match="25-byte"):
        matching_report(shown, bytes(range(1, 26)).hex())
    leaked = bytearray(body)
    leaked[: len(CANARY)] = CANARY.encode()[:25]
    leaked_shown = __import__("base64").b64encode(bytes(leaked)).decode()
    with pytest.raises(ValueError, match="Fixture memory"):
        matching_report(leaked_shown, bytes(leaked).hex())
    with pytest.raises(ValueError, match="Fixture memory"):
        matching_report(shown, body.hex(), CANARY.encode())


def test_receipt_cannot_claim_production_or_safari_acceptance():
    receipt = {
        "resource_acceptance": False,
        "production_collection_available": False,
        "native_safari_acceptance": False,
        "journey_attempts": JOURNEY_ATTEMPTS,
        "engines": list(ENGINES),
    }
    require_diagnostic_limits(receipt)
    receipt["resource_acceptance"] = True
    with pytest.raises(ValueError, match="resource"):
        require_diagnostic_limits(receipt)


def test_loopback_bake_changes_only_the_copy(tmp_path):
    source = ROOT
    disclosure = (source / "mnemion/product_telemetry/disclosure.json").read_bytes()
    route = (source / "mnemion/product_telemetry/transport-route.json").read_bytes()
    assert_production_inactive(__import__("json").loads(disclosure), __import__("json").loads(route))
    copy = tmp_path / "copy"
    for relative in (
        "mnemion/product_telemetry/disclosure.json",
        "mnemion/product_telemetry/transport-route.json",
        "studio/electron/package.json",
    ):
        target = copy / relative
        target.parent.mkdir(parents=True)
        target.write_bytes((source / relative).read_bytes())
    certificate = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"
    # The production validator requires a well-formed public certificate. Use the
    # fixture helper's own sample only when the copied route is still inactive.
    from tests.test_product_telemetry_transport import _certificates

    class Factory:
        def mktemp(self, name):
            path = tmp_path / name
            path.mkdir()
            return path

    issued, _context = _certificates(Factory(), "localhost")
    inventory = write_bake(
        copy, "https://localhost:48763/v3/report", "127.0.0.1", issued.read_text(encoding="utf-8")
    )
    assert inventory["baked_files"] == [
        "mnemion/product_telemetry/disclosure.json",
        "mnemion/product_telemetry/transport-route.json",
    ]
    assert inventory["production_collection_available"] is False
    assert (source / "mnemion/product_telemetry/disclosure.json").read_bytes() == disclosure
    assert (source / "mnemion/product_telemetry/transport-route.json").read_bytes() == route
    baked = __import__("json").loads((copy / "mnemion/product_telemetry/disclosure.json").read_text())
    assert baked["collection_available"] is True
    assert baked["destination"] == "https://localhost:48763/v3/report"
    assert list(copy.rglob("*"))  # the copy exists
    assert not any(CANARY.encode() in path.read_bytes() for path in copy.rglob("*") if path.is_file())


def test_workflow_is_manual_linux_and_uses_both_engines():
    workflow = (ROOT / ".github/workflows/telemetry-browser-journeys.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "\n  push:" not in workflow
    assert "ubuntu-22.04" in workflow
    assert "firefox webkit" in workflow
    assert "playwright@1.64.0-alpha-1790635538000" in workflow
    assert "resource_acceptance" in workflow
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "telemetry-browser-journeys" not in release


def test_driver_syntax():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    completed = subprocess.run(
        [node, "--check", str(ROOT / "deploy/probe_telemetry_browser.mjs")],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr


def test_owned_process_cleanup_is_finite():
    async def exercise():
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-c", "import time; time.sleep(60)",
            start_new_session=True,
        )
        await stop_owned(process)
        assert process.returncode is not None

    asyncio.run(exercise())
