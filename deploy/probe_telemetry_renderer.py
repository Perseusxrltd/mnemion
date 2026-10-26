"""Exercise telemetry in the real development renderer, bridge and memory API.

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


async def observe_tree(root, done):
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
                        processes.append(
                            {
                                "pid": child.pid,
                                "created": child.create_time(),
                                "rss": child.memory_info().rss,
                                "cpu_ms": 1000 * (cpu.user + cpu.system),
                            }
                        )
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


async def run(source, output, playwright):
    output.mkdir(mode=0o700)
    original = (source / "mnemion/product_telemetry/disclosure.json").read_bytes()
    assert not json.loads(original)["collection_available"]
    assert not policy.COLLECTION_AVAILABLE and policy.COLLECTOR_URL is None
    saved_policy = policy.COLLECTION_AVAILABLE, policy.COLLECTOR_URL
    counts = {"reports": 0, "accepted": 0, "body_bytes": 0, "forbidden_metadata": 0}
    published = []
    collector = Collector(published.append)

    async def ingress(scope, receive, send):
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
            return event

        async def sending(event):
            if event["type"] == "http.response.start" and event["status"] == 204:
                counts["accepted"] += 1
            await send(event)

        await collector(scope, received, sending)

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
                    for label, available, enabled in [
                        ("unavailable", False, False),
                        ("opted_out", True, False),
                        ("enabled", True, True),
                    ]:
                        before = dict(counts)
                        with tempfile.TemporaryDirectory(
                            prefix="mnemion-owned-renderer-"
                        ) as fixture:
                            root = Path(fixture)
                            roots.append(root)
                            copy = root / "source"
                            hashes = copy_source(source, copy)
                            write_json(output / f"{label}-inputs.json", hashes)
                            (copy / "studio/frontend/src/owned-memory-probe.ts").write_text(
                                "export { MnemionClient } from '@mnemion/client';\n"
                                "export { measuredStudioClient } from './workspace/measured-client';\n"
                                "export { nativeFetch } from './workspace/native';\n"
                            )
                            contract = json.loads(original)
                            contract.update(
                                collection_available=available,
                                destination=destination if available else None,
                            )
                            write_json(copy / "mnemion/product_telemetry/disclosure.json", contract)
                            write_json(
                                copy / "studio/electron/dist/telemetry-disclosure.json", contract
                            )
                            write_json(
                                copy / "studio/electron/dist/telemetry-transport-route.json",
                                {"version": 1, "address": "127.0.0.1" if available else None},
                            )
                            app = copy / "studio/electron"
                            manifest = json.loads((app / "package.json").read_text())
                            manifest["main"] = "probe-telemetry-renderer.mjs"
                            write_json(app / "package.json", manifest)
                            shutil.copyfile(
                                source / "studio/electron/scripts/probe-telemetry-renderer.mjs",
                                app / "probe-telemetry-renderer.mjs",
                            )
                            policy.COLLECTION_AVAILABLE, policy.COLLECTOR_URL = True, destination
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
                                write_json(
                                    root / "probe-input.json",
                                    {
                                        "variant": label,
                                        "memory": memory,
                                        "destination": destination,
                                    },
                                )
                                (root / "probe-input.json").chmod(0o600)
                                with socket.socket() as selection:
                                    selection.bind(("127.0.0.1", 0))
                                    port = selection.getsockname()[1]
                                environment = {
                                    key: value
                                    for key, value in os.environ.items()
                                    if not key.startswith("MNEMION_")
                                }
                                environment.pop("ELECTRON_RUN_AS_NODE", None)
                                executable = {
                                    "win32": "electron.exe",
                                    "darwin": "Electron.app/Contents/MacOS/Electron",
                                }.get(sys.platform, "electron")
                                environment.update(
                                    PYTHONPATH=str(source),
                                    MNEMION_BUILD_PYTHON=sys.executable,
                                    MNEMION_STUDIO_USER_DATA=str(root),
                                    MNEMION_LEGACY_STUDIO="0",
                                    MNEMION_AUTO_UPDATE="0",
                                    MNEMION_START_AT_LOGIN="0",
                                    MNEMION_LOCAL_ENGINE=str(root / "absent-engine"),
                                    MNEMION_LOCAL_DATABASE=str(root / "absent-database"),
                                    MNEMION_COST_RESULT=str(output / f"{label}.json"),
                                    MNEMION_PROBE_ARTIFACTS=str(output),
                                    MNEMION_PROBE_PLAYWRIGHT=str(playwright),
                                    MNEMION_PROBE_ELECTRON=str(
                                        source
                                        / "studio/electron/node_modules/electron/dist"
                                        / executable
                                    ),
                                    VITE_DEV_PORT=str(port),
                                    NODE_EXTRA_CA_CERTS=str(certificate),
                                )
                                vite = process = None
                                done = asyncio.Event()
                                observer = asyncio.create_task(observe_tree(root, done))
                                try:
                                    with (output / f"{label}-vite.log").open("x") as log:
                                        vite = await asyncio.create_subprocess_exec(
                                            "node",
                                            str(
                                                copy
                                                / "studio/frontend/node_modules/vite/bin/vite.js"
                                            ),
                                            "--host",
                                            "127.0.0.1",
                                            "--port",
                                            str(port),
                                            "--strictPort",
                                            cwd=copy / "studio/frontend",
                                            env=environment,
                                            stdout=log,
                                            stderr=asyncio.subprocess.STDOUT,
                                        )
                                        async with asyncio.timeout(30):
                                            while True:
                                                if vite.returncode is not None:
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
                                    await stop(vite)
                                    done.set()
                                    samples = await observer
                                    write_json(output / f"{label}-processes.json", samples)
                                result = json.loads((output / f"{label}.json").read_text())
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
                                    }
                                raw = database_file.read_bytes()
                                result["fixture_content_absent_from_queue"] = (
                                    b"PRIVATE_RENDERER_MEMORY_CANARY" not in raw
                                    and memory["api_key"].encode() not in raw
                                )
                                result["journey_completed"] = (
                                    result["memory_results_verified"]
                                    and result["memory_api"]["successful"] >= 384
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
            "resource_limits": "Observed RSS sums double-count shared pages. Short-lived helpers between samples can be missed; CPU totals are sampled lower bounds. Three sequential runs are descriptive, not stable overhead or installed-target acceptance.",
        },
    )
    if not all(row["journey_completed"] for row in results):
        raise SystemExit("Inspect retained observations; renderer acceptance did not pass")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--playwright-module", required=True, type=Path)
    args = parser.parse_args()
    asyncio.run(run(args.source.resolve(), args.output.resolve(), args.playwright_module.resolve()))
