"""Build one unpublished diagnostic package and run the installed delivery journey.

The package is a copy of this source with loopback disclosure and route baked
before the normal client, frontend and native-engine build. Production files
and release feeds are not changed. This does not claim the journey passed.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Mapping
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import platform
import re
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


from deploy.report_telemetry_renderer import (
    INSTALLED_DESKTOP_ENV,
    PHASE_MEMORY_CHECKPOINTS,
    owned_delegate_identity_ok,
    owned_scope_command,
    resource_counterbalance_cases,
    retain_owned_launch,
)
from deploy.telemetry_installed_fixture import (
    LOOPBACK_PORT,
    UPDATE_FEEDS,
    loopback_destination,
    record_inactive,
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
        "fixture_content_absent": b"PRIVATE_RENDERER_MEMORY_CANARY" not in raw
        and secret not in raw,
    }


def read_resource_profile_store(profile: Path) -> dict:
    """Attempt counts for one case. A missing store is zero attempts, not an error."""
    from mnemion.product_telemetry.policy import DATABASE_NAME

    database = profile / "mnemion-product-telemetry" / DATABASE_NAME
    if not database.is_file():
        return {
            "present": False,
            "attempts": 0,
            "reserved_bytes": 0,
            "fixture_content_absent": True,
        }
    from mnemion.product_telemetry.policy import APPLICATION_ID, STORAGE_VERSION

    raw = database.read_bytes()
    with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as connection:
        if (
            connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID
            or connection.execute("PRAGMA user_version").fetchone()[0] != STORAGE_VERSION
        ):
            raise ValueError("resource_store_unreadable")
        row = connection.execute(
            "SELECT count(*), coalesce(sum(reserved_bytes), 0) FROM delivery_attempts"
        ).fetchone()
    if row is None:
        raise ValueError("resource_store_unreadable")
    return {
        "present": True,
        "attempts": int(row[0]),
        "reserved_bytes": int(row[1]),
        "fixture_content_absent": b"PRIVATE_RENDERER_MEMORY_CANARY" not in raw,
    }


def copy_declared_source(source: Path, destination: Path) -> dict[str, str]:
    status = subprocess.check_output(["git", "status", "--porcelain", "-z"], cwd=source)
    if status.strip(b"\0"):
        raise RuntimeError("Diagnostic packaging requires a clean tracked checkout")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    names = (
        subprocess.check_output(["git", "ls-files", "--cached", "-z"], cwd=source)
        .decode()
        .split("\0")
    )
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
        found = _interpreter(
            source, "studio/client/.venv", "Scripts/python.exe" if windows else "bin/python"
        )
        if found:
            environment["MNEMION_BUILD_PYTHON"] = str(found)
    archives = environment.get("MNEMION_POSTGRES_ARCHIVES") or str(
        source / "build-tmp/native-postgres"
    )
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
_RESOURCE_SCOPE = (
    "Installed resource workload only. Production collection stays off. "
    "The 8 MiB and 0.5 percent budgets remain unaccepted. Completion is not acceptance."
)


def _receipt(error: str | None = None, *, resource: bool = False) -> dict:
    receipt = {
        "qualification": "installed resource workload" if resource else "installed fixture delivery",
        "journey_completed": False,
        "production_collection_available": False,
        "resource_acceptance": False,
        "scope": _RESOURCE_SCOPE if resource else _SCOPE,
    }
    if resource:
        receipt["delivery_compared"] = False
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
        or "\\" in text
        or "/users/" in lowered
        or "/home/" in lowered
        or "runner_temp" in lowered
    ):
        return type(exc).__name__
    return text


def _write_receipt(output: Path, receipt: dict) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


def _preserve_build_notes(copy: Path, output: Path, folder: str = "build-notes") -> None:
    notes = copy / "build-tmp"
    if not notes.is_dir():
        return
    destination = output / folder
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
        killer = os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"), "System32", "taskkill.exe"
        )
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
    return subprocess.Popen(
        command, cwd=cwd, env=env, stdout=stdout, stderr=subprocess.STDOUT, **kwargs
    )


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


def _run_inherited(
    command: list[str], cwd: Path, env: dict[str, str], timeout: int
) -> subprocess.CompletedProcess:
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


def _run_resource_smoke(command, cwd, env, timeout, on_line) -> subprocess.CompletedProcess:
    """Read case lines as they finish. Stdout is not stored in the uploaded evidence."""
    process = _popen(command, cwd, env, subprocess.PIPE)
    assert process.stdout is not None

    def pump() -> None:
        pending = b""
        try:
            while True:
                chunk = process.stdout.read(4096)
                if not chunk:
                    break
                pending += chunk
                while b"\n" in pending:
                    raw, pending = pending.split(b"\n", 1)
                    if b"PRIVATE_RENDERER_MEMORY_CANARY" in raw or b"mnm_" in raw:
                        continue
                    if len(raw) <= 2048:
                        sys.stdout.buffer.write(raw + b"\n")
                        sys.stdout.buffer.flush()
                    text = raw.decode("utf-8", "replace").strip()
                    if text.startswith("RESOURCE_CASE "):
                        on_line(text)
        except Exception:
            return

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _stop_process(process)
        reader.join(timeout=5)
        raise TimeoutError("Installed application journey exceeded its finite timeout")
    reader.join(timeout=30)
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
        names = [
            f"{stem}-x86_64.AppImage" if arch == "x64" else f"{stem}-{arch}.AppImage",
            f"{stem}-amd64.deb" if arch == "x64" else f"{stem}-{arch}.deb",
        ]
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


async def _inherited(
    command: list[str], cwd: Path, env: dict[str, str], timeout: int
) -> subprocess.CompletedProcess:
    def run() -> subprocess.CompletedProcess:
        return _run_inherited(command, cwd, env, timeout)

    return await asyncio.wait_for(asyncio.to_thread(run), timeout + 30)


def _require_loopback_material(material: Path) -> tuple[Path, Path, str]:
    certificate = material / "certificate.pem"
    key = material / "key.pem"
    if (
        not certificate.is_file()
        or not key.is_file()
        or certificate.is_symlink()
        or key.is_symlink()
        or certificate.stat().st_size > 4096
        or key.stat().st_size > 8192
    ):
        raise RuntimeError(
            "Installed fixture delivery requires the shared loopback certificate and key"
        )
    public = certificate.read_text(encoding="utf-8")
    private = key.read_text(encoding="utf-8")
    if "PRIVATE KEY" in public or "BEGIN CERTIFICATE" not in public or "PRIVATE KEY" not in private:
        raise RuntimeError(
            "Loopback material must keep the public certificate and private key separate"
        )
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


_OBSERVATION_COUNTERS = (
    "snapshot_admitted",
    "snapshot_null",
    "snapshot_rejected",
    "snapshot_deadline",
    "snapshot_elapsed_lt_5",
    "snapshot_elapsed_lt_25",
    "snapshot_elapsed_ge_25",
    "acl_accepted",
    "acl_refused",
    "acl_timed_out",
    "acl_duration_lt_50",
    "acl_duration_lt_250",
    "acl_duration_lt_1000",
    "acl_duration_ge_1000",
    "snapshot_suppressed_owner",
    "snapshot_suppressed_hint",
    "record_attempted",
    "record_committed",
    "record_refused_owner",
    "record_refused_stamp",
    "record_refused_policy",
    "record_refused_storage",
)
_OBSERVATION_READINESS = frozenset(
    {
        "none",
        "manual_review",
        "before_permission",
        "collection_enabled",
        "memory_observations",
        "report_inspect",
        "report_bytes",
        "report_held",
        "invalidated_report",
        "collection_reenabled",
        "report_discard",
        "report_discarded",
        "report_approve",
        "report_consumed",
        "final_opt_out",
        "restart_review",
        "review_request",
        "privacy_open",
        "unknown_phase",
    }
)
_OBSERVATION_PENDING = frozenset(
    {
        "none",
        "unavailable",
        "not_initialized",
        "upgrade_required",
        "stored_snapshot",
        "inactive",
        "paused",
        "held",
        "discarded",
        "approved",
        "consumed",
        "expired",
        "invalidated",
        "no_report",
        "no_observations",
        "collection_not_permitted",
        "transport_unavailable",
        "delivery_not_ready",
        "control_unavailable",
        "review_unavailable",
        "review_not_paused",
        "connection_pending",
        "collection_pending",
        "observations_pending",
        "report_not_held",
        "report_not_discarded",
        "report_not_consumed",
        "privacy_navigation",
        "privacy_page",
        "privacy_state",
        "privacy_control",
    }
)


def _observation_diagnostic(value: object) -> dict | None:
    """Copy fixed counters only. Drop the field when any token or count is outside the bound."""
    if not isinstance(value, dict):
        return None
    safe: dict = {}
    for name in _OBSERVATION_COUNTERS:
        number = value.get(name)
        if type(number) is not int or number < 0 or number > 255:
            return None
        safe[name] = number
    cycle = value.get("cycle")
    readiness = value.get("readiness")
    pending = value.get("pending")
    if type(cycle) is not int or cycle < 0 or cycle > 3:
        return None
    if type(readiness) is not str or type(pending) is not str:
        return None
    if readiness not in _OBSERVATION_READINESS or pending not in _OBSERVATION_PENDING:
        return None
    safe["cycle"] = cycle
    safe["readiness"] = readiness
    safe["pending"] = pending
    return safe


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


def _refuse(output: Path, message: str, *, resource: bool = False) -> None:
    _write_receipt(output, _receipt(message, resource=resource))
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
                {name for name, _ in scope.get("headers", [])}
                & {b"cookie", b"authorization", b"referer", b"user-agent"}
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
                installed = await _logged(
                    _npm(prefix), copy, environment, output / log_name, 20 * 60
                )
                if installed.returncode:
                    raise RuntimeError("Diagnostic copy dependency install failed")
            inventory = write_bake(copy, destination, "127.0.0.1", public)
            inventory.update(
                {
                    "source": copied["source"],
                    "tracked_sha256": copied["tracked_sha256"],
                    "package_output": "dist-electron",
                    "production_engine_archive_used": False,
                }
            )
            (output / "diagnostic-inventory.json").write_text(
                json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
            )
            build = await _logged(
                [sys.executable, "-m", "deploy.build_desktop"],
                copy,
                environment,
                output / "packaging.log",
                50 * 60,
            )
            if build.returncode:
                raise RuntimeError(
                    "Diagnostic packaging failed; production disclosure was not published"
                )
            package_output = copy / "dist-electron"
            removed = _exclude_update_feeds(package_output)
            inventory["update_feeds_removed"] = removed
            installers = _expected_installers(copy)
            inventory["installer_sha256"] = {path.name: _sha256_file(path) for path in installers}
            (output / "diagnostic-inventory.json").write_text(
                json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
            )
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
                        smoke = [
                            "dbus-run-session",
                            "--",
                            "xvfb-run",
                            "-a",
                            "bash",
                            "deploy/native-keyring-test.sh",
                            "installed-hosting",
                        ]
                    else:
                        smoke = ["node", "studio/electron/scripts/smoke-installed-hosting.mjs"]
                    probe = await _inherited(smoke, copy, smoke_env, 45 * 60)
                    evidence_path = copy / "build-tmp/telemetry-installed-delivery.json"
                    evidence = _load_app_evidence(evidence_path, str(memory["api_key"]))
                    (output / "app-evidence.json").write_text(
                        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
                    )
                    approved = evidence.get("approved_body_hex")
                    counts_ok = counts == {
                        "reports": 1,
                        "accepted": 1,
                        "body_bytes": PACKET_BYTES,
                        "forbidden_metadata": 0,
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
                            probe.returncode == 0
                            and evidence.get("app_checks_passed") is True
                            and counts_ok
                            and body_match
                            and private_absent
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
                        **(
                            {"observation": observation}
                            if (observation := _observation_diagnostic(evidence.get("observation")))
                            else {}
                        ),
                        "production_collection_available": False,
                        "resource_acceptance": False,
                        "scope": _SCOPE,
                    }
                    return receipt
        finally:
            server.should_exit = True
            await task


def select_owned_observer(environ: object, *, platform_name: str) -> str:
    """The native client interpreter. Windows ARM must not reuse the x64 engine."""
    if not isinstance(environ, Mapping):
        raise RuntimeError("Resource accounting requires MNEMION_OWNED_LAUNCH_PYTHON")
    observer = environ.get("MNEMION_OWNED_LAUNCH_PYTHON")
    if type(observer) is not str or not observer.strip():
        raise RuntimeError("Resource accounting requires MNEMION_OWNED_LAUNCH_PYTHON")
    arm = any(
        str(environ.get(name, "")).upper() == "ARM64"
        for name in ("PROCESSOR_ARCHITECTURE", "RUNNER_ARCH")
    )
    engine = environ.get("MNEMION_ENGINE_PYTHON")
    engine_missing = type(engine) is not str or not engine.strip()
    if platform_name == "win32" and arm and (
        engine_missing or os.path.normcase(observer) == os.path.normcase(engine)
    ):
        raise RuntimeError("Windows ARM observer must be the native client Python")
    return observer


def linux_resource_launch_allowed(*, mode, probe_mode, returncode, stdout, euid) -> bool:
    """A failed identity probe does not become an unmeasured launch."""
    return (
        mode == "systemd_service_delegate"
        and probe_mode == "systemd_service_delegate"
        and owned_delegate_identity_ok(returncode, stdout, euid)
    )


# The existing 128-cycle workload is save, fetch and lexical recall.
CANONICAL_MEMORY_RESULTS = 384
_REPORT_HEX = re.compile(r"[0-9a-f]{50}\Z")


def note_resource_ingress(captured, reviewed, counts) -> dict:
    """Keep one exact body. A null capture is a rejected body and is not cleared."""
    from deploy.report_telemetry_renderer import retain_reviewed_packet

    malformed = captured is None
    retained = None
    if captured is not None and len(reviewed) < 8:
        retained = retain_reviewed_packet([bytes(captured)], review=True)
        if retained is not None:
            reviewed.append(retained)
    if captured is not None:
        captured.clear()
    rejected = malformed or retained is None
    if rejected:
        counts["malformed_body"] = counts.get("malformed_body", 0) + 1
    return {"malformed": rejected, "body_hex": retained}


def resource_observation_complete(
    condition: object,
    *,
    attempts: object,
    reserved_bytes: object,
    events: object,
    memory_successful: object,
    memory_api_operations: object,
    inspected_body_hex: object,
) -> bool:
    """Per-case telemetry outside the app. Global totals are not enough."""
    if (
        type(memory_successful) is not int
        or memory_successful < CANONICAL_MEMORY_RESULTS
        or memory_api_operations != CANONICAL_MEMORY_RESULTS
        or type(events) is not list
        or type(attempts) is not int
        or type(reserved_bytes) is not int
    ):
        return False
    if condition in ("unavailable", "opted_out"):
        return attempts == 0 and reserved_bytes == 0 and events == []
    if condition != "enabled":
        return False
    if attempts != 1 or reserved_bytes != 65536 or len(events) != 1:
        return False
    event = events[0]
    if type(event) is not dict or event.get("malformed") is True:
        return False
    body = event.get("body_hex")
    if type(body) is not str or not _REPORT_HEX.fullmatch(body):
        return False
    if inspected_body_hex is not None and inspected_body_hex != body:
        return False
    return True


def installed_resource_case_completed(evidence, owned) -> bool:
    """Matching verified counts are not resource acceptance."""
    if type(evidence) is not dict or type(owned) is not dict:
        return False
    cycles = evidence.get("memory_cycles")
    observed = owned.get("canonical_operations_completed")
    if type(cycles) is not int or type(observed) is not int or cycles != observed:
        return False
    if evidence.get("memory_results_verified") is not True:
        return False
    if list(evidence.get("checkpoints") or []) != list(PHASE_MEMORY_CHECKPOINTS):
        return False
    if evidence.get("model_calls") != 0:
        return False
    if evidence.get("resource_acceptance") is not False or owned.get("resource_acceptance") is not False:
        return False
    return resource_observation_complete(
        evidence.get("condition"),
        attempts=evidence.get("telemetry_attempts"),
        reserved_bytes=evidence.get("telemetry_reserved_bytes"),
        events=evidence.get("telemetry_events"),
        memory_successful=evidence.get("memory_successful"),
        memory_api_operations=evidence.get("memory_api_operations"),
        inspected_body_hex=evidence.get("inspected_body_hex"),
    )


def bind_resource_packages(*, source: str, active: Path, inactive: Path) -> dict:
    """Hash both installers. The manifest has no credential and no private key."""
    if type(source) is not str or not re.fullmatch(r"[0-9a-f]{40}", source):
        raise ValueError("Resource packages require the declared source")
    if active.resolve() == inactive.resolve():
        raise ValueError("Inactive and active installers must be different files")

    def record(path: Path, condition: str) -> dict:
        if not path.is_file():
            raise ValueError("Resource installer is missing")
        return {"installer": str(path), "sha256": _sha256_file(path), "condition": condition}

    manifest = {
        "source": source,
        "packages": {
            "inactive": record(inactive, "inactive"),
            "active": record(active, "active"),
        },
        "cases": resource_counterbalance_cases(),
    }
    if "credential" in manifest or "api_key" in manifest:
        raise ValueError("Resource manifest must not carry a credential")
    return manifest


def resource_smoke_environment(base, *, observer, endpoint, space, fixture_key, manifest) -> dict:
    """Pass the observer and fixture to smoke. Delivery mode stays off."""
    if type(base) is not dict or type(observer) is not str or not observer:
        raise RuntimeError("Resource smoke environment is missing")
    env = {
        name: value
        for name, value in base.items()
        if name != "MNEMION_TELEMETRY_INSTALLED_DELIVERY"
    }
    env["MNEMION_TELEMETRY_INSTALLED_RESOURCE"] = "1"
    env["MNEMION_OWNED_LAUNCH_PYTHON"] = observer
    env["MNEMION_TELEMETRY_FIXTURE_ENDPOINT"] = endpoint
    env["MNEMION_TELEMETRY_FIXTURE_SPACE"] = space
    env["MNEMION_TELEMETRY_FIXTURE_KEY"] = fixture_key
    env["MNEMION_TELEMETRY_RESOURCE_MANIFEST"] = str(manifest)
    if "MNEMION_TELEMETRY_INSTALLED_DELIVERY" in env:
        raise RuntimeError("Resource launches cannot inherit installed delivery diagnostics")
    return env


def _engine_label(archives: str) -> str:
    if not archives:
        return "built-from-package-source"
    directory = Path(archives)
    if not directory.is_dir():
        raise RuntimeError("Diagnostic engine archive directory is missing")
    zips = sorted(
        path for path in directory.iterdir() if path.is_file() and path.suffix == ".zip"
    )
    if len(zips) != 1:
        raise RuntimeError("Diagnostic engine directory must contain exactly one archive")
    return directory.name + ":" + _sha256_file(zips[0])


def _absolute_tool(name: str) -> str:
    found = shutil.which(name)
    if type(found) is not str or not found.startswith("/") or "\x00" in found or not Path(found).is_file():
        raise RuntimeError("Linux resource comparison requires absolute session tools")
    return found


async def _serve_resources(copy: Path, output: Path, source: Path, material: Path) -> dict:
    """Build one inactive and one active package, then run the six owned cases."""
    from mnemion.product_telemetry.collector_v3 import CollectorV3
    from deploy.report_telemetry_renderer import absorb_reviewed_chunk, retain_reviewed_packet
    from deploy.telemetry_memory_fixture import memory_workspace
    import uvicorn

    active_archives = os.environ.get("MNEMION_ENGINE_ARCHIVES", "").strip()
    inactive_archives = os.environ.get("MNEMION_ENGINE_ARCHIVES_INACTIVE", "").strip()
    runner_arch = os.environ.get("RUNNER_ARCH", "")
    observer = select_owned_observer(os.environ, platform_name=sys.platform)
    environment = _build_env(source)
    environment.pop("MNEMION_TELEMETRY_INSTALLED_DELIVERY", None)
    if sys.platform == "win32":
        if not active_archives or not inactive_archives:
            raise RuntimeError(
                "Windows resource comparison requires separate active and inactive engine archives"
            )
        active_dir = str(Path(active_archives).resolve())
        inactive_dir = str(Path(inactive_archives).resolve())
        if active_dir == inactive_dir:
            raise RuntimeError(
                "Windows resource comparison requires separate active and inactive engine archives"
            )
        environment["MNEMION_ENGINE_ARCHIVES"] = active_dir
        active_label = _engine_label(active_dir)
        inactive_label = _engine_label(inactive_dir)
    else:
        environment.pop("MNEMION_ENGINE_ARCHIVES", None)
        environment.pop("MNEMION_ENGINE_ARCHIVES_INACTIVE", None)
        active_label = "built-from-package-source"
        inactive_label = "built-from-package-source"
        active_dir = ""
        inactive_dir = ""
    published = []
    counts = {
        "reports": 0,
        "accepted": 0,
        "body_bytes": 0,
        "forbidden_metadata": 0,
        "malformed_body": 0,
    }
    reviewed = []
    events = []
    observation_lock = threading.Lock()

    async def ingress(scope, receive, send):
        captured = bytearray()
        chunks = 0
        report = scope.get("type") == "http" and scope.get("method") == "POST"
        if report:
            with observation_lock:
                counts["reports"] += 1
                counts["forbidden_metadata"] += bool(
                    {name for name, _ in scope.get("headers", [])}
                    & {b"cookie", b"authorization", b"referer", b"user-agent"}
                )

        async def received():
            nonlocal captured, chunks
            event = await receive()
            if report and event["type"] == "http.request":
                chunk = event.get("body", b"")
                if type(chunk) is bytes:
                    with observation_lock:
                        counts["body_bytes"] += len(chunk)
                    captured, chunks = absorb_reviewed_chunk(captured, chunks, chunk)
            return event

        async def sending(event):
            if event["type"] == "http.response.start" and event["status"] == 204:
                with observation_lock:
                    counts["accepted"] += 1
            await send(event)

        await CollectorV3(published.append)(scope, received, sending)
        if report:
            with observation_lock:
                events.append(note_resource_ingress(captured, reviewed, counts))

    certificate, key_path, public = _require_loopback_material(material)
    inactive_copy = copy.parent / "inactive-source"
    _key_stays_outside(key_path, output, copy, inactive_copy)
    context = _tls_context(certificate, key_path)
    destination = loopback_destination()
    with socket.socket() as listener:
        try:
            listener.bind(("127.0.0.1", LOOPBACK_PORT))
        except OSError as exc:
            raise RuntimeError("The installed fixture loopback port did not bind") from exc
        listener.listen(8)
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
        try:
            async with asyncio.timeout(20):
                while not server.started:
                    if task.done():
                        await task
                        raise RuntimeError("Owned TLS collector did not start")
                    await asyncio.sleep(0.01)

            async def package(target: Path, build_env: dict, prefix: str, bake: bool, label: str):
                if not target.exists():
                    target.mkdir()
                copied = await asyncio.to_thread(copy_declared_source, source, target)
                for npm_prefix, log_name in (
                    ("packages/client", "npm-packages-client.log"),
                    ("studio/frontend", "npm-studio-frontend.log"),
                    ("studio/electron", "npm-studio-electron.log"),
                ):
                    installed = await _logged(
                        _npm(npm_prefix), target, build_env, output / f"{prefix}-{log_name}", 20 * 60
                    )
                    if installed.returncode:
                        raise RuntimeError("Diagnostic copy dependency install failed")
                if bake:
                    inventory = write_bake(target, destination, "127.0.0.1", public)
                else:
                    inventory = record_inactive(target)
                inventory.update(
                    {
                        "source": copied["source"],
                        "tracked_sha256": copied["tracked_sha256"],
                        "package_output": "dist-electron",
                        "production_engine_archive_used": False,
                        "engine_label": label,
                        "condition": "active" if bake else "inactive",
                    }
                )
                (output / f"{prefix}-diagnostic-inventory.json").write_text(
                    json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
                )
                build = await _logged(
                    [sys.executable, "-m", "deploy.build_desktop"],
                    target,
                    build_env,
                    output / f"{prefix}-packaging.log",
                    50 * 60,
                )
                if build.returncode:
                    raise RuntimeError(
                        "Diagnostic packaging failed; production disclosure was not published"
                    )
                removed = _exclude_update_feeds(target / "dist-electron")
                inventory["update_feeds_removed"] = removed
                installers = _expected_installers(target)
                inventory["installer_sha256"] = {
                    path.name: _sha256_file(path) for path in installers
                }
                (output / f"{prefix}-diagnostic-inventory.json").write_text(
                    json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
                )
                return inventory, installers[0], copied["source"]

            inactive_env = dict(environment)
            active_env = dict(environment)
            inactive_env["MNEMION_TELEMETRY_RESOURCE_PROBE"] = "1"
            active_env["MNEMION_TELEMETRY_RESOURCE_PROBE"] = "1"
            environment.pop("MNEMION_ENGINE_ARCHIVES_INACTIVE", None)
            inactive_env.pop("MNEMION_ENGINE_ARCHIVES_INACTIVE", None)
            active_env.pop("MNEMION_ENGINE_ARCHIVES_INACTIVE", None)
            if sys.platform == "win32":
                inactive_env["MNEMION_ENGINE_ARCHIVES"] = inactive_dir
            else:
                inactive_env.pop("MNEMION_ENGINE_ARCHIVES", None)
            inactive_inventory, inactive_installer, inactive_source = await package(
                inactive_copy, inactive_env, "inactive", False, inactive_label
            )
            active_inventory, active_installer, active_source = await package(
                copy, active_env, "active", True, active_label
            )
            if inactive_source != active_source:
                raise RuntimeError("Resource packages diverged from the declared source")
            manifest = bind_resource_packages(
                source=active_source, active=active_installer, inactive=inactive_installer
            )
            manifest_path = copy.parent / "resource-manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            manifest_path.chmod(0o600)
            from mnemion.local_state import temporary_directory

            with temporary_directory(prefix="mnemion-owned-telemetry-") as owned:
                async with memory_workspace(owned) as (memory, memory_counts):
                    if not str(memory["base_url"]).startswith("http://127.0.0.1:"):
                        raise ValueError("Telemetry fixture memory left loopback")
                    secret = str(memory["api_key"])
                    smoke_env = resource_smoke_environment(
                        environment,
                        observer=observer,
                        endpoint=memory["base_url"],
                        space=memory["space_id"],
                        fixture_key=secret,
                        manifest=manifest_path,
                    )
                    if sys.platform == "linux":
                        plain = [
                            _absolute_tool("dbus-run-session"),
                            "--",
                            _absolute_tool("xvfb-run"),
                            "-a",
                            _absolute_tool("bash"),
                            "deploy/native-keyring-test.sh",
                            "installed-hosting",
                        ]
                        common = dict(
                            requested=True,
                            systemd=_absolute_tool("systemd-run"),
                            sudo=_absolute_tool("sudo"),
                            euid=os.geteuid(),
                            egid=os.getegid(),
                            cwd=str(copy.resolve()),
                            environ=smoke_env,
                            probe_accepted=None,
                            env_names=INSTALLED_DESKTOP_ENV,
                        )
                        command, mode = owned_scope_command(plain, **common)
                        probe_command, probe_mode = owned_scope_command(
                            [_absolute_tool("id"), "-u"], **common
                        )
                        completed = None
                        if probe_mode == "systemd_service_delegate":
                            completed = subprocess.run(
                                probe_command, capture_output=True, text=True, timeout=60
                            )
                        allowed = linux_resource_launch_allowed(
                            mode=mode,
                            probe_mode=probe_mode,
                            returncode=None if completed is None else completed.returncode,
                            stdout="" if completed is None else completed.stdout,
                            euid=common["euid"],
                        )
                        (output / "resource-launch-scope.json").write_text(
                            json.dumps(
                                {
                                    "launch": mode,
                                    "probe": probe_mode,
                                    "requested": True,
                                    "allowed": allowed,
                                    "resource_acceptance": False,
                                },
                                indent=2,
                            )
                            + "\n",
                            encoding="utf-8",
                        )
                        if not allowed:
                            raise RuntimeError(
                                "Linux resource comparison refused to launch without a delegated identity"
                            )
                        smoke = command
                    else:
                        smoke = ["node", "studio/electron/scripts/smoke-installed-hosting.mjs"]
                    case_snapshots = []
                    event_cursor = {"index": 0, "memory": 0}

                    def on_case_line(text: str) -> None:
                        if len(text) > 2200 or "PRIVATE_RENDERER_MEMORY_CANARY" in text:
                            return
                        try:
                            payload = json.loads(text[len("RESOURCE_CASE ") :])
                        except json.JSONDecodeError:
                            return
                        if type(payload) is not dict or type(payload.get("label")) is not str:
                            return
                        with observation_lock:
                            fresh = list(events[event_cursor["index"] :])
                            event_cursor["index"] = len(events)
                            current = memory_counts["successful"]
                            delta = current - event_cursor["memory"]
                            event_cursor["memory"] = current
                        if type(delta) is not int:
                            delta = None
                        case_snapshots.append(
                            {
                                "label": payload["label"],
                                "events": fresh,
                                "memory_successful": delta,
                            }
                        )

                    probe = await asyncio.to_thread(
                        _run_resource_smoke, smoke, copy, smoke_env, 90 * 60, on_case_line
                    )
                    evidence = _load_app_evidence(
                        copy / "build-tmp/telemetry-installed-resources.json", secret
                    )
                    app_cases = {
                        row.get("label"): row
                        for row in evidence.get("cases") or []
                        if isinstance(row, dict) and isinstance(row.get("label"), str)
                    }
                    cases = []
                    diagnostics = False
                    snapshots = {
                        item["label"]: item
                        for item in case_snapshots
                        if type(item.get("label")) is str
                    }
                    for row in resource_counterbalance_cases():
                        owned_path = copy / "build-tmp" / f"{row['label']}-owned-launch.json"
                        raw = {}
                        if owned_path.is_file():
                            text = owned_path.read_text(encoding="utf-8")
                            if secret in text or "PRIVATE_RENDERER_MEMORY_CANARY" in text:
                                raw = {
                                    "private_content_withheld": True,
                                    "resource_acceptance": False,
                                }
                            else:
                                loaded = json.loads(text)
                                raw = loaded if isinstance(loaded, dict) else {}
                        if raw.get("delivery_diagnostics_enabled") is True:
                            diagnostics = True
                        app = app_cases.get(row["label"]) or {}
                        snap = snapshots.get(row["label"]) or {}
                        case_events = snap.get("events") if type(snap.get("events")) is list else []
                        inspected = app.get("inspected_body_hex")
                        if type(inspected) is not str or not _REPORT_HEX.fullmatch(inspected):
                            inspected = None
                        completed = installed_resource_case_completed(
                            {
                                "memory_cycles": app.get("memory_cycles"),
                                "memory_results_verified": app.get("memory_results_verified"),
                                "checkpoints": app.get("checkpoints"),
                                "model_calls": app.get("model_calls"),
                                "resource_acceptance": app.get("resource_acceptance"),
                                "condition": row["condition"],
                                "memory_api_operations": app.get("memory_api_operations"),
                                "telemetry_attempts": app.get("telemetry_attempts"),
                                "telemetry_reserved_bytes": app.get("telemetry_reserved_bytes"),
                                "telemetry_events": case_events,
                                "memory_successful": snap.get("memory_successful"),
                                "inspected_body_hex": inspected,
                            },
                            {
                                "canonical_operations_completed": raw.get(
                                    "canonical_operations_completed"
                                ),
                                "resource_acceptance": raw.get("resource_acceptance"),
                            },
                        )
                        observed = raw.get("canonical_operations_completed")
                        cycles = app.get("memory_cycles")
                        sent = None
                        if len(case_events) == 1 and type(case_events[0]) is dict:
                            body = case_events[0].get("body_hex")
                            if type(body) is str and _REPORT_HEX.fullmatch(body):
                                sent = body
                        agreement = None
                        if inspected is not None and sent is not None:
                            agreement = inspected == sent
                        elif inspected is not None:
                            agreement = False
                        cases.append(
                            {
                                "label": row["label"],
                                "condition": row["condition"],
                                "package": row["package"],
                                "workload_completed": completed,
                                "memory_cycles": cycles if type(cycles) is int else None,
                                "canonical_operations_completed": observed
                                if type(observed) is int
                                else None,
                                "canonical_operations_known": raw.get("canonical_operations_known")
                                if type(raw.get("canonical_operations_known")) is bool
                                else None,
                                "resource_acceptance": False,
                                "telemetry": {
                                    "attempts": app.get("telemetry_attempts")
                                    if type(app.get("telemetry_attempts")) is int
                                    else None,
                                    "reserved_bytes": app.get("telemetry_reserved_bytes")
                                    if type(app.get("telemetry_reserved_bytes")) is int
                                    else None,
                                    "reports": sum(
                                        1
                                        for event in case_events
                                        if type(event) is dict and event.get("malformed") is not True
                                    ),
                                    "malformed": sum(
                                        1
                                        for event in case_events
                                        if type(event) is dict and event.get("malformed") is True
                                    ),
                                    "sent_body_hex": sent,
                                    "inspected_body_hex": inspected,
                                    "body_agreement": agreement,
                                    "memory_successful": snap.get("memory_successful")
                                    if type(snap.get("memory_successful")) is int
                                    else None,
                                },
                                "owned": retain_owned_launch(raw),
                            }
                        )
                    memory_api = {
                        name: value
                        for name, value in dict(memory_counts).items()
                        if type(value) is int
                    }
                    return {
                        "qualification": "installed resource workload",
                        "journey_completed": bool(
                            probe.returncode == 0
                            and len(cases) == 6
                            and all(item["workload_completed"] for item in cases)
                            and not diagnostics
                            and evidence.get("private_content_withheld") is not True
                        ),
                        "workload_completed": bool(
                            len(cases) == 6 and all(item["workload_completed"] for item in cases)
                        ),
                        "resource_acceptance": False,
                        "delivery_compared": False,
                        "production_collection_available": False,
                        "delivery_diagnostics_enabled": diagnostics,
                        "collector": counts,
                        "published_aggregate_count": len(published),
                        "memory_api": memory_api,
                        "smoke_exit": probe.returncode,
                        "source": active_source,
                        "observer_python": Path(observer).name,
                        "runner_arch": runner_arch,
                        "machine": platform.machine(),
                        "packages": {
                            "inactive": {
                                "sha256": manifest["packages"]["inactive"]["sha256"],
                                "condition": "inactive",
                                "engine_label": inactive_label,
                                "disclosure_sha256": inactive_inventory.get(
                                    "diagnostic_disclosure_sha256"
                                ),
                            },
                            "active": {
                                "sha256": manifest["packages"]["active"]["sha256"],
                                "condition": "active",
                                "engine_label": active_label,
                                "disclosure_sha256": active_inventory.get(
                                    "diagnostic_disclosure_sha256"
                                ),
                            },
                        },
                        "cases": cases,
                        "limitations": [
                            "darwin_wait4_direct_child_only",
                            "group_sampling_is_not_complete_cpu",
                            "rss_high_water_is_sampled_and_can_truncate_at_120s",
                            "additional_rss_budget_bytes_8388608_unaccepted",
                            "cpu_budget_one_core_fraction_0.005_unaccepted",
                            "completion_is_not_acceptance",
                            "terminal_count_is_the_verified_count",
                            "unknown_progress_is_explicit",
                            "phase_cpu_is_sampled_descriptive",
                            "lifetime_cpu_is_separate",
                            "windows_product_switch_is_sequential_and_was_not_executed_here",
                        ],
                        "scope": _RESOURCE_SCOPE,
                    }
        finally:
            server.should_exit = True
            await task


def run(source: Path, output: Path, material: Path, *, resource_comparison: bool = False) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32" and (
        os.environ.get("CI") != "true" or os.environ.get("RUNNER_OS") != "Windows"
    ):
        _refuse(
            output,
            "The installed telemetry package is installed only on a disposable Windows CI runner",
            resource=resource_comparison,
        )
    if sys.platform == "win32" and os.environ.get("RUNNER_ARCH", "").upper() == "ARM64":
        if not os.environ.get("MNEMION_ENGINE_ARCHIVES", "").strip():
            _refuse(
                output,
                "Windows ARM requires the same-source diagnostic x64 engine archive",
                resource=resource_comparison,
            )
    if resource_comparison and sys.platform == "win32":
        if not os.environ.get("MNEMION_ENGINE_ARCHIVES_INACTIVE", "").strip():
            _refuse(
                output,
                "Windows resource comparison requires separate active and inactive engine archives",
                resource=True,
            )
    source = source.resolve()
    material = material.resolve()
    try:
        _require_loopback_material(material)
        _key_stays_outside(material / "key.pem", output)
    except Exception as exc:
        _refuse(output, _bounded_error(exc), resource=resource_comparison)
    original = (source / "mnemion/product_telemetry/disclosure.json").read_bytes()
    route_bytes = (source / "mnemion/product_telemetry/transport-route.json").read_bytes()
    receipt = _receipt(
        "Installed resource workload did not start"
        if resource_comparison
        else "Installed fixture delivery did not start",
        resource=resource_comparison,
    )
    try:
        with tempfile.TemporaryDirectory(prefix="mnemion-owned-telemetry-checkout-") as temporary:
            copy = Path(temporary) / "source"
            copy.mkdir()
            try:
                if resource_comparison:
                    receipt = asyncio.run(_serve_resources(copy, output, source, material))
                else:
                    receipt = asyncio.run(_serve(copy, output, source, material))
            except Exception as exc:
                receipt = _receipt(_bounded_error(exc), resource=resource_comparison)
                raise
            finally:
                _preserve_build_notes(copy, output)
                if resource_comparison:
                    _preserve_build_notes(
                        Path(temporary) / "inactive-source", output, "inactive-build-notes"
                    )
                _drop_private_files(output)
                disclosure_now = (source / "mnemion/product_telemetry/disclosure.json").read_bytes()
                route_now = (source / "mnemion/product_telemetry/transport-route.json").read_bytes()
                if disclosure_now != original or route_now != route_bytes:
                    receipt = _receipt(
                        "Production disclosure or route changed during diagnostic staging",
                        resource=resource_comparison,
                    )
                    _write_receipt(output, receipt)
                    raise RuntimeError(
                        "Production disclosure or route changed during diagnostic staging"
                    )
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
    parser.add_argument("--read-resource-store", type=Path)
    parser.add_argument(
        "--resource-comparison",
        action="store_true",
        help="Run the optional installed resource comparison. Omit it to keep all-six delivery.",
    )
    args = parser.parse_args()
    if args.read_resource_store:
        json.dump(read_resource_profile_store(args.read_resource_store), sys.stdout)
        sys.stdout.write("\n")
        return
    if args.read_store:
        secret = sys.stdin.buffer.read()
        json.dump(read_delivery_store(args.read_store, secret), sys.stdout)
        sys.stdout.write("\n")
        return
    if not args.source or not args.output or not args.loopback_material:
        parser.error("--source, --output and --loopback-material are required")
    receipt = run(
        args.source,
        args.output,
        args.loopback_material,
        resource_comparison=args.resource_comparison,
    )
    if not receipt.get("journey_completed"):
        if args.resource_comparison:
            raise SystemExit(
                "Inspect retained observations; installed resource workload did not complete"
            )
        raise SystemExit("Inspect retained observations; installed fixture delivery did not pass")


if __name__ == "__main__":
    main()
