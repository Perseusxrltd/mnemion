"""One Firefox journey and one WebKit journey against the built Studio app.

Linux hosted CI only. The production disclosure and route stay inactive.
A disposable tracked copy receives only the reviewed loopback bake, then the
normal frontend build. This does not install a browser on a desktop, accept
native Safari, or claim resource or production collection.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import sys
import tempfile


ENGINES = ("firefox", "webkit")
JOURNEY_ATTEMPTS = 1
# Short enough to detect a content leak inside the fixed 25-byte report.
CANARY = "PRIVATE_BROWSER_CANARY"
CANARY_BYTES = CANARY.encode()
BUILD_TIMEOUT_SECONDS = 600
JOURNEY_TIMEOUT_SECONDS = 300
SENSOR_STATES = ("unavailable", "present")
BAKED_FILES = (
    "mnemion/product_telemetry/disclosure.json",
    "mnemion/product_telemetry/transport-route.json",
)


def sensor_availability(observed: object) -> str:
    """A missing browser sensor is unavailable. Zero is not a reading."""
    if observed not in SENSOR_STATES:
        raise ValueError("Missing browser sensors are unavailable, never zero")
    return observed


def matching_report(shown_base64: str, received_hex: str, *stored: bytes) -> bytes:
    """The approved body, the TLS body and retained storage must be the same 25 bytes."""
    try:
        body = base64.b64decode(shown_base64, validate=True)
    except Exception as exc:
        raise ValueError("Reviewed report is not canonical base64") from exc
    if len(body) != 25 or body.hex() != received_hex:
        raise ValueError("Reviewed report does not match the received 25-byte body")
    if CANARY_BYTES in body or any(CANARY_BYTES in blob for blob in stored):
        raise ValueError("Fixture memory content appeared in telemetry")
    return body


def require_diagnostic_limits(receipt: dict) -> None:
    if receipt.get("resource_acceptance") is not False:
        raise ValueError("This journey cannot claim resource acceptance")
    if receipt.get("production_collection_available") is not False:
        raise ValueError("This journey cannot claim production collection")
    if receipt.get("native_safari_acceptance") is not False:
        raise ValueError("WebKit engine evidence is not native Safari acceptance")
    if receipt.get("journey_attempts") != JOURNEY_ATTEMPTS:
        raise ValueError("Each engine runs one finite journey")
    if tuple(receipt.get("engines", ())) != ENGINES:
        raise ValueError("The journey is Firefox and WebKit")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _scrub(path: Path, secret: str) -> None:
    if not secret or not path.is_file():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    if secret in text:
        path.write_text(text.replace(secret, "[redacted]"), encoding="utf-8")


async def stop_owned(process: asyncio.subprocess.Process | None) -> None:
    """Stop one subprocess and every process it still owns. The wait is finite."""
    if process is None or process.returncode is not None:
        return
    pid = process.pid
    children = []
    try:
        import psutil

        children = psutil.Process(pid).children(recursive=True)
    except Exception:
        children = []
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), 10)
    except TimeoutError:
        process.kill()
        await process.wait()
    for child in children:
        try:
            if child.is_running():
                child.kill()
        except Exception:
            pass
    if os.name != "nt":
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass


def _header_names(scope: dict) -> set[str]:
    names = set()
    for name, _value in scope.get("headers", []):
        if type(name) is bytes:
            names.add(name.decode("latin1").lower())
    return names


async def run(source: Path, output: Path, playwright: Path) -> dict:
    if sys.platform != "linux":
        raise ValueError("The Firefox and WebKit telemetry journey is a Linux hosted CI check")
    if not playwright.is_file():
        raise RuntimeError("The pinned Playwright module is required")
    source = source.resolve()
    output = output.resolve()
    # The workflow records dispatch.json before calling this driver.
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    if any(path.name != "dispatch.json" for path in output.iterdir()):
        raise RuntimeError("Use a fresh browser journey evidence directory")
    disclosure_path = source / BAKED_FILES[0]
    route_path = source / BAKED_FILES[1]
    original_disclosure = disclosure_path.read_bytes()
    original_route = route_path.read_bytes()
    from deploy.telemetry_installed_fixture import (
        assert_production_inactive,
        issue_loopback,
        write_bake,
    )

    assert_production_inactive(json.loads(original_disclosure), json.loads(original_route))
    if not (source / "packages/client/dist").is_dir():
        raise RuntimeError("Build packages/client before the browser journey")
    for relative in ("packages/client/node_modules", "studio/frontend/node_modules"):
        if not (source / relative).is_dir():
            raise RuntimeError(f"Install {relative} before the browser journey")

    from deploy.probe_telemetry_installed import copy_declared_source
    from deploy.report_telemetry_renderer import absorb_reviewed_chunk, retain_reviewed_packet
    from deploy.telemetry_memory_fixture import memory_workspace
    from mnemion.product_telemetry import policy
    from mnemion.product_telemetry.collector_v3 import CollectorV3
    import uvicorn

    phases = ["collector_starting"]
    results = []
    original_failure = None
    cleanup = {
        "collector_stopped": False,
        "memory_api_stopped": False,
        "profiles_removed": False,
        "private_input_removed": True,
        "production_disclosure_unchanged": False,
        "production_route_unchanged": False,
    }
    published: list = []
    reviewed: list[str] = []
    header_names: set[str] = set()
    counts = {
        "post_reports": 0,
        "accepted": 0,
        "body_bytes": 0,
        "preflight": 0,
        "credential_headers": 0,
        "referer_headers": 0,
        "user_agent_headers": 0,
    }
    received_flag = output / "received.json"
    task = None
    server = None
    tls_root = None
    secret = ""

    async def ingress(scope, receive, send):
        post = (
            scope.get("type") == "http"
            and scope.get("method") == "POST"
            and scope.get("path") == "/v3/report"
        )
        options = (
            scope.get("type") == "http"
            and scope.get("method") == "OPTIONS"
            and scope.get("path") == "/v3/report"
        )
        captured = bytearray() if post else None
        chunks = 0
        if post or options:
            names = _header_names(scope)
            header_names.update(names)
            if post:
                counts["post_reports"] += 1
                counts["credential_headers"] += bool(names & {"cookie", "authorization"})
                counts["referer_headers"] += "referer" in names
                counts["user_agent_headers"] += "user-agent" in names
            else:
                counts["preflight"] += 1

        async def received():
            nonlocal captured, chunks
            event = await receive()
            if post and event.get("type") == "http.request":
                chunk = event.get("body", b"")
                if type(chunk) is bytes:
                    counts["body_bytes"] += len(chunk)
                    captured, chunks = absorb_reviewed_chunk(captured, chunks, chunk)
            return event

        async def sending(event):
            if post and event.get("type") == "http.response.start" and event.get("status") == 204:
                counts["accepted"] += 1
            await send(event)

        await CollectorV3(published.append)(scope, received, sending)
        if post and captured is not None and len(reviewed) < 8:
            retained = retain_reviewed_packet([bytes(captured)], review=True)
            if retained is not None:
                reviewed.append(retained)
                if not received_flag.exists():
                    _write_json(received_flag, {"body_hex": retained})
        if captured is not None:
            captured.clear()

    try:
        with tempfile.TemporaryDirectory(prefix="mnemion-browser-journey-") as temporary:
            root = Path(temporary)
            tls_root = root / "loopback"
            issue_loopback(tls_root)
            certificate = tls_root / "certificate.pem"
            key_path = tls_root / "key.pem"
            if output in key_path.resolve().parents or key_path.resolve().is_relative_to(output):
                raise RuntimeError(
                    "The loopback private key must stay outside the evidence directory"
                )
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(8)
                port = listener.getsockname()[1]
                destination = f"https://localhost:{port}/v3/report"
                context = ssl_context(certificate, key_path)
                config = uvicorn.Config(
                    ingress,
                    log_config=None,
                    access_log=False,
                    server_header=False,
                    date_header=False,
                    timeout_keep_alive=0,
                    ssl_certfile=str(certificate),
                    ssl_keyfile=str(key_path),
                )
                config.load()
                config.ssl = context
                server = uvicorn.Server(config)
                task = asyncio.create_task(server.serve(sockets=[listener]))
                async with asyncio.timeout(20):
                    while not server.started:
                        if task.done():
                            await task
                            raise RuntimeError("Owned TLS collector did not start")
                        await asyncio.sleep(0.01)
                phases.append("collector_ready")
                copy = root / "source"
                identity = await asyncio.to_thread(copy_declared_source, source, copy)
                phases.append("source_copied")
                inventory = write_bake(
                    copy, destination, "127.0.0.1", certificate.read_text(encoding="utf-8")
                )
                if inventory["baked_files"] != list(BAKED_FILES):
                    raise RuntimeError(
                        "The loopback bake touched more than the disclosure and route"
                    )
                for relative in ("packages/client/node_modules", "studio/frontend/node_modules"):
                    (copy / relative).symlink_to(source / relative, target_is_directory=True)
                phases.append("disclosure_baked")
                _write_json(
                    output / "source.json",
                    {
                        "source": identity["source"],
                        "tracked_sha256": identity["tracked_sha256"],
                        "production_disclosure_sha256": _sha256(original_disclosure),
                        "production_route_sha256": _sha256(original_route),
                        **{
                            key: inventory[key]
                            for key in (
                                "baked_files",
                                "diagnostic_disclosure_sha256",
                                "diagnostic_route_sha256",
                                "destination_host",
                                "destination_path",
                                "route_address",
                                "diagnostic_collection_available",
                                "production_collection_available",
                            )
                        },
                    },
                )
                build_env = {
                    key: value
                    for key, value in os.environ.items()
                    if key not in {"ELECTRON_BUILD", "GH_TOKEN", "GITHUB_TOKEN", "NODE_AUTH_TOKEN"}
                    and not key.startswith("MNEMION_")
                }
                builder = None
                with (output / "frontend-build.log").open("x", encoding="utf-8") as log:
                    builder = await asyncio.create_subprocess_exec(
                        "npm",
                        "--prefix",
                        str(copy / "studio/frontend"),
                        "run",
                        "build",
                        cwd=copy / "studio/frontend",
                        env=build_env,
                        stdout=log,
                        stderr=asyncio.subprocess.STDOUT,
                        start_new_session=True,
                    )
                    try:
                        await asyncio.wait_for(builder.wait(), BUILD_TIMEOUT_SECONDS)
                    finally:
                        await stop_owned(builder)
                if builder.returncode:
                    raise RuntimeError("Inspect retained frontend-build.log")
                dist = copy / "studio/frontend/dist"
                compiled = b"".join(
                    path.read_bytes()
                    for path in dist.rglob("*")
                    if path.is_file() and path.suffix in {".js", ".html"}
                )
                if destination.encode() not in compiled:
                    raise RuntimeError(
                        "The built frontend does not contain the baked loopback destination"
                    )
                if CANARY_BYTES in compiled:
                    raise RuntimeError("The memory canary was compiled into the app")
                phases.append("frontend_built")
                child_env = dict(build_env)
                child_env["MNEMION_PROBE_PLAYWRIGHT"] = str(playwright.resolve())
                # Host company policy must not change this private fixture.
                # An absent file in an existing directory is the unmanaged default.
                absent_policy = root / "no-company-policy.json"
                from unittest.mock import patch

                with patch.object(policy, "company_policy_file", lambda: absent_policy):
                    async with memory_workspace(root, studio_dist=dist) as (memory, memory_counts):
                        phases.append("memory_api_ready")
                        secret = memory["api_key"]
                        origin = memory["base_url"]
                        for engine in ENGINES:
                            before_reports = list(reviewed)
                            before_api = dict(memory_counts)
                            before_api["_credentials"] = counts["credential_headers"]
                            before_api["_referers"] = counts["referer_headers"]
                            received_flag.unlink(missing_ok=True)
                            profile = root / f"profile-{engine}"
                            profile.mkdir(mode=0o700)
                            secret_path = root / f"{engine}-input.json"
                            _write_json(
                                secret_path,
                                {
                                    "engine": engine,
                                    "origin": origin,
                                    "memory": memory,
                                    "canary": CANARY,
                                    "query": f"browserjourneylexical{engine}",
                                    "received_flag": str(received_flag),
                                    "result": str(output / f"{engine}.json"),
                                    "failure": str(output / f"{engine}-failure.json"),
                                    "profile": str(profile),
                                },
                            )
                            secret_path.chmod(0o600)
                            child_env["MNEMION_BROWSER_JOURNEY_INPUT"] = str(secret_path)
                            phases.append(f"{engine}_starting")
                            driver = None
                            timed_out = False
                            try:
                                with (output / f"{engine}.log").open("x", encoding="utf-8") as log:
                                    driver = await asyncio.create_subprocess_exec(
                                        "node",
                                        str(source / "deploy/probe_telemetry_browser.mjs"),
                                        cwd=source,
                                        env=child_env,
                                        stdout=log,
                                        stderr=asyncio.subprocess.STDOUT,
                                        start_new_session=True,
                                    )
                                    try:
                                        await asyncio.wait_for(
                                            driver.wait(), JOURNEY_TIMEOUT_SECONDS
                                        )
                                    except TimeoutError:
                                        timed_out = True
                                        await stop_owned(driver)
                                engine_result = {"engine": engine}
                                result_path = output / f"{engine}.json"
                                if result_path.is_file():
                                    engine_result.update(
                                        json.loads(result_path.read_text(encoding="utf-8"))
                                    )
                                if timed_out:
                                    engine_result["original_failure"] = (
                                        f"{engine} journey exceeded {JOURNEY_TIMEOUT_SECONDS}s"
                                    )
                                new_reports = reviewed[len(before_reports) :]
                                shown = engine_result.get("approved_body_base64")
                                approved_hex = engine_result.get("approved_body_hex")
                                matched = False
                                match_error = None
                                same_body = False
                                if isinstance(approved_hex, str):
                                    try:
                                        same_body = new_reports == [
                                            bytes.fromhex(approved_hex).hex()
                                        ]
                                    except ValueError:
                                        same_body = False
                                if (
                                    driver is not None
                                    and driver.returncode == 0
                                    and isinstance(shown, str)
                                    and same_body
                                ):
                                    try:
                                        matching_report(shown, new_reports[0])
                                        matched = True
                                    except ValueError as exc:
                                        match_error = str(exc)
                                elif driver is not None and driver.returncode == 0:
                                    match_error = (
                                        "The collector did not receive exactly the approved body"
                                    )
                                engine_result["collector_reports"] = new_reports
                                engine_result["collector_body_matches_inspection"] = matched
                                engine_result["match_error"] = match_error
                                engine_result["api_requests"] = (
                                    memory_counts["api_requests"] - before_api["api_requests"]
                                )
                                engine_result["api_successful"] = (
                                    memory_counts["api_successful"] - before_api["api_successful"]
                                )
                                engine_result["driver_exit_code"] = (
                                    None if driver is None else driver.returncode
                                )
                                checks = (
                                    engine_result.get("checks")
                                    if isinstance(engine_result.get("checks"), dict)
                                    else {}
                                )
                                sensors = (
                                    engine_result.get("sensors")
                                    if isinstance(engine_result.get("sensors"), dict)
                                    else {}
                                )
                                try:
                                    sensor_record = {
                                        name: sensor_availability(sensors.get(name))
                                        for name in (
                                            "pressure_observer",
                                            "heap_memory",
                                            "network_information",
                                        )
                                    }
                                except ValueError as exc:
                                    sensor_record = {}
                                    match_error = str(exc)
                                engine_result["sensors"] = sensor_record or sensors
                                engine_result["match_error"] = match_error
                                engine_result["journey_completed"] = bool(
                                    driver is not None
                                    and driver.returncode == 0
                                    and not timed_out
                                    and matched
                                    and match_error is None
                                    and engine_result.get("attempts") == JOURNEY_ATTEMPTS
                                    and engine_result.get("native_safari_acceptance") is False
                                    and engine_result.get("resource_acceptance") is False
                                    and engine_result.get("production_collection_available")
                                    is False
                                    and all(
                                        checks.get(name) is True
                                        for name in (
                                            "disclosure_acknowledged",
                                            "manual_review_configured",
                                            "memory_saved",
                                            "memory_fetched",
                                            "lexical_recall",
                                            "inspected_25_byte_report",
                                            "approved_exact_body",
                                            "received_matching_report",
                                            "spent_budget_preserved",
                                            "opt_out_persisted",
                                            "manual_review_persisted",
                                            "canary_absent_from_origin_storage",
                                            "canary_absent_from_reviewed_body",
                                        )
                                    )
                                    and engine_result.get("budget_attempts_after_reload") == 1
                                    and engine_result.get("api_successful", 0) >= 4
                                    and counts["credential_headers"]
                                    == before_api.get("_credentials", counts["credential_headers"])
                                    and counts["referer_headers"]
                                    == before_api.get("_referers", counts["referer_headers"])
                                    and isinstance(engine_result.get("browser_version"), str)
                                    and engine_result["browser_version"]
                                    and not engine_result.get("page_errors")
                                )
                                if engine == "webkit":
                                    engine_result["acceptance"] = (
                                        "webkit_engine_evidence_not_native_safari"
                                    )
                                results.append(engine_result)
                                _write_json(output / f"{engine}-result.json", engine_result)
                                phases.append(f"{engine}_finished")
                            except Exception as exc:
                                if not any(row.get("engine") == engine for row in results):
                                    results.append(
                                        {
                                            "engine": engine,
                                            "journey_completed": False,
                                            "original_failure": f"{type(exc).__name__}: {exc}",
                                            "native_safari_acceptance": False,
                                            "resource_acceptance": False,
                                            "production_collection_available": False,
                                        }
                                    )
                                phases.append(f"{engine}_failed")
                            finally:
                                await stop_owned(driver)
                                secret_path.unlink(missing_ok=True)
                                import shutil

                                shutil.rmtree(profile, ignore_errors=True)
                        cleanup["profiles_removed"] = all(
                            not (root / f"profile-{engine}").exists() for engine in ENGINES
                        )
                        cleanup["memory_api_stopped"] = True
                        phases.append("memory_api_stopped")
                if server is not None and task is not None:
                    server.should_exit = True
                    try:
                        await asyncio.wait_for(task, 10)
                    except TimeoutError:
                        task.cancel()
                cleanup["collector_stopped"] = task is None or task.done()
    except Exception as exc:
        original_failure = f"{type(exc).__name__}: {exc}"
        phases.append("failed")
        raise
    finally:
        if server is not None:
            server.should_exit = True
        if task is not None:
            try:
                await asyncio.wait_for(task, 10)
            except TimeoutError:
                task.cancel()
            cleanup["collector_stopped"] = task.done()
        cleanup["production_disclosure_unchanged"] = (
            disclosure_path.read_bytes() == original_disclosure
        )
        cleanup["production_route_unchanged"] = route_path.read_bytes() == original_route
        if secret:
            for path in output.rglob("*"):
                if path.is_file() and path.suffix in {".json", ".log", ".txt", ".md"}:
                    _scrub(path, secret)
        cleanup["private_input_removed"] = not any(output.rglob("*input.json"))
        _write_json(output / "cleanup.json", cleanup)
        receipt = {
            "schema_version": 1,
            "at": datetime.now(timezone.utc).isoformat(),
            "phases": phases,
            "engines": list(ENGINES),
            "journey_attempts": JOURNEY_ATTEMPTS,
            "results": [
                {
                    "engine": row.get("engine"),
                    "journey_completed": row.get("journey_completed"),
                    "browser_version": row.get("browser_version"),
                    "sensors": row.get("sensors"),
                    "collector_body_matches_inspection": row.get(
                        "collector_body_matches_inspection"
                    ),
                    "api_successful": row.get("api_successful"),
                    "budget_attempts_after_reload": row.get("budget_attempts_after_reload"),
                    "original_failure": row.get("original_failure"),
                    "acceptance": row.get("acceptance"),
                }
                for row in results
            ],
            "collector": dict(counts),
            "observed_request_header_names": sorted(header_names),
            "published_aggregate_count": len(published),
            "loopback_tls_exception": "playwright_ignoreHTTPSErrors",
            "loopback_tls_reason": "Browser fetch cannot load the baked route certificate. The collector still presents that disposable certificate.",
            "resource_acceptance": False,
            "production_collection_available": False,
            "native_safari_acceptance": False,
            "webkit_engine_evidence_only": True,
            "original_failure": original_failure,
            "cleanup": cleanup,
            "journey_completed": bool(results)
            and all(row.get("journey_completed") is True for row in results)
            and len(results) == len(ENGINES)
            and original_failure is None
            and cleanup["production_disclosure_unchanged"]
            and cleanup["production_route_unchanged"],
        }
        require_diagnostic_limits(receipt)
        _write_json(output / "receipt.json", receipt)
    if not receipt["journey_completed"]:
        raise SystemExit("Inspect retained observations; the browser journey did not pass")
    return receipt


def ssl_context(certificate: Path, key: Path):
    import ssl

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(certificate, key)
    return context


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--playwright-module", type=Path)
    args = parser.parse_args()
    if not args.source or not args.output or not args.playwright_module:
        parser.error("--source, --output and --playwright-module are required")
    try:
        asyncio.run(run(args.source, args.output, args.playwright_module))
    except SystemExit:
        raise
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
