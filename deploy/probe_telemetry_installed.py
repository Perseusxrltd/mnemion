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
import signal
import socket
import sqlite3
import ssl
import stat
import subprocess
import sys
import tempfile
import threading


from deploy.telemetry_installed_fixture import (
    LOOPBACK_PORT,
    UPDATE_FEEDS,
    loopback_destination,
    validate_loopback_target,
    write_bake,
)


def read_delivery_store(profile: Path, secret: bytes) -> dict:
    from mnemion.product_telemetry.delivery import RESERVED_BYTES
    from mnemion.product_telemetry.policy import APPLICATION_ID, DATABASE_NAME, STORAGE_VERSION

    database = profile / "mnemion-product-telemetry" / DATABASE_NAME
    if not database.is_file() or not secret or len(secret) > 256:
        raise ValueError("The packaged telemetry database or fixture secret is unusable")
    raw = database.read_bytes()
    with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as connection:
        if (
            connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID
            or connection.execute("PRAGMA user_version").fetchone()[0] != STORAGE_VERSION
            or connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete"
        ):
            raise ValueError("The packaged telemetry database schema is not the current store")
        state = connection.execute(
            "SELECT lease_token, lease_deadline_ms FROM delivery_state WHERE singleton=1"
        ).fetchone()
        attempts = connection.execute(
            "SELECT slot, reserved_bytes FROM delivery_attempts ORDER BY slot"
        ).fetchall()
        pending = connection.execute("SELECT count(*) FROM pending").fetchone()
    if (
        state is None
        or pending is None
        or state[0] is not None
        or state[1] != 0
        or len(attempts) != 1
        or attempts[0][1] != RESERVED_BYTES
    ):
        raise ValueError("The packaged telemetry database has no single cleared reservation")
    return {
        "attempts": [1, RESERVED_BYTES],
        "lease_cleared": True,
        "queue_cells": pending[0],
        "fixture_content_absent": b"PRIVATE_RENDERER_MEMORY_CANARY" not in raw and secret not in raw,
    }


def copy_declared_source(source: Path, destination: Path) -> dict[str, str]:
    status = subprocess.check_output(["git", "status", "--porcelain", "-z"], cwd=source)
    if status.strip(b"\0"):
        raise RuntimeError("Diagnostic packaging requires a clean tracked checkout")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    names = subprocess.check_output(["git", "ls-files", "--cached", "-z"], cwd=source).decode().split("\0")
    digest = hashlib.sha256()
    for name in sorted(set(names) - {""}):
        path = source / name
        if path.is_symlink() or not path.is_file():
            continue
        payload = path.read_bytes()
        mode = stat.S_IMODE(path.stat().st_mode)
        digest.update(name.encode() + b"\0")
        digest.update(payload)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        target.chmod(mode)
    return {"source": head, "tracked_sha256": digest.hexdigest()}


def _npm(prefix: str) -> list[str]:
    command = f"npm --prefix {prefix} ci --no-fund --no-audit"
    if os.name == "nt":
        return [os.path.join(os.environ["SystemRoot"], "System32", "cmd.exe"), "/d", "/c", command]
    return ["npm", "--prefix", prefix, "ci", "--no-fund", "--no-audit"]


def _interpreter(source: Path, *parts: str) -> Path | None:
    candidate = source.joinpath(*parts)
    return candidate if candidate.is_file() else None


def _build_env(source: Path) -> dict[str, str]:
    blocked = {
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
    engine = environment.get("MNEMION_ENGINE_ARCHIVES", "").strip()
    if sys.platform == "win32" and engine:
        environment["MNEMION_ENGINE_ARCHIVES"] = engine
    else:
        environment.pop("MNEMION_ENGINE_ARCHIVES", None)
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


def _stop_process(process: subprocess.Popen) -> None:
    """Kill one diagnostic process tree. A timed-out package or app must not stay alive."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        killer = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "taskkill.exe")
        subprocess.run(
            [killer, "/F", "/T", "/PID", str(process.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            process.kill()
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _popen(command: list[str], cwd: Path, env: dict[str, str], stdout) -> subprocess.Popen:
    kwargs = {"start_new_session": True} if os.name != "nt" else {}
    return subprocess.Popen(command, cwd=cwd, env=env, stdout=stdout, stderr=subprocess.STDOUT, **kwargs)


def _run_logged(
    command: list[str], cwd: Path, env: dict[str, str], log_path: Path, timeout: int
) -> subprocess.CompletedProcess:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as stream:
        process = _popen(command, cwd, env, subprocess.PIPE)
        assert process.stdout is not None

        def pump() -> None:
            try:
                for chunk in iter(lambda: process.stdout.read(8192), b""):
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.buffer.flush()
                    stream.write(chunk)
                    stream.flush()
            except Exception:
                return

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _stop_process(process)
            reader.join(timeout=5)
            raise TimeoutError("Diagnostic command exceeded its finite timeout")
        reader.join(timeout=30)
        if process.poll() is None:
            _stop_process(process)
            raise TimeoutError("Diagnostic command did not exit")
        return subprocess.CompletedProcess(command, code)


def _run_inherited(command: list[str], cwd: Path, env: dict[str, str], timeout: int) -> subprocess.CompletedProcess:
    """Wait for the installed app without writing its stdout into the uploaded evidence."""
    process = _popen(command, cwd, env, None)
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _stop_process(process)
        raise TimeoutError("Installed application journey exceeded its finite timeout")
    if process.poll() is None:
        _stop_process(process)
        raise TimeoutError("Installed application journey did not exit")
    return subprocess.CompletedProcess(command, code)


def _desktop_arch() -> str:
    runner = os.environ.get("RUNNER_ARCH", "").upper()
    if runner == "ARM64":
        return "arm64"
    if runner == "X64":
        return "x64"
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    if machine in {"x86_64", "amd64"}:
        return "x64"
    raise RuntimeError("Unsupported desktop architecture")


def _expected_installers(copy: Path) -> list[Path]:
    package = json.loads((copy / "studio/electron/package.json").read_text(encoding="utf-8"))
    version = package["version"]
    output = copy / "dist-electron"
    arch = _desktop_arch()
    if sys.platform == "darwin":
        stem = f"Mnemion-Studio-{version}-macos-{arch}"
        names = [f"{stem}.dmg", f"{stem}.zip"]
    elif sys.platform == "win32":
        names = [f"Mnemion-Studio-{version}-windows-{arch}.exe"]
    else:
        stem = f"Mnemion-Studio-{version}-linux"
        names = [f"{stem}-x86_64.AppImage" if arch == "x64" else f"{stem}-{arch}.AppImage",
                 f"{stem}-amd64.deb" if arch == "x64" else f"{stem}-{arch}.deb"]
    paths = [output / name for name in names]
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError("Diagnostic packaging did not produce the normal installer names")
    return paths


async def _logged(
    command: list[str], cwd: Path, env: dict[str, str], log_path: Path, timeout: int
) -> subprocess.CompletedProcess:
    def run() -> subprocess.CompletedProcess:
        return _run_logged(command, cwd, env, log_path, timeout)

    return await asyncio.wait_for(asyncio.to_thread(run), timeout + 30)


async def _inherited(command: list[str], cwd: Path, env: dict[str, str], timeout: int) -> subprocess.CompletedProcess:
    def run() -> subprocess.CompletedProcess:
        return _run_inherited(command, cwd, env, timeout)

    return await asyncio.wait_for(asyncio.to_thread(run), timeout + 30)


def _require_loopback_material(material: Path) -> tuple[Path, Path, str]:
    certificate = (material / "certificate.pem")
    key = (material / "key.pem")
    if (
        not certificate.is_file()
        or not key.is_file()
        or certificate.is_symlink()
        or key.is_symlink()
        or certificate.stat().st_size > 4096
        or key.stat().st_size > 8192
    ):
        raise RuntimeError("Installed fixture delivery requires the shared loopback certificate and key")
    public = certificate.read_text(encoding="utf-8")
    private = key.read_text(encoding="utf-8")
    if "PRIVATE KEY" in public or "BEGIN CERTIFICATE" not in public or "PRIVATE KEY" not in private:
        raise RuntimeError("Loopback material must keep the public certificate and private key separate")
    validate_loopback_target(loopback_destination(), "127.0.0.1", public)
    return certificate, key, public


def _tls_context(certificate: Path, key: Path) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.num_tickets = 0
    context.load_cert_chain(certificate, key)
    return context


def _key_stays_outside(key: Path, *roots: Path) -> None:
    resolved_key = key.resolve()
    for root in roots:
        resolved = root.resolve()
        if resolved_key == resolved or resolved in resolved_key.parents:
            raise RuntimeError("Loopback key must stay outside the diagnostic copy and evidence")


def _fixture_absent_from_packets(reviewed: list, secret: str) -> bool:
    secret_bytes = secret.encode()
    canary = b"PRIVATE_RENDERER_MEMORY_CANARY"
    for item in reviewed:
        if not isinstance(item, str):
            return False
        try:
            body = bytes.fromhex(item)
        except ValueError:
            return False
        if canary in body or secret_bytes in body:
            return False
    return True


def _load_app_evidence(path: Path, secret: str) -> dict:
    if not path.is_file():
        return {"app_checks_passed": False}
    text = path.read_text(encoding="utf-8")
    if "PRIVATE_RENDERER_MEMORY_CANARY" in text or (secret and secret in text):
        return {"app_checks_passed": False, "private_content_withheld": True}
    loaded = json.loads(text)
    return loaded if isinstance(loaded, dict) else {"app_checks_passed": False}


def _drop_private_files(output: Path) -> None:
    needles = (b"PRIVATE KEY", b"PRIVATE_RENDERER_MEMORY_CANARY")
    removed = False
    for path in list(output.rglob("*")):
        if not path.is_file() or path.name in {"receipt.json", "private-material-withheld.txt"}:
            continue
        if _file_contains(path, needles):
            path.unlink()
            removed = True
    if removed:
        (output / "private-material-withheld.txt").write_text(
            "A diagnostic file contained private fixture material and was removed before upload.\n",
            encoding="utf-8",
        )


def _file_contains(path: Path, needles: tuple[bytes, ...]) -> bool:
    try:
        with path.open("rb") as stream:
            previous = b""
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    return False
                window = previous + chunk
                if any(needle in window for needle in needles):
                    return True
                previous = window[-80:]
    except OSError:
        return False


def _refuse(output: Path, message: str) -> None:
    _write_receipt(output, _receipt(message))
    raise RuntimeError(message)


async def _serve(copy: Path, output: Path, source: Path, material: Path) -> dict:
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

    certificate, key_path, public = _require_loopback_material(material)
    _key_stays_outside(key_path, output, copy)
    context = _tls_context(certificate, key_path)
    destination = loopback_destination()
    # Capture producer paths before the memory fixture clears MNEMION_* for its yield.
    environment = _build_env(source)
    with socket.socket() as listener:
        try:
            listener.bind(("127.0.0.1", LOOPBACK_PORT))
        except OSError as exc:
            raise RuntimeError("The installed fixture loopback port did not bind") from exc
        listener.listen(8)
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
            copied = await asyncio.to_thread(copy_declared_source, source, copy)
            for prefix, log_name in (
                ("packages/client", "npm-packages-client.log"),
                ("studio/frontend", "npm-studio-frontend.log"),
                ("studio/electron", "npm-studio-electron.log"),
            ):
                installed = await _logged(_npm(prefix), copy, environment, output / log_name, 20 * 60)
                if installed.returncode:
                    raise RuntimeError("Diagnostic copy dependency install failed")
            inventory = write_bake(copy, destination, "127.0.0.1", public)
            inventory.update({
                "source": copied["source"],
                "tracked_sha256": copied["tracked_sha256"],
                "package_output": "dist-electron",
                "production_engine_archive_used": False,
            })
            (output / "diagnostic-inventory.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
            build = await _logged(
                [sys.executable, "-m", "deploy.build_desktop"], copy, environment, output / "packaging.log", 50 * 60
            )
            if build.returncode:
                raise RuntimeError("Diagnostic packaging failed; production disclosure was not published")
            package_output = copy / "dist-electron"
            removed = _exclude_update_feeds(package_output)
            inventory["update_feeds_removed"] = removed
            installers = _expected_installers(copy)
            inventory["installer_sha256"] = {path.name: _sha256_file(path) for path in installers}
            (output / "diagnostic-inventory.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
            from mnemion.local_state import temporary_directory

            with temporary_directory(prefix="mnemion-owned-telemetry-") as owned:
                async with memory_workspace(owned) as (memory, memory_counts):
                    if not str(memory["base_url"]).startswith("http://127.0.0.1:"):
                        raise ValueError("Telemetry fixture memory left loopback")
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
                    probe = await _inherited(smoke, copy, smoke_env, 45 * 60)
                    evidence_path = copy / "build-tmp/telemetry-installed-delivery.json"
                    evidence = _load_app_evidence(evidence_path, str(memory["api_key"]))
                    (output / "app-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
                    approved = evidence.get("approved_body_hex")
                    counts_ok = counts == {
                        "reports": 1, "accepted": 1, "body_bytes": PACKET_BYTES, "forbidden_metadata": 0,
                    }
                    body_match = reviewed == [approved]
                    private_absent = (
                        evidence.get("private_content_withheld") is not True
                        and isinstance(evidence.get("durable"), dict)
                        and evidence["durable"].get("fixture_content_absent") is True
                        and _fixture_absent_from_packets(reviewed, str(memory["api_key"]))
                    )
                    receipt = {
                        "qualification": "installed fixture delivery",
                        "journey_completed": bool(
                            probe.returncode == 0 and evidence.get("app_checks_passed") is True
                            and counts_ok and body_match and private_absent
                        ),
                        "collector_body_matches_inspection": body_match,
                        "collector": counts,
                        "published_aggregate_count": len(published),
                        "memory_api": dict(memory_counts),
                        "app_checks_passed": evidence.get("app_checks_passed") is True,
                        "smoke_exit": probe.returncode,
                        "packaged": evidence.get("packaged") is True,
                        "runtime": evidence.get("runtime"),
                        "approved_body_hex": approved if private_absent else None,
                        "review_checks": evidence.get("review_checks"),
                        "durable": evidence.get("durable"),
                        "installer_sha256": inventory["installer_sha256"],
                        "source": inventory["source"],
                        "tracked_sha256": inventory["tracked_sha256"],
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
                        "scope": _SCOPE,
                    }
                    return receipt
        finally:
            server.should_exit = True
            await task


def run(source: Path, output: Path, material: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32" and (os.environ.get("CI") != "true" or os.environ.get("RUNNER_OS") != "Windows"):
        _refuse(output, "The installed telemetry package is installed only on a disposable Windows CI runner")
    if sys.platform == "win32" and os.environ.get("RUNNER_ARCH", "").upper() == "ARM64":
        if not os.environ.get("MNEMION_ENGINE_ARCHIVES", "").strip():
            _refuse(output, "Windows ARM requires the same-source diagnostic x64 engine archive")
    source = source.resolve()
    material = material.resolve()
    try:
        _require_loopback_material(material)
        _key_stays_outside(material / "key.pem", output)
    except Exception as exc:
        _refuse(output, _bounded_error(exc))
    original = (source / "mnemion/product_telemetry/disclosure.json").read_bytes()
    route_bytes = (source / "mnemion/product_telemetry/transport-route.json").read_bytes()
    receipt = _receipt("Installed fixture delivery did not start")
    try:
        with tempfile.TemporaryDirectory(prefix="mnemion-owned-telemetry-checkout-") as temporary:
            copy = Path(temporary) / "source"
            copy.mkdir()
            try:
                receipt = asyncio.run(_serve(copy, output, source, material))
            except Exception as exc:
                receipt = _receipt(_bounded_error(exc))
                raise
            finally:
                _preserve_build_notes(copy, output)
                _drop_private_files(output)
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
    parser.add_argument("--loopback-material", type=Path)
    parser.add_argument("--read-store", type=Path)
    args = parser.parse_args()
    if args.read_store:
        secret = sys.stdin.buffer.read()
        json.dump(read_delivery_store(args.read_store, secret), sys.stdout)
        sys.stdout.write("\n")
        return
    if not args.source or not args.output or not args.loopback_material:
        parser.error("--source, --output and --loopback-material are required")
    receipt = run(args.source, args.output, args.loopback_material)
    if not receipt.get("journey_completed"):
        raise SystemExit("Inspect retained observations; installed fixture delivery did not pass")


if __name__ == "__main__":
    main()
