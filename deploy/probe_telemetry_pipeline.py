"""Measure an isolated desktop telemetry pipeline, not installed/full-app acceptance.

Run from a reviewed source checkout with dev dependencies and an existing
Electron build. --memory-workload also requires the built client SDK and pgserver.
No production profile, collector, certificate trust or source
disclosure is changed. Output must name a new directory. The synthetic producer
burst is deliberately not labelled a representative memory-work CPU benchmark.
The fixed real-transaction variant remains a scoped diagnostic: its UI producer
runs in the main process and does not exercise a renderer or installed platform.
"""

import argparse
import asyncio
from contextlib import AsyncExitStack, closing
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

import uvicorn

from mnemion.product_telemetry import policy
from mnemion.product_telemetry.collector import Collector
from mnemion.version import __version__
from tests.test_product_telemetry_transport import certificates


async def run(source, output, *, memory_workload=False):
    output.mkdir(mode=0o700)
    client_file = source / "studio/electron/scripts/probe-telemetry-pipeline.mjs"
    shutil.copyfile(Path(__file__), output / Path(__file__).name)
    shutil.copyfile(client_file, output / client_file.name)
    if memory_workload:
        from .telemetry_memory_fixture import memory_workspace

        for path in [
            source / "deploy/telemetry_memory_fixture.py",
            source / "studio/electron/scripts/prepare-telemetry-memory.mjs",
        ]:
            shutil.copyfile(path, output / path.name)
    inputs = {}
    for folder in [source / "mnemion/product_telemetry", source / "studio/electron"]:
        paths = folder.rglob("*") if folder.name == "product_telemetry" else folder.glob("*.ts")
        for path in paths:
            if path.is_file() and path.suffix in {".py", ".json", ".c", ".h", ".ts"}:
                inputs[path.relative_to(source).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    for path in (source / "studio/electron/dist").glob("*"):
        if path.is_file() and path.suffix in {".js", ".json", ".node", ".exe"}:
            inputs[path.relative_to(source).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    if memory_workload:
        for path in [
            *sorted((source / "packages/client/src").glob("*.ts")),
            *sorted((source / "packages/client/dist").glob("*.js")),
            *sorted((source / "mnemion/service").rglob("*.py")),
            *sorted((source / "mnemion/service").rglob("*.sql")),
            source / "studio/frontend/src/workspace/measured-client.ts",
            source / "deploy/telemetry_memory_fixture.py",
            source / "studio/electron/scripts/prepare-telemetry-memory.mjs",
            source / "service_tests/conftest.py",
        ]:
            inputs[path.relative_to(source).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    (output / "inputs.json").write_text(json.dumps(inputs, sort_keys=True, indent=2) + "\n")
    disclosure_file = source / "mnemion/product_telemetry/disclosure.json"
    production = disclosure_file.read_bytes()
    assert json.loads(production)["collection_available"] is False
    assert policy.COLLECTION_AVAILABLE is False and policy.COLLECTOR_URL is None
    counts = {"reports": 0, "accepted": 0, "options": 0, "body_bytes": 0, "forbidden_metadata": 0}
    published = []
    collector = Collector(published.append)

    async def ingress(scope, receive, send):
        if scope["type"] != "http":
            return await collector(scope, receive, send)
        method = scope.get("method")
        if method == "OPTIONS":
            counts["options"] += 1
        if method == "POST":
            counts["reports"] += 1
            names = {name for name, _ in scope.get("headers", [])}
            counts["forbidden_metadata"] += bool(
                names & {b"cookie", b"authorization", b"referer", b"user-agent"}
            )

        async def received():
            event = await receive()
            if method == "POST" and event["type"] == "http.request":
                counts["body_bytes"] += len(event.get("body", b""))
            return event

        async def sending(event):
            if (
                method == "POST"
                and event["type"] == "http.response.start"
                and event["status"] == 204
            ):
                counts["accepted"] += 1
            await send(event)

        await collector(scope, received, sending)

    results, isolated_roots = [], []
    task, tls_root = None, None
    saved = policy.COLLECTION_AVAILABLE, policy.COLLECTOR_URL
    try:
        with tempfile.TemporaryDirectory(prefix="mnemion-owned-pipeline-tls-") as tls_temporary:
            tls_root = Path(tls_temporary)
            prepared_client = tls_root / "measured-studio-fixture.mjs"
            if memory_workload:
                subprocess.run(
                    [
                        "node",
                        str(source / "studio/electron/scripts/prepare-telemetry-memory.mjs"),
                        str(prepared_client),
                    ],
                    check=True,
                    timeout=30,
                    capture_output=True,
                )
                subprocess.run(
                    ["node", "--check", str(prepared_client)],
                    check=True,
                    timeout=10,
                    capture_output=True,
                )
                shutil.copyfile(prepared_client, output / prepared_client.name)

            class Factory:
                def mktemp(self, _name):
                    return tls_root

            certificate, context = certificates.__wrapped__(Factory())
            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            listener.listen(8)
            port = listener.getsockname()[1]
            destination = f"https://localhost:{port}/v1/report"
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
                while not server.started:
                    if task.done():
                        await task
                    await asyncio.sleep(0.01)
                for label, enabled, available in [
                    ("unavailable", False, False),
                    ("opted_out", False, True),
                    ("enabled", True, True),
                ]:
                    before = dict(counts)
                    with tempfile.TemporaryDirectory(prefix="mnemion-owned-pipeline-") as temporary:
                        root = Path(temporary)
                        isolated_roots.append(root)
                        async with AsyncExitStack() as fixtures:
                            memory_input, memory_counts = None, None
                            if memory_workload:
                                memory_input, memory_counts = await fixtures.enter_async_context(
                                    memory_workspace(root)
                                )
                            policy.COLLECTION_AVAILABLE = True
                            policy.COLLECTOR_URL = destination
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
                            policy.COLLECTION_AVAILABLE, policy.COLLECTOR_URL = saved
                            (root / "probe-input.json").write_text(
                                json.dumps(
                                    {
                                        "destination": destination,
                                        "certificate_authorities": [certificate.read_text()],
                                        "enabled": enabled,
                                        "available": available,
                                        "variant": label,
                                        "memory": memory_input,
                                    }
                                )
                            )
                            (root / "probe-input.json").chmod(0o600)
                            application = root / "app"
                            application.mkdir()
                            shutil.copytree(
                                source / "studio/bridge",
                                root / "bridge",
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                            )
                            (application / "package.json").write_text(
                                json.dumps(
                                    {
                                        "name": "mnemion-resource-fixture",
                                        "version": __version__,
                                        "type": "module",
                                        "main": "probe.mjs",
                                    }
                                )
                            )
                            shutil.copyfile(client_file, application / "probe.mjs")
                            if memory_workload:
                                shutil.copyfile(prepared_client, application / prepared_client.name)
                            environment = dict(os.environ)
                            environment.pop("ELECTRON_RUN_AS_NODE", None)
                            environment.update(
                                {
                                    "PYTHONPATH": str(source),
                                    "MNEMION_BUILD_PYTHON": sys.executable,
                                    "MNEMION_PROBE_SOURCE": str(source),
                                    "MNEMION_STUDIO_USER_DATA": str(root),
                                    "MNEMION_STUDIO_SMOKE_HEADLESS": "1",
                                    "MNEMION_STUDIO_SMOKE_FILE": str(root / "startup.json"),
                                    "MNEMION_AUTO_UPDATE": "0",
                                    "MNEMION_START_AT_LOGIN": "0",
                                    "MNEMION_LEGACY_STUDIO": "0",
                                    "MNEMION_LOCAL_ENGINE": str(root / "absent-engine"),
                                    "MNEMION_LOCAL_DATABASE": str(root / "absent-database"),
                                    "MNEMION_COST_RESULT": str(output / f"{label}.json"),
                                }
                            )
                            with (output / f"{label}.log").open("x") as log:
                                executable = {
                                    "win32": "electron.exe",
                                    "darwin": "Electron.app/Contents/MacOS/Electron",
                                }.get(sys.platform, "electron")
                                process = await asyncio.create_subprocess_exec(
                                    str(
                                        source
                                        / "studio/electron/node_modules/electron/dist"
                                        / executable
                                    ),
                                    str(application),
                                    cwd=application,
                                    env=environment,
                                    stdout=log,
                                    stderr=asyncio.subprocess.STDOUT,
                                )
                                try:
                                    await asyncio.wait_for(
                                        process.wait(), 180 if memory_workload else 45
                                    )
                                finally:
                                    if process.returncode is None:
                                        process.kill()
                                        await process.wait()
                            if process.returncode:
                                raise RuntimeError(
                                    f"Inspect {label} original log; no installed profile was changed"
                                )
                            result = json.loads((output / f"{label}.json").read_text())
                            result["collector"] = {key: counts[key] - before[key] for key in counts}
                            with closing(
                                sqlite3.connect(
                                    root / "mnemion-product-telemetry" / policy.DATABASE_NAME
                                )
                            ) as database:
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
                                    "database_bytes": (
                                        root / "mnemion-product-telemetry" / policy.DATABASE_NAME
                                    )
                                    .stat()
                                    .st_size,
                                }
                            if memory_counts is not None:
                                result["memory_api"] = dict(memory_counts)
                                queue_bytes = (
                                    root / "mnemion-product-telemetry" / policy.DATABASE_NAME
                                ).read_bytes()
                                result["fixture_content_absent_from_queue"] = (
                                    b"PRIVATE_MEMORY_CANARY" not in queue_bytes
                                    and memory_input["api_key"].encode() not in queue_bytes
                                )
                            result["journey_completed"] = (
                                (
                                    memory_counts is None
                                    or memory_counts == {"requests": 384, "successful": 384}
                                )
                                and result.get("memory_results_verified", not memory_workload)
                                and result.get("fixture_content_absent_from_queue", True)
                                and result["collector"]["reports"] == int(enabled)
                                and result["collector"]["accepted"] == int(enabled)
                                and result["collector"]["body_bytes"] == 4 * int(enabled)
                                and result["collector"]["options"] == 0
                                and result["collector"]["forbidden_metadata"] == 0
                                and result["durable"]["attempts"]
                                == (int(enabled), 65536 * int(enabled))
                                and result["durable"]["lease_cleared"]
                            )
                    result["isolated_profile_removed"] = not root.exists()
                    results.append(result)
            finally:
                server.should_exit = True
                await task
                listener.close()
    finally:
        policy.COLLECTION_AVAILABLE, policy.COLLECTOR_URL = saved
        (output / "cleanup.json").write_text(
            json.dumps(
                {
                    "isolated_profiles_removed": all(not root.exists() for root in isolated_roots),
                    "certificate_profile_removed": tls_root is None or not tls_root.exists(),
                    "collector_stopped": task is None or task.done(),
                    "production_disclosure_unchanged": disclosure_file.read_bytes() == production,
                    "production_policy_restored": (
                        policy.COLLECTION_AVAILABLE,
                        policy.COLLECTOR_URL,
                    )
                    == saved,
                },
                indent=2,
            )
            + "\n"
        )
    assert disclosure_file.read_bytes() == production
    receipt = {
        "schema_version": 1,
        "memory_workload": memory_workload,
        "at": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "collector_closed": task.done(),
        "certificate_profile_removed": not tls_root.exists(),
        "published_aggregate_count": len(published),
        "production_collection_available": False,
        "source_disclosure_sha256": hashlib.sha256(production).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "client_sha256": hashlib.sha256(client_file.read_bytes()).hexdigest(),
        "inputs_sha256": hashlib.sha256((output / "inputs.json").read_bytes()).hexdigest(),
        "qualification": "Diagnostic; no public release, installed matrix, representative memory workload or total wire acceptance.",
    }
    if memory_workload:
        unavailable, opted_out, enabled = results
        receipt["workload_comparisons"] = [
            {
                "variant": row["variant"],
                "baseline": baseline["variant"],
                "difference_rss_growth_bytes": row["rss_delta_bytes"] - baseline["rss_delta_bytes"],
                "difference_sampled_peak_growth_bytes": row["sampled_peak_rss_delta_bytes"]
                - baseline["sampled_peak_rss_delta_bytes"],
                "difference_cpu_ms": row["cpu_ms"] - baseline["cpu_ms"],
                "cpu_difference_percent_one_core_over_baseline_elapsed": 100
                * (row["cpu_ms"] - baseline["cpu_ms"])
                / baseline["elapsed_ms"],
            }
            for row, baseline in [
                (opted_out, unavailable),
                (enabled, unavailable),
                (enabled, opted_out),
            ]
        ]
        receipt["prepared_client_sha256"] = hashlib.sha256(
            (output / "measured-studio-fixture.mjs").read_bytes()
        ).hexdigest()
        receipt["qualification"] = (
            "One fixed real-memory comparison on Linux development Electron main process; "
            "includes cold first-operation costs in all variants. No idle padding or forced GC. "
            "Descriptive differences are not stable acceptance estimates: no renderer/IPC, "
            "Chromium network-service RSS, installed matrix, full wire or embedding-quality proof."
        )
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                "observations": [
                    {
                        name: row[name]
                        for name in [
                            "variant",
                            "rss_delta_bytes",
                            "cpu_ms",
                            "elapsed_ms",
                            "accepted_writes",
                            "reserved_attempts",
                            "collector",
                            "durable",
                            "journey_completed",
                        ]
                    }
                    for row in results
                ]
            }
        )
    )
    if not all(row["journey_completed"] for row in results):
        raise SystemExit(
            "The receipt retains the actual refusal/failure. Inspect it before claiming pipeline acceptance."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--memory-workload",
        action="store_true",
        help="Use 128 fixed real save/fetch/lexical-recall cycles with a disposable PostgreSQL API. Requires built client SDK and pgserver.",
    )
    args = parser.parse_args()
    asyncio.run(
        run(args.source.resolve(), args.output.resolve(), memory_workload=args.memory_workload)
    )
