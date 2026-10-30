"""Build one unpublished diagnostic package and run the installed delivery journey.

The package is a copy of this source with loopback disclosure and route baked
before the normal client, frontend and native-engine build. Production files
and release feeds are not changed. This does not claim the journey passed.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile


from deploy.telemetry_installed_fixture import UPDATE_FEEDS, write_bake


def read_delivery_store(profile: Path, secret: bytes) -> dict:
    database = profile / "mnemion-product-telemetry" / "product-telemetry.sqlite3"
    if not database.is_file() or not secret or len(secret) > 256:
        raise ValueError("The packaged telemetry database or fixture secret is unusable")
    raw = database.read_bytes()
    with closing(sqlite3.connect(database)) as connection:
        attempts = connection.execute(
            "SELECT count(*), coalesce(sum(reserved_bytes), 0) FROM delivery_attempts"
        ).fetchone()
        lease = connection.execute("SELECT lease_token IS NULL FROM delivery_state").fetchone()
        pending = connection.execute("SELECT count(*) FROM pending").fetchone()
    if attempts is None or lease is None or pending is None:
        raise ValueError("The packaged telemetry database has no delivery record")
    return {
        "attempts": [attempts[0], attempts[1]],
        "lease_cleared": lease[0] == 1,
        "queue_cells": pending[0],
        "fixture_content_absent": b"PRIVATE_RENDERER_MEMORY_CANARY" not in raw and secret not in raw,
    }


def _link(target: Path, link: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        subprocess.run(
            [os.path.join(os.environ["SystemRoot"], "System32", "cmd.exe"), "/d", "/c", "mklink", "/J", str(link), str(target)],
            check=True,
        )
        return
    link.symlink_to(target, target_is_directory=True)


def copy_declared_source(source: Path, destination: Path) -> None:
    names = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=source
    ).decode().split("\0")
    for name in sorted(set(names) - {""}):
        path = source / name
        if not path.is_file() or path.is_symlink():
            continue
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    for relative in ("studio/electron/node_modules", "studio/frontend/node_modules", "packages/client/node_modules"):
        modules = source / relative
        if not modules.is_dir():
            raise RuntimeError("Install the locked desktop dependencies before the diagnostic package build")
        _link(modules, destination / relative)


def _interpreter(source: Path, *parts: str) -> Path | None:
    candidate = source.joinpath(*parts)
    return candidate if candidate.is_file() else None


def _build_env(source: Path) -> dict[str, str]:
    blocked = {
        "MNEMION_ENGINE_ARCHIVES",
        "MNEMION_TELEMETRY_FIXTURE_KEY",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "NODE_AUTH_TOKEN",
        "CSC_LINK",
        "CSC_KEY_PASSWORD",
        "APPLE_ID",
        "APPLE_APP_SPECIFIC_PASSWORD",
        "APPLE_TEAM_ID",
    }
    environment = {key: value for key, value in os.environ.items() if key not in blocked}
    windows = os.name == "nt"
    engine = environment.get("MNEMION_ENGINE_PYTHON")
    build = environment.get("MNEMION_BUILD_PYTHON")
    if not engine:
        found = _interpreter(source, ".venv", "Scripts/python.exe" if windows else "bin/python")
        if found:
            environment["MNEMION_ENGINE_PYTHON"] = str(found)
    if not build:
        found = _interpreter(source, "studio/client/.venv", "Scripts/python.exe" if windows else "bin/python")
        if found:
            environment["MNEMION_BUILD_PYTHON"] = str(found)
    archives = environment.get("MNEMION_POSTGRES_ARCHIVES") or str(source / "build-tmp/native-postgres")
    environment["MNEMION_POSTGRES_ARCHIVES"] = archives
    return environment


def _exclude_update_feeds(package_output: Path) -> list[str]:
    removed = []
    for pattern in UPDATE_FEEDS:
        for path in package_output.glob(pattern):
            if path.is_file():
                removed.append(path.name)
                path.unlink()
    return sorted(removed)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_SCOPE = (
    "Installed fixture delivery only. Production ingress, provider privacy, "
    "resources and full V08 remain unqualified."
)


def _receipt(error: str | None = None) -> dict:
    receipt = {
        "qualification": "installed fixture delivery",
        "journey_completed": False,
        "production_collection_available": False,
        "resource_acceptance": False,
        "scope": _SCOPE,
    }
    if error:
        receipt["error"] = error
    return receipt


def _bounded_error(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    lowered = text.lower()
    if (
        len(text) > 240
        or "begin certificate" in lowered
        or "private key" in lowered
        or "api_key" in lowered
        or "PRIVATE_RENDERER_MEMORY_CANARY" in text
    ):
        return type(exc).__name__
    return text


def _write_receipt(output: Path, receipt: dict) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


def _preserve_build_notes(copy: Path, output: Path) -> None:
    notes = copy / "build-tmp"
    if not notes.is_dir():
        return
    destination = output / "build-notes"
    destination.mkdir(parents=True, exist_ok=True)
    for path in notes.iterdir():
        if not path.is_file() or path.suffix not in {".json", ".log", ".txt"}:
            continue
        if path.stat().st_size > 1_000_000:
            continue
        shutil.copy2(path, destination / path.name)


def _run_logged(command: list[str], cwd: Path, env: dict[str, str], log_path: Path) -> subprocess.CompletedProcess:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as stream:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert process.stdout is not None
        for chunk in iter(lambda: process.stdout.read(8192), b""):
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
            stream.write(chunk)
        return subprocess.CompletedProcess(command, process.wait())


async def _serve(copy: Path, output: Path, source: Path) -> dict:
    from tests.test_product_telemetry_transport import _certificates
    from mnemion.product_telemetry.collector_v3 import CollectorV3
    from mnemion.product_telemetry.wire_v3 import PACKET_BYTES
    from deploy.report_telemetry_renderer import absorb_reviewed_chunk, retain_reviewed_packet
    from deploy.telemetry_memory_fixture import memory_workspace
    import uvicorn

    published = []
    counts = {"reports": 0, "accepted": 0, "body_bytes": 0, "forbidden_metadata": 0}
    reviewed = []

    async def ingress(scope, receive, send):
        captured = bytearray()
        chunks = 0
        report = scope.get("type") == "http" and scope.get("method") == "POST"
        if report:
            counts["reports"] += 1
            counts["forbidden_metadata"] += bool(
                {name for name, _ in scope.get("headers", [])} & {b"cookie", b"authorization", b"referer", b"user-agent"}
            )

        async def received():
            nonlocal captured, chunks
            event = await receive()
            if report and event["type"] == "http.request":
                chunk = event.get("body", b"")
                if type(chunk) is bytes:
                    counts["body_bytes"] += len(chunk)
                    captured, chunks = absorb_reviewed_chunk(captured, chunks, chunk)
            return event

        async def sending(event):
            if event["type"] == "http.response.start" and event["status"] == 204:
                counts["accepted"] += 1
            await send(event)

        await CollectorV3(published.append)(scope, received, sending)
        if report and captured is not None and len(reviewed) < 8:
            retained = retain_reviewed_packet([bytes(captured)], review=True)
            if retained is not None:
                reviewed.append(retained)
        captured.clear()

    receipt = {"journey_completed": False, "qualification": "installed fixture delivery"}
    with tempfile.TemporaryDirectory(prefix="mnemion-owned-telemetry-tls-") as temporary:
        class Factory:
            def mktemp(self, name):
                path = Path(temporary) / name
                path.mkdir()
                return path

        certificate, context = _certificates(Factory(), "localhost")
        key_path = certificate.parent / "key.pem"
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(8)
            port = listener.getsockname()[1]
            destination = f"https://localhost:{port}/v3/report"
            config = uvicorn.Config(
                ingress, log_config=None, access_log=False, server_header=False, date_header=False,
                timeout_keep_alive=0, ssl_certfile=str(certificate), ssl_keyfile=str(key_path),
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
                owned = Path(tempfile.mkdtemp(prefix="mnemion-owned-telemetry-installed-"))
                try:
                    async with memory_workspace(owned) as (memory, memory_counts):
                        if not str(memory["base_url"]).startswith("http://127.0.0.1:"):
                            raise ValueError("Telemetry fixture memory left loopback")
                        copy_declared_source(source, copy)
                        inventory = write_bake(copy, destination, "127.0.0.1", certificate.read_text(encoding="utf-8"))
                        inventory.update({
                            "source": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip(),
                            "package_output": "dist-electron",
                            "production_engine_archive_used": False,
                        })
                        (output / "diagnostic-inventory.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
                        environment = _build_env(source)
                        build = _run_logged(
                            [sys.executable, "-m", "deploy.build_desktop"], copy, environment, output / "packaging.log"
                        )
                        if build.returncode:
                            raise RuntimeError("Diagnostic packaging failed; production disclosure was not published")
                        package_output = copy / "dist-electron"
                        removed = _exclude_update_feeds(package_output)
                        inventory["update_feeds_removed"] = removed
                        installers = sorted(path.name for path in package_output.iterdir() if path.suffix in {".exe", ".dmg", ".AppImage", ".deb", ".zip"})
                        inventory["installer_sha256"] = {
                            name: _sha256_file(package_output / name) for name in installers
                        }
                        (output / "diagnostic-inventory.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
                        smoke_env = dict(environment)
                        smoke_env.update(
                            MNEMION_TELEMETRY_INSTALLED_DELIVERY="1",
                            MNEMION_TELEMETRY_FIXTURE_ENDPOINT=memory["base_url"],
                            MNEMION_TELEMETRY_FIXTURE_SPACE=memory["space_id"],
                            MNEMION_TELEMETRY_FIXTURE_KEY=memory["api_key"],
                        )
                        if sys.platform == "linux":
                            smoke = ["dbus-run-session", "--", "xvfb-run", "-a", "bash", "deploy/native-keyring-test.sh", "installed-hosting"]
                        else:
                            smoke = ["node", "studio/electron/scripts/smoke-installed-hosting.mjs"]
                        probe = subprocess.run(smoke, cwd=copy, env=smoke_env)
                        evidence_path = copy / "build-tmp/telemetry-installed-delivery.json"
                        evidence = json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.is_file() else {"app_checks_passed": False}
                        (output / "app-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
                        approved = evidence.get("approved_body_hex")
                        matched = reviewed == [approved] and counts == {
                            "reports": 1, "accepted": 1, "body_bytes": PACKET_BYTES, "forbidden_metadata": 0,
                        }
                        receipt = {
                            "qualification": "installed fixture delivery",
                            "journey_completed": bool(probe.returncode == 0 and evidence.get("app_checks_passed") is True and matched),
                            "collector_body_matches_inspection": reviewed == [approved],
                            "collector": counts,
                            "published_aggregate_count": len(published),
                            "memory_api": dict(memory_counts),
                            "app_checks_passed": evidence.get("app_checks_passed") is True,
                            "smoke_exit": probe.returncode,
                            "packaged": evidence.get("packaged") is True,
                            "runtime": evidence.get("runtime"),
                            "approved_body_hex": approved,
                            "review_checks": evidence.get("review_checks"),
                            "durable": evidence.get("durable"),
                            "installer_sha256": inventory["installer_sha256"],
                            "source": inventory["source"],
                            "diagnostic_configuration": {
                                "production_collection_available": False,
                                "diagnostic_collection_available": True,
                                "destination_host": "localhost",
                                "route_address": "127.0.0.1",
                                "excluded_from_publication": True,
                                "update_feeds_removed": removed,
                            },
                            "production_collection_available": False,
                            "resource_acceptance": False,
                            "scope": "Installed fixture delivery only. Production ingress, provider privacy, resources and full V08 remain unqualified.",
                        }
                        return receipt
                finally:
                    shutil.rmtree(owned, ignore_errors=True)
            finally:
                server.should_exit = True
                await task
    return receipt


def run(source: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32" and (os.environ.get("CI") != "true" or os.environ.get("RUNNER_OS") != "Windows"):
        message = "The installed telemetry package is installed only on a disposable Windows CI runner"
        _write_receipt(output, _receipt(message))
        raise RuntimeError(message)
    if sys.platform == "win32" and platform.machine().lower() in {"arm64", "aarch64"}:
        message = (
            "Windows ARM cannot freeze this diagnostic engine locally, and a production engine archive is refused. "
            "Build the engine on Windows x64 from the same baked disclosure and pass only that archive."
        )
        _write_receipt(output, _receipt(message))
        raise RuntimeError(message)
    source = source.resolve()
    original = (source / "mnemion/product_telemetry/disclosure.json").read_bytes()
    route_bytes = (source / "mnemion/product_telemetry/transport-route.json").read_bytes()
    receipt = _receipt("Installed fixture delivery did not start")
    try:
        with tempfile.TemporaryDirectory(prefix="mnemion-owned-telemetry-checkout-") as temporary:
            copy = Path(temporary) / "source"
            copy.mkdir()
            try:
                receipt = asyncio.run(_serve(copy, output, source))
            except Exception as exc:
                receipt = _receipt(_bounded_error(exc))
                raise
            finally:
                _preserve_build_notes(copy, output)
                disclosure_now = (source / "mnemion/product_telemetry/disclosure.json").read_bytes()
                route_now = (source / "mnemion/product_telemetry/transport-route.json").read_bytes()
                if disclosure_now != original or route_now != route_bytes:
                    receipt = _receipt("Production disclosure or route changed during diagnostic staging")
                    _write_receipt(output, receipt)
                    raise RuntimeError("Production disclosure or route changed during diagnostic staging")
                _write_receipt(output, receipt)
        return receipt
    finally:
        if not (output / "receipt.json").is_file():
            _write_receipt(output, receipt)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--read-store", type=Path)
    args = parser.parse_args()
    if args.read_store:
        secret = sys.stdin.buffer.read()
        json.dump(read_delivery_store(args.read_store, secret), sys.stdout)
        sys.stdout.write("\n")
        return
    if not args.source or not args.output:
        parser.error("--source and --output are required")
    receipt = run(args.source, args.output)
    if not receipt.get("journey_completed"):
        raise SystemExit("Inspect retained observations; installed fixture delivery did not pass")


if __name__ == "__main__":
    main()
