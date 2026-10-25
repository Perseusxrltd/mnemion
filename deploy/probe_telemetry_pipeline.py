"""Measure an isolated desktop telemetry pipeline, not installed/full-app acceptance.

Run from a reviewed source checkout with dev dependencies and an existing
Electron build. No production profile, collector, certificate trust or source
disclosure is changed. Output must name a new directory. The synthetic producer
burst is deliberately not labelled a representative memory-work CPU benchmark.
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
import sys
import tempfile

import uvicorn

from mnemion.product_telemetry import policy
from mnemion.product_telemetry.collector import Collector
from mnemion.version import __version__
from tests.test_product_telemetry_transport import certificates


async def run(source, output):
    output.mkdir(mode=0o700)
    client_file = source / "studio/electron/scripts/probe-telemetry-pipeline.mjs"
    shutil.copyfile(Path(__file__), output / Path(__file__).name)
    shutil.copyfile(client_file, output / client_file.name)
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

    results = []
    saved = policy.COLLECTION_AVAILABLE, policy.COLLECTOR_URL
    try:
        with tempfile.TemporaryDirectory(prefix="mnemion-owned-pipeline-tls-") as tls_temporary:
            tls_root = Path(tls_temporary)

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
                                    "enabled": enabled,
                                    "available": available,
                                    "variant": label,
                                }
                            )
                        )
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
                                "NODE_EXTRA_CA_CERTS": str(certificate),
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
                                await asyncio.wait_for(process.wait(), 45)
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
                        result["journey_completed"] = (
                            result["collector"]["reports"] == int(enabled)
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
    assert disclosure_file.read_bytes() == production
    receipt = {
        "schema_version": 1,
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
    args = parser.parse_args()
    asyncio.run(run(args.source.resolve(), args.output.resolve()))
