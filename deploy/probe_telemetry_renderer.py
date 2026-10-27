"""Exercise telemetry in the compiled source renderer, bridge and memory API.

Requires the built desktop/SDK, a GUI display, pgserver, psutil and an explicit
Playwright module. All configuration changes live in an owned temporary copy;
production source and installed profiles are never activated or changed.
"""

import argparse
import asyncio
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

import psutil
import uvicorn

from mnemion.product_telemetry import policy
from mnemion.product_telemetry.collector import Collector
from tests.test_product_telemetry_transport import certificates

from .telemetry_memory_fixture import memory_workspace


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def copy_source(source, destination):
    files = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=source
        )
        .decode()
        .split("\0")
    )
    hashes = {}
    for name in sorted(set(files) - {""}):
        path = source / name
        if not path.is_file():
            continue
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ["studio/electron", "studio/frontend", "packages/client"]:
        (destination / name / "node_modules").symlink_to(source / name / "node_modules")
    for name in ["studio/electron/dist", "packages/client/dist"]:
        shutil.copytree(source / name, destination / name)
        for path in (source / name).rglob("*"):
            if path.is_file():
                hashes[path.relative_to(source).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    return hashes


def linux_residency(pid):
    """Bounded numeric OS counters; never retain process names or mappings."""
    if sys.platform != "linux":
        return None
    fields = {"VmRSS", "VmHWM", "RssAnon", "RssFile", "RssShmem"}
    try:
        with (Path("/proc") / str(pid) / "status").open() as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            return None
        result = {}
        for line in raw.splitlines():
            key, _, value = line.partition(":")
            if key in fields:
                parts = value.split()
                if len(parts) != 2 or parts[1] != "kB" or not parts[0].isdigit():
                    return None
                result[key] = int(parts[0]) * 1024
        return result if set(result) == fields else None
    except OSError:
        return None


async def observe_tree(root, done, *, attribution=False):
    samples = []
    while not done.is_set():
        try:
            marker = json.loads((root / "monitor.json").read_text())
            owner = psutil.Process(marker["pid"])
            processes = []
            for child in [owner, *owner.children(recursive=True)]:
                try:
                    with child.oneshot():
                        cpu = child.cpu_times()
                        row = {
                            "pid": child.pid,
                            "created": child.create_time(),
                            "rss": child.memory_info().rss,
                            "cpu_ms": 1000 * (cpu.user + cpu.system),
                        }
                        if attribution:
                            row["linux_residency"] = linux_residency(child.pid)
                            # Do not add this to observed descendant CPU: doing
                            # that would count reaped children twice.
                            row["reaped_children_cpu_ms"] = 1000 * (
                                getattr(cpu, "children_user", 0)
                                + getattr(cpu, "children_system", 0)
                            )
                        processes.append(row)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            samples.append(
                {"at_ms": time.time() * 1000, "phase": marker["phase"], "processes": processes}
            )
        except (OSError, ValueError, KeyError, psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        try:
            await asyncio.wait_for(done.wait(), 0.1)
        except TimeoutError:
            pass
    return samples


async def stop(process):
    if process is None or process.returncode is not None:
        return
    # Only the explicitly created process and its descendants belong here.
    try:
        children = psutil.Process(process.pid).children(recursive=True)
    except psutil.NoSuchProcess:
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
        except psutil.NoSuchProcess:
            pass


REVIEW_CHECKS = (
    "disclosure_required",
    "setup_disclosure_deferred_without_permission",
    "manual_choice_before_permission",
    "app_disclosure_acknowledged",
    "exact_review_preserved",
    "native_optout_invalidates_review",
    "reenable_starts_empty",
    "discard_does_not_spend",
    "approved_attempt_uses_inspected_body",
    "optout_and_review_survive_restart",
)


async def run(
    source, output, playwright, *, attribution=False, comparison=False, review_journey=False
):
    if sum((attribution, comparison, review_journey)) > 1:
        raise ValueError("Choose comparison, allocation attribution or review as separate journeys")
    if review_journey and sys.platform != "linux":
        raise ValueError("The review journey is a separate Linux source-app check")
    output.mkdir(mode=0o700)
    executable = {
        "win32": "electron.exe",
        "darwin": "Electron.app/Contents/MacOS/Electron",
    }.get(sys.platform, "electron")
    electron = source / "studio/electron/node_modules/electron/dist" / executable
    if not electron.is_file():
        raise RuntimeError("Install the pinned Electron executable before starting this diagnostic")
    original = (source / "mnemion/product_telemetry/disclosure.json").read_bytes()
    assert not json.loads(original)["collection_available"]
    assert not policy.COLLECTION_AVAILABLE and policy.COLLECTOR_URL is None
    saved_policy = policy.COLLECTION_AVAILABLE, policy.COLLECTOR_URL
    counts = {"reports": 0, "accepted": 0, "body_bytes": 0, "forbidden_metadata": 0}
    reviewed_bodies = []
    published = []
    collector = Collector(published.append)

    async def ingress(scope, receive, send):
        reviewed_body = bytearray()
        is_report = scope.get("type") == "http" and scope.get("method") == "POST"
        if scope["type"] == "http":
            counts["reports"] += int(scope.get("method") == "POST")
            counts["forbidden_metadata"] += bool(
                {name for name, _ in scope.get("headers", [])}
                & {b"cookie", b"authorization", b"referer", b"user-agent"}
            )

        async def received():
            event = await receive()
            if event["type"] == "http.request":
                counts["body_bytes"] += len(event.get("body", b""))
                if review_journey and len(reviewed_body) + len(event.get("body", b"")) <= 4:
                    reviewed_body.extend(event.get("body", b""))
            return event

        async def sending(event):
            if event["type"] == "http.response.start" and event["status"] == 204:
                counts["accepted"] += 1
            await send(event)

        await collector(scope, received, sending)
        if review_journey and is_report and len(reviewed_bodies) < 8:
            # Only the disposable fixture's four-byte packet; no real user data.
            reviewed_bodies.append(reviewed_body.hex())

    results, roots = [], []
    task = None
    tls_root = None
    try:
        with tempfile.TemporaryDirectory(prefix="mnemion-owned-renderer-tls-") as temporary:
            tls_root = Path(temporary)

            class Factory:
                def mktemp(self, _name):
                    return tls_root

            certificate, context = certificates.__wrapped__(Factory())
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(8)
                destination = f"https://localhost:{listener.getsockname()[1]}/v1/report"
                config = uvicorn.Config(
                    ingress,
                    log_config=None,
                    access_log=False,
                    server_header=False,
                    date_header=False,
                    timeout_keep_alive=0,
                    ssl_certfile=str(certificate),
                    ssl_keyfile=str(tls_root / "key.pem"),
                )
                config.load()
                config.ssl = context
                server = uvicorn.Server(config)
                task = asyncio.create_task(server.serve(sockets=[listener]))
                try:
                    async with asyncio.timeout(20):
                        while not server.started:
                            if task.done():
                                await task
                                raise RuntimeError("Owned TLS collector did not start")
                            await asyncio.sleep(0.01)
                    triplet = [
                        ("unavailable", False, False),
                        ("opted_out", True, False),
                        ("enabled", True, True),
                    ]
                    cases = [
                        (label, label, available, enabled, 1)
                        for label, available, enabled in triplet
                    ]
                    if review_journey:
                        cases = [("review", "review", True, True, 1)]
                    if attribution or comparison:
                        # Fixed before measurement. Never add another launch to
                        # select a favorable outcome from unchanged source.
                        cases = [
                            (f"r{replicate}-{label}", label, available, enabled, replicate)
                            for replicate, order in [(1, triplet), (2, list(reversed(triplet)))]
                            for label, available, enabled in order
                        ]
                    for label, condition, available, enabled, replicate in cases:
                        before = dict(counts)
                        with tempfile.TemporaryDirectory(
                            prefix="mnemion-owned-renderer-"
                        ) as fixture:
                            root = Path(fixture)
                            roots.append(root)
                            copy = root / "source"
                            hashes = copy_source(source, copy)
                            write_json(output / f"{label}-inputs.json", hashes)
                            contract = json.loads(original)
                            contract.update(
                                collection_available=available,
                                destination=destination if available else None,
                            )
                            write_json(copy / "mnemion/product_telemetry/disclosure.json", contract)
                            write_json(
                                copy / "studio/electron/dist/telemetry-disclosure.json", contract
                            )
                            fixture_route = {
                                "version": 2,
                                "address": "127.0.0.1" if available else None,
                                "certificate_authorities": [certificate.read_text()]
                                if available
                                else [],
                            }
                            write_json(
                                copy / "studio/electron/dist/telemetry-transport-route.json",
                                fixture_route,
                            )
                            write_json(
                                copy / "mnemion/product_telemetry/transport-route.json",
                                fixture_route,
                            )
                            app = copy / "studio/electron"
                            manifest = json.loads((app / "package.json").read_text())
                            manifest["main"] = "probe-telemetry-renderer.mjs"
                            write_json(app / "package.json", manifest)
                            shutil.copyfile(
                                source / "studio/electron/scripts/probe-telemetry-renderer.mjs",
                                app / "probe-telemetry-renderer.mjs",
                            )
                            engine = root / "absent-engine"
                            if review_journey:
                                shutil.copyfile(
                                    source / "studio/electron/scripts/probe-telemetry-review.mjs",
                                    app / "probe-telemetry-review.mjs",
                                )
                                if any(character.isspace() for character in sys.executable):
                                    raise ValueError("Use an interpreter path without whitespace")
                                # Use the real source CLI behind the normal private-stdin
                                # bridge. The installed engine is not replaced or qualified.
                                engine = root / "source-engine"
                                engine.write_text(
                                    f"#!{sys.executable}\nimport sys\n"
                                    f"sys.path.insert(0, {str(copy)!r})\n"
                                    "from mnemion.service.cli import main\n"
                                    "raise SystemExit(main())\n"
                                )
                                engine.chmod(0o700)
                            else:
                                policy.COLLECTION_AVAILABLE, policy.COLLECTOR_URL = (
                                    True,
                                    destination,
                                )
                                configured = policy.configure(
                                    root / "mnemion-product-telemetry",
                                    {
                                        "enabled": enabled,
                                        "expected_revision": 0,
                                        "disclosure_version": 1,
                                        "connection_mode": "unmetered",
                                    },
                                    policy_path=root / "company-absent.json",
                                )
                                assert configured["effective_enabled"] is enabled
                                policy.COLLECTION_AVAILABLE, policy.COLLECTOR_URL = saved_policy
                            async with memory_workspace(root) as (memory, memory_counts):
                                with socket.socket() as selection:
                                    selection.bind(("127.0.0.1", 0))
                                    port = selection.getsockname()[1]
                                environment = {
                                    key: value
                                    for key, value in os.environ.items()
                                    if not key.startswith("MNEMION_")
                                }
                                environment.pop("ELECTRON_RUN_AS_NODE", None)
                                environment.update(
                                    PYTHONPATH=str(source),
                                    MNEMION_BUILD_PYTHON=sys.executable,
                                    MNEMION_STUDIO_USER_DATA=str(root),
                                    MNEMION_STUDIO_DEVTOOLS="0",
                                    MNEMION_LEGACY_STUDIO="0",
                                    MNEMION_AUTO_UPDATE="0",
                                    MNEMION_START_AT_LOGIN="0",
                                    MNEMION_LOCAL_ENGINE=str(engine),
                                    MNEMION_LOCAL_DATABASE=str(root / "absent-database"),
                                    MNEMION_COST_RESULT=str(output / f"{label}.json"),
                                    MNEMION_PROBE_ARTIFACTS=str(output),
                                    MNEMION_PROBE_PLAYWRIGHT=str(playwright),
                                    MNEMION_PROBE_ELECTRON=str(electron),
                                    VITE_DEV_PORT=str(port),
                                )
                                builder = frontend = process = None
                                done = asyncio.Event()
                                observer = asyncio.create_task(
                                    observe_tree(root, done, attribution=attribution)
                                )
                                try:
                                    build_receipt = output / f"{label}-frontend-build.json"
                                    with (output / f"{label}-frontend-build.log").open("x") as log:
                                        builder = await asyncio.create_subprocess_exec(
                                            "node",
                                            str(
                                                copy
                                                / "studio/frontend/scripts/build-telemetry-probe.mjs"
                                            ),
                                            str(build_receipt),
                                            cwd=copy / "studio/frontend",
                                            env=environment,
                                            stdout=log,
                                            stderr=asyncio.subprocess.STDOUT,
                                        )
                                        await asyncio.wait_for(builder.wait(), 90)
                                        if builder.returncode:
                                            raise RuntimeError(
                                                f"Inspect retained {label}-frontend-build.log"
                                            )
                                    compiled = json.loads(build_receipt.read_text())
                                    write_json(
                                        root / "probe-input.json",
                                        {
                                            "variant": label,
                                            "condition": condition,
                                            "replicate": replicate,
                                            "attribution": attribution,
                                            "comparison": comparison,
                                            "review_journey": review_journey,
                                            "memory": memory,
                                            "destination": destination,
                                            "probe_entry": compiled["probe_entry"],
                                        },
                                    )
                                    (root / "probe-input.json").chmod(0o600)
                                    # No development compiler remains resident during the
                                    # workload. Serve only the compiled disposable assets.
                                    with (output / f"{label}-frontend.log").open("x") as log:
                                        frontend = await asyncio.create_subprocess_exec(
                                            sys.executable,
                                            "-m",
                                            "http.server",
                                            str(port),
                                            "--bind",
                                            "127.0.0.1",
                                            "--directory",
                                            str(copy / "studio/frontend/dist-probe"),
                                            cwd=copy / "studio/frontend",
                                            env=environment,
                                            stdout=log,
                                            stderr=asyncio.subprocess.STDOUT,
                                        )
                                        async with asyncio.timeout(30):
                                            while True:
                                                if frontend.returncode is not None:
                                                    raise RuntimeError(
                                                        "Owned frontend exited before readiness"
                                                    )
                                                try:
                                                    _, writer = await asyncio.open_connection(
                                                        "127.0.0.1", port
                                                    )
                                                    writer.close()
                                                    await writer.wait_closed()
                                                    break
                                                except OSError:
                                                    await asyncio.sleep(0.05)
                                        with (output / f"{label}.log").open("x") as app_log:
                                            process = await asyncio.create_subprocess_exec(
                                                "node",
                                                str(app / "probe-telemetry-renderer.mjs"),
                                                cwd=app,
                                                env=environment,
                                                stdout=app_log,
                                                stderr=asyncio.subprocess.STDOUT,
                                            )
                                            await asyncio.wait_for(process.wait(), 240)
                                            if process.returncode:
                                                raise RuntimeError(
                                                    f"Inspect retained {label}.log; fixture failed"
                                                )
                                finally:
                                    await stop(process)
                                    await stop(frontend)
                                    await stop(builder)
                                    done.set()
                                    samples = await observer
                                    write_json(output / f"{label}-processes.json", samples)
                                result = json.loads((output / f"{label}.json").read_text())
                                result["frontend"] = compiled["frontend"]
                                result["shared_app_policy_and_client_modules"] = compiled[
                                    "shared_app_policy_and_client_modules"
                                ]
                                result["collector"] = {
                                    key: counts[key] - before[key] for key in counts
                                }
                                result["memory_api"] = dict(memory_counts)
                                database_file = (
                                    root / "mnemion-product-telemetry" / policy.DATABASE_NAME
                                )
                                with closing(sqlite3.connect(database_file)) as database:
                                    result["durable"] = {
                                        "attempts": database.execute(
                                            "SELECT count(*),coalesce(sum(reserved_bytes),0) FROM delivery_attempts"
                                        ).fetchone(),
                                        "lease_cleared": database.execute(
                                            "SELECT lease_token IS NULL FROM delivery_state"
                                        ).fetchone()[0]
                                        == 1,
                                        "queue_cells": database.execute(
                                            "SELECT count(*) FROM pending"
                                        ).fetchone()[0],
                                        "database_bytes": database_file.stat().st_size,
                                        "maximum_producer_count": database.execute(
                                            "SELECT coalesce(max(count),0) FROM producer_budget"
                                        ).fetchone()[0],
                                    }
                                raw = database_file.read_bytes()
                                result["fixture_content_absent_from_queue"] = (
                                    b"PRIVATE_RENDERER_MEMORY_CANARY" not in raw
                                    and memory["api_key"].encode() not in raw
                                )
                                if review_journey:
                                    result["collector_body_matches_inspection"] = (
                                        reviewed_bodies == [result.get("approved_body_hex")]
                                    )
                                result["journey_completed"] = (
                                    result["memory_results_verified"]
                                    and result["memory_api"]["successful"]
                                    >= (9 if review_journey else 384)
                                    and result["fixture_content_absent_from_queue"]
                                    and result["collector"]
                                    == {
                                        "reports": int(enabled),
                                        "accepted": int(enabled),
                                        "body_bytes": 4 * int(enabled),
                                        "forbidden_metadata": 0,
                                    }
                                    and result["durable"]["attempts"]
                                    == (int(enabled), 65536 * int(enabled))
                                    and result["durable"]["lease_cleared"]
                                    and not result["page_errors"]
                                    and not result.get("allocation", {}).get("errors")
                                    and (
                                        review_journey
                                        or (
                                            result.get("process_ownership_verified") is True
                                            and result.get("devtools_auto_open") is False
                                            and all(
                                                sample.get("ownership", {}).get("valid") is True
                                                for sample in result["samples"]
                                            )
                                            and len(result["samples"])
                                            == (9 if attribution or comparison else 5)
                                        )
                                    )
                                    and (
                                        not review_journey
                                        or (
                                            result["collector_body_matches_inspection"]
                                            and all(
                                                result.get("review_checks", {}).get(name) is True
                                                for name in REVIEW_CHECKS
                                            )
                                            and result.get("app_launches") == 2
                                        )
                                    )
                                )
                        result["isolated_profile_removed"] = not root.exists()
                        results.append(result)
                        write_json(output / f"{label}-result.json", result)
                        print(
                            json.dumps(
                                {
                                    "variant": label,
                                    "journey_completed": result["journey_completed"],
                                    "collector": result["collector"],
                                    "memory_api": result["memory_api"],
                                }
                            ),
                            flush=True,
                        )
                finally:
                    server.should_exit = True
                    await task
    finally:
        policy.COLLECTION_AVAILABLE, policy.COLLECTOR_URL = saved_policy
        write_json(
            output / "cleanup.json",
            {
                "isolated_profiles_removed": all(not root.exists() for root in roots),
                "collector_stopped": task is None or task.done(),
                "certificate_profile_removed": tls_root is None or not tls_root.exists(),
                "production_disclosure_unchanged": (
                    source / "mnemion/product_telemetry/disclosure.json"
                ).read_bytes()
                == original,
            },
        )
    write_json(
        output / "receipt.json",
        {
            "schema_version": 1,
            "at": datetime.now(timezone.utc).isoformat(),
            "results": results,
            "production_collection_available": False,
            "published_aggregate_count": len(published),
            "sampling_interval_ms": 100,
            "resource_acceptance": False,
            "attribution": attribution,
            "comparison": comparison,
            "review_journey": review_journey,
            "declared_case_order": [row[0] for row in cases],
            "resource_limits": "Observed RSS sums double-count shared pages. Short-lived helpers between samples can be missed; CPU totals are sampled lower bounds. The declared runs are descriptive, not stable overhead or installed-target acceptance. Attribution instruments first activation and can perturb allocations and timing; profiled CPU is not qualification.",
        },
    )
    if not all(row["journey_completed"] for row in results):
        raise SystemExit("Inspect retained observations; renderer acceptance did not pass")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--playwright-module", required=True, type=Path)
    parser.add_argument(
        "--attribution",
        action="store_true",
        help="Six fixed counterbalanced launches with bounded first-activation and OS counters",
    )
    parser.add_argument(
        "--comparison",
        action="store_true",
        help="Six fixed counterbalanced launches without first-activation attribution",
    )
    parser.add_argument(
        "--review-journey",
        action="store_true",
        help="Two Linux source-app launches for actual manual review, TLS delivery and restart",
    )
    args = parser.parse_args()
    asyncio.run(
        run(
            args.source.resolve(),
            args.output.resolve(),
            args.playwright_module.resolve(),
            attribution=args.attribution,
            comparison=args.comparison,
            review_journey=args.review_journey,
        )
    )
