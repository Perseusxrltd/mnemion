"""Source checks for the hosted Firefox and WebKit journey. No browser is launched."""

import asyncio
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import pytest

from deploy.probe_telemetry_browser import (
    ENGINES,
    JOURNEY_ATTEMPTS,
    fixture_marker,
    journey_qualified,
    matching_report,
    reject_compiled_marker,
    require_diagnostic_limits,
    sensor_availability,
    shutdown_owned_listener,
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
    marker = fixture_marker().encode()
    body = bytes(range(25))
    shown = __import__("base64").b64encode(body).decode()
    assert matching_report(shown, body.hex(), marker=marker) == body
    with pytest.raises(ValueError, match="25-byte"):
        matching_report(shown, bytes(range(1, 26)).hex(), marker=marker)
    leaked = bytearray(body)
    assert len(marker) < len(body)
    leaked[: len(marker)] = marker
    leaked_shown = __import__("base64").b64encode(bytes(leaked)).decode()
    with pytest.raises(ValueError, match="Fixture memory"):
        matching_report(leaked_shown, bytes(leaked).hex(), marker=marker)
    with pytest.raises(ValueError, match="Fixture memory"):
        matching_report(shown, body.hex(), marker, marker=marker)
    with pytest.raises(ValueError, match="25-byte report"):
        matching_report(shown, body.hex(), marker=b"")


def test_fixture_marker_is_private_and_not_a_bundled_document_literal():
    document = (ROOT / "docs/implementation/telemetry-browser-journeys-2026-10-30.md").read_bytes()
    assert b"PRIVATE_BROWSER_CANARY" not in document
    first = fixture_marker().encode()
    second = fixture_marker().encode()
    assert first != second
    assert 16 <= len(first) <= 25
    assert first not in document and second not in document
    bundled = b"var docs=" + document
    reject_compiled_marker(bundled, first)
    with pytest.raises(RuntimeError, match="compiled into the app"):
        reject_compiled_marker(bundled + first, first)


def _clean_cleanup(**overrides):
    cleanup = {
        "collector_stopped": True,
        "collector_shutdown_errors": [],
        "memory_api_stopped": True,
        "profiles_removed": True,
        "private_input_removed": True,
        "production_disclosure_unchanged": True,
        "production_route_unchanged": True,
        "errors": [],
    }
    cleanup.update(overrides)
    return cleanup


def test_cleanup_failure_does_not_qualify_the_journey():
    completed = [{"journey_completed": True}, {"journey_completed": True}]
    assert journey_qualified(completed, None, _clean_cleanup()) is True
    assert journey_qualified(completed, "RuntimeError: original", _clean_cleanup()) is False
    assert journey_qualified(completed, None, _clean_cleanup(collector_stopped=False)) is False
    assert (
        journey_qualified(
            completed,
            None,
            _clean_cleanup(collector_shutdown_errors=["ValueError: Invalid file descriptor: -1"]),
        )
        is False
    )
    assert journey_qualified(completed[:1], None, _clean_cleanup()) is False


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
    assert_production_inactive(
        __import__("json").loads(disclosure), __import__("json").loads(route)
    )
    copy = tmp_path / "copy"
    for relative in (
        "mnemion/product_telemetry/disclosure.json",
        "mnemion/product_telemetry/transport-route.json",
        "studio/electron/package.json",
    ):
        target = copy / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / relative).read_bytes())
    # Generate an ephemeral certificate accepted by the production validator.
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
    baked = __import__("json").loads(
        (copy / "mnemion/product_telemetry/disclosure.json").read_text()
    )
    assert baked["collection_available"] is True
    assert baked["destination"] == "https://localhost:48763/v3/report"
    assert list(copy.rglob("*"))  # the copy exists
    marker = fixture_marker().encode()
    assert not any(marker in path.read_bytes() for path in copy.rglob("*") if path.is_file())


def test_workflow_is_manual_linux_and_uses_both_engines():
    workflow = (ROOT / ".github/workflows/telemetry-browser-journeys.yml").read_text(
        encoding="utf-8"
    )
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


def test_collector_listener_stays_open_until_its_task_stops():
    async def exercise():
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        seen = {}

        class Server:
            def __init__(self):
                self.should_exit = False

        server = Server()

        async def serve():
            while not server.should_exit:
                await asyncio.sleep(0.01)
            seen["fileno"] = listener.fileno()
            listener.getsockname()

        task = asyncio.create_task(serve())
        await asyncio.sleep(0.03)
        errors = await shutdown_owned_listener(
            server, task, listener, wait_seconds=2, cancel_seconds=1
        )
        assert errors == []
        assert seen["fileno"] >= 0
        assert listener.fileno() == -1
        assert task.done()
        assert task.exception() is None

    asyncio.run(exercise())


def test_closing_the_listener_before_shutdown_raises_invalid_descriptor():
    async def exercise():
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        stop = asyncio.Event()

        async def serve():
            await stop.wait()
            if listener.fileno() < 0:
                raise ValueError("Invalid file descriptor: -1")
            listener.getsockname()

        task = asyncio.create_task(serve())
        await asyncio.sleep(0.02)
        listener.close()
        stop.set()
        with pytest.raises(ValueError, match="Invalid file descriptor"):
            await task

    asyncio.run(exercise())


def test_collector_task_error_is_retained_and_does_not_replace_the_original():
    async def exercise():
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)

        class Server:
            should_exit = False

        async def serve():
            listener.close()
            raise ValueError("Invalid file descriptor: -1")

        task = asyncio.create_task(serve())
        await asyncio.sleep(0.05)
        errors = await shutdown_owned_listener(
            Server(), task, listener, wait_seconds=2, cancel_seconds=1
        )
        assert errors == ["ValueError: Invalid file descriptor: -1"]
        assert listener.fileno() == -1
        original = "RuntimeError: The memory canary was compiled into the app"
        assert (
            journey_qualified(
                [{"journey_completed": True}, {"journey_completed": True}],
                original,
                _clean_cleanup(collector_shutdown_errors=errors),
            )
            is False
        )
        assert original == "RuntimeError: The memory canary was compiled into the app"

    asyncio.run(exercise())


def test_collector_cancellation_is_finite_and_unsuccessful():
    async def exercise():
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        release = asyncio.Event()

        class Server:
            should_exit = False

        async def stubborn():
            while not release.is_set():
                try:
                    await asyncio.sleep(0.05)
                except asyncio.CancelledError:
                    continue

        task = asyncio.create_task(stubborn())
        await asyncio.sleep(0.02)
        errors = await shutdown_owned_listener(
            Server(), task, listener, wait_seconds=0.1, cancel_seconds=0.1
        )
        assert errors == ["collector cancellation timed out"]
        assert task.done() is False
        assert listener.fileno() == -1
        assert (
            journey_qualified(
                [{"journey_completed": True}, {"journey_completed": True}],
                None,
                _clean_cleanup(collector_stopped=False, collector_shutdown_errors=errors),
            )
            is False
        )
        release.set()
        await asyncio.wait_for(task, 1)

    asyncio.run(exercise())


def test_owned_process_cleanup_is_finite():
    async def exercise():
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import time; time.sleep(60)",
            start_new_session=True,
        )
        await stop_owned(process)
        assert process.returncode is not None

    asyncio.run(exercise())
