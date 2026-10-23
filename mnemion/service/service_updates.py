"""Operator-controlled staging and compatible hotfixes for a managed service."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from ..version import __version__
from . import supervision
from . import update_state as state_io
from . import runtime_wheels
from .update_cleanup import KEEP_BACKUPS, SLOT, retain_backup, retain_runtimes
from .update_manifest import ManifestError, ServiceRelease, verify_manifest, version_tuple
from .update_packages import copy_inspected_source, verify_installed_package
from .update_transport import UpdateNotPublished, download_artifact, fetch_manifest
from .update_trust import SERVICE_UPDATE_PUBLIC_KEY
from .update_schedule import UpdateSchedule, schedule_status
from .process_transition import (
    START_BUDGET_SECONDS,
    STOP_BUDGET_SECONDS,
    ProcessTransitionError,
    diagnostics as transition_diagnostics,
)

UV_VERSION = "0.12.24"
DEFAULT_INTERVAL = 6 * 60 * 60
MIN_FREE_BYTES = 3 * 1024**3
MAX_COMMAND_LOG_BYTES = 262144


class UpdateInterrupted(BaseException):
    """Supervisor requested shutdown; leave the journal for the next startup."""


def _root(state: Path) -> tuple[Path, Path, dict]:
    state, settings = supervision.settings(state)
    if settings.get("managed_updates") is not True:
        raise ManifestError("Use the managed service setup before enabling server updates")
    root = state_io.directory(state / "updates")
    for name in ("logs", "releases", "backups", "cache", "tools"):
        state_io.directory(root / name)
    return state, root, settings


def _configuration(root: Path) -> dict:
    value = state_io.read(root / "config.json")
    if (
        value.get("format") != 1
        or type(value.get("enabled")) is not bool
        or type(value.get("interval_seconds")) is not int
        or not 900 <= value["interval_seconds"] <= 86400
        or not isinstance(value.get("uv"), str)
    ):
        raise ManifestError("Invalid managed update configuration")
    return value


def _environment(settings: dict | None = None) -> dict[str, str]:
    # Package installation gets no database, API, publisher or model-provider
    # credentials. Network proxy/certificate configuration remains usable.
    allowed = {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "LANG",
        "LC_ALL",
        "TMPDIR",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "NO_PROXY",
        "https_proxy",
        "http_proxy",
        "no_proxy",
        "SYSTEMROOT",
        "WINDIR",
    }
    result = {key: value for key, value in os.environ.items() if key in allowed}
    result.update({"PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    if settings is not None:
        result.update(supervision._environment(settings["environment"]))
    return result


def _command(
    command: list[str],
    *,
    cwd: Path,
    environment: dict,
    log: Path,
    timeout: int,
    retain_operation_locks: bool = True,
) -> bytes:
    """Drain output continuously while retaining only a bounded private tail."""
    import selectors

    tail = bytearray()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        pass_fds=state_io.inherited_locks() if retain_operation_locks else (),
    )

    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    os.set_blocking(process.stdout.fileno(), False)
    deadline = time.monotonic() + timeout
    try:
        while True:
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(command, timeout)
            events = selector.select(0.1)
            if events:
                chunk = os.read(process.stdout.fileno(), 8192)
                if chunk:
                    tail.extend(chunk)
                    del tail[:-MAX_COMMAND_LOG_BYTES]
                elif process.poll() is not None:
                    break
            elif process.poll() is not None:
                break
        failed = process.wait(timeout=5) != 0
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        raise
    finally:
        selector.close()
        process.stdout.close()
        descriptor, name = tempfile.mkstemp(prefix=".command-", dir=log.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(tail)
            os.replace(temporary, log)
        finally:
            temporary.unlink(missing_ok=True)
    if failed:
        raise ManifestError("A managed update command failed; inspect its private bounded log")
    return bytes(tail)


def _models(runtime: dict, settings: dict, root: Path) -> list[str]:
    output = _command(
        [
            runtime["python"],
            *(["-I"] if runtime.get("isolated") else []),
            "-m",
            "mnemion.service.cli",
            "models",
        ],
        cwd=Path(runtime["directory"]),
        environment=_environment(settings),
        log=root / "logs/models.log",
        timeout=60,
    )
    try:
        value = json.loads(output)["profiles"]
        if not isinstance(value, list) or len(value) > 100:
            raise ValueError("catalog")
        return sorted({item["generation_id"] for item in value})
    except (ValueError, KeyError, TypeError):
        raise ManifestError("Cannot inspect the candidate's embedding generations") from None


def _target(dsn: str) -> tuple:
    from psycopg.conninfo import conninfo_to_dict

    value = conninfo_to_dict(dsn)
    if value.get("service") or not value.get("dbname"):
        raise ManifestError("Managed update database URLs need an explicit database target")
    return tuple(
        value.get(key, default)
        for key, default in (
            ("host", ""),
            ("hostaddr", ""),
            ("port", "5432"),
            ("dbname", ""),
        )
    )


def setup(
    state: Path,
    api: Path,
    worker: Path,
    admin: Path,
    *,
    uv: Path | None = None,
    pg_bin: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 7892,
    public_url: str | None = None,
    environment: Path | None = None,
    connector_configs: tuple[Path, ...] = (),
    inherit_environment: bool = True,
) -> dict:
    """One explicit host adoption; new managed installations update by default."""
    state = state.expanduser().absolute()
    if state.exists() and any(state.iterdir()):
        raise ManifestError("Use a new empty managed state directory; existing hosts are preserved")
    owner = state_io.read(admin).get("admin_database_url")
    api_url = state_io.read(api).get("database_url")
    worker_url = state_io.read(worker).get("worker_database_url")
    if not all(
        isinstance(value, str) and 0 < len(value) <= 16384 for value in (owner, api_url, worker_url)
    ):
        raise ManifestError("Provide private API, worker and admin database credential files")
    if _target(owner) != _target(api_url) or _target(owner) != _target(worker_url):
        raise ManifestError("Update backup and service roles must use the same database target")
    selected_uv = str(uv.expanduser().absolute()) if uv else shutil.which("uv")
    if not selected_uv:
        raise ManifestError(f"Install the free uv {UV_VERSION} package manager before adoption")
    try:
        version = subprocess.run(
            [selected_uv, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
            env=_environment(),
        ).stdout.split()
    except (OSError, subprocess.SubprocessError):
        raise ManifestError("Cannot run the selected uv package manager") from None
    if len(version) < 2 or version[:2] != ["uv", UV_VERSION]:
        raise ManifestError(f"Managed service updates currently require uv {UV_VERSION}")
    # Validate backup tools and the current schema before adding host state.
    from .recovery import _pg_tool
    import psycopg

    _pg_tool("pg_dump", pg_bin)
    with psycopg.connect(owner, connect_timeout=5) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout='10s'")
        schema = dict(
            connection.execute("SELECT name, sha256 FROM mnemion.schema_migrations").fetchall()
        )
    if schema != state_io.local_migrations():
        raise ManifestError(
            "The existing database must match the installed service before adoption"
        )
    with state_io.adoption(state):
        prepared = supervision.prepare(
            state,
            api,
            worker,
            host=host,
            port=port,
            public_url=public_url,
            environment=environment,
            managed_updates=True,
            connector_configs=connector_configs,
            inherit_environment=inherit_environment,
        )
        state, root, settings = _root(state)
        for child in ("logs", "releases", "backups", "cache", "tools"):
            state_io.directory(root / child)
        # Keep the reviewed installer available when an operator upgrades their
        # ordinary uv command. This is an ordinary executable copy, not a new service.
        uv_source = Path(selected_uv).resolve()
        if not uv_source.is_file() or not 0 < uv_source.stat().st_size <= 128 * 1024 * 1024:
            raise ManifestError("The selected uv executable is missing or exceeds its size budget")
        pinned_uv = root / "tools/uv"
        with pinned_uv.open("xb") as destination, uv_source.open("rb") as source:
            shutil.copyfileobj(source, destination, length=1024 * 1024)
        pinned_uv.chmod(0o700)
        state_io.write(root / "owner.json", {"admin_database_url": owner}, replace=False)
        from ..connectors.runner import HEADLESS_CAPTURE_PROTOCOL, MANAGED_PROTOCOL

        runtime = {
            "version": __version__,
            "readiness_protocol": supervision.READINESS_PROTOCOL,
            "connector_protocol": MANAGED_PROTOCOL,
            "capture_protocol": HEADLESS_CAPTURE_PROTOCOL,
            "python": settings["python"],
            "directory": settings["directory"],
            "isolated": False,
            "migrations": schema,
            "slot": None,
        }
        runtime["generations"] = _models(runtime, settings, root)
        state_io.write(root / "active.json", runtime, replace=False)
        state_io.write(
            root / "config.json",
            {
                "format": 1,
                "enabled": True,
                "interval_seconds": DEFAULT_INTERVAL,
                "uv": str(pinned_uv),
                "pg_bin": str(pg_bin.absolute()) if pg_bin else None,
                "python": settings["python"],
                "baseline": runtime,
            },
            replace=False,
        )
        state_io.record(root, "configured", version=__version__, enabled=True)
        return {
            **prepared,
            "automatic_updates": True,
            "schema_policy": "identical",
            "backup_before_restart": True,
        }


def _release(root: Path) -> ServiceRelease:
    content = state_io.read(root / "candidate.json")
    try:
        import base64

        return verify_manifest(
            base64.b64decode(content["envelope"], validate=True), SERVICE_UPDATE_PUBLIC_KEY
        )
    except (KeyError, ValueError, TypeError):
        raise ManifestError("The staged service release has no valid publisher signature") from None


def _slot(root: Path, release: ServiceRelease) -> Path:
    return root / "releases" / f"{release.version}-{release.commit[:12]}"


def compatible_version(previous: str, candidate: str) -> bool:
    """Stable minor releases retain their major API contract; 0.x stays narrow.

    This classifies versions only. Callers still require a newer signed runtime,
    identical migrations and model generations, and verified backup/readiness.
    """
    before, after = version_tuple(previous), version_tuple(candidate)
    return before[0] == after[0] and (before[0] != 0 or before[1] == after[1])


def _automatic_compatible(previous: dict, candidate: dict) -> bool:
    return (
        candidate["migrations"] == previous["migrations"]
        and candidate["generations"] == previous["generations"]
        and compatible_version(previous["version"], candidate["version"])
    )


def check(state: Path) -> dict:
    state, root, settings = _root(state)
    with state_io.lock(root):
        return _check(root)


def _check(root: Path) -> dict:
    import base64

    active = state_io.read(root / "active.json")
    try:
        envelope = fetch_manifest()
    except UpdateNotPublished:
        result = {"status": "not_published", "current_version": active["version"]}
    else:
        release = verify_manifest(envelope, SERVICE_UPDATE_PUBLIC_KEY)
        seen = (
            state_io.read(root / "seen.json")
            if (root / "seen.json").exists()
            else {"version": active["version"]}
        )
        high = seen["version"]
        digest = hashlib.sha256(envelope).hexdigest()
        if version_tuple(release.version) < version_tuple(high):
            raise ManifestError("The service feed attempted to replay an older verified release")
        if release.version == high and seen.get("manifest_sha256", digest) != digest:
            raise ManifestError("The service feed changed an already verified immutable version")
        if not release.is_newer_than(active["version"]):
            result = {"status": "current", "current_version": active["version"]}
        else:
            state_io.write(
                root / "candidate.json", {"envelope": base64.b64encode(envelope).decode()}
            )
            state_io.write(
                root / "seen.json", {"version": release.version, "manifest_sha256": digest}
            )
            result = {
                "status": "available",
                "current_version": active["version"],
                "available_version": release.version,
                "schema_compatible": dict(release.migrations) == active["migrations"],
                "version_compatible": compatible_version(active["version"], release.version),
            }
            if not (result["schema_compatible"] and result["version_compatible"]):
                from .managed_upgrade import pending_update

                result.update(pending_update(active, release))
    state_io.write(root / "last-check.json", {**result, "checked_at": state_io.timestamp()})
    return result


def _validate_python(release: ServiceRelease) -> None:
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    if version not in release.python_versions:
        raise ManifestError("This service update requires a different Python installation")
    if (
        platform.system() == "Darwin"
        and platform.machine() == "x86_64"
        and sys.version_info >= (3, 14)
    ):
        raise ManifestError("Intel Mac service deployments currently require Python 3.12 or 3.13")


def stage(state: Path) -> dict:
    state, root, settings = _root(state)
    with state_io.lock(root):
        if (root / "upgrade-journal.json").exists():
            raise ManifestError(
                "Resume the pending managed schema upgrade before staging another release"
            )
        return _stage(root, settings)


def _stage(root: Path, settings: dict) -> dict:
    release = _release(root)
    active = state_io.read(root / "active.json")
    if not release.is_newer_than(active["version"]):
        raise ManifestError("Only a newer signed stable release can be staged")
    _validate_python(release)
    slot = _slot(root, release)
    receipt = slot / "ready.json"
    if receipt.exists():
        return {
            "status": "staged",
            "version": release.version,
            # Eligibility belongs to the current runtime and policy, not a
            # cached decision made before another update or by an older client.
            # Apply re-verifies installed bytes and live models before stopping.
            "automatic_compatible": _automatic_compatible(
                active, state_io.read(receipt)["runtime"]
            ),
        }
    # Remove only authenticated, obsolete managed slots. Operator files and
    # both runtimes in a recovery journal are always preserved.
    retain_runtimes(root, SERVICE_UPDATE_PUBLIC_KEY, pending=slot.name)
    if shutil.disk_usage(root).free < MIN_FREE_BYTES:
        raise ManifestError(
            "Staging needs at least 3 GiB free for packages and the isolated runtime"
        )
    config = _configuration(root)
    state_io.directory(slot)
    envelope = state_io.read(root / "candidate.json")
    if (slot / "envelope.json").exists():
        if state_io.read(slot / "envelope.json") != envelope:
            raise ManifestError("The pending runtime's immutable release identity changed")
    else:
        state_io.write(slot / "envelope.json", envelope, replace=False)
    artifacts = state_io.directory(slot / "artifacts")
    native_wheels = runtime_wheels.selected_wheels(release)
    for artifact in (*release.artifacts, *native_wheels):
        download_artifact(release.version, artifact, artifacts / artifact.name)
    source = slot / "source"
    if source.exists():
        # Only a previous incomplete staging tree in this exact private slot.
        if source.is_symlink():
            raise ManifestError("Service staging source cannot be a symbolic link")
        shutil.rmtree(source)
    copy_inspected_source(artifacts, release, source)
    for artifact in native_wheels:
        runtime_wheels.inspect_wheel(artifacts / artifact.name, artifact, source / "uv.lock")
    environment = _environment()
    environment.update(
        {
            "UV_PROJECT_ENVIRONMENT": str(slot / "venv"),
            "UV_CACHE_DIR": str(root / "cache"),
            "UV_CONCURRENT_DOWNLOADS": "2",
            "UV_CONCURRENT_BUILDS": "1",
            "UV_CONCURRENT_INSTALLS": "2",
            "UV_NO_PROGRESS": "1",
            "UV_NO_CONFIG": "1",
            "UV_PYTHON_DOWNLOADS": "never",
        }
    )
    _command(
        [
            config["uv"],
            "sync",
            "--locked",
            "--no-dev",
            "--extra",
            "supervision",
            "--no-install-project",
            "--no-build",
            *(["--no-install-package", "cryptography"] if native_wheels else []),
            "--no-python-downloads",
            "--python",
            config["python"],
        ],
        cwd=source,
        environment=environment,
        log=root / "logs/dependencies.log",
        timeout=1200,
    )
    python = slot / "venv/bin/python"
    _command(
        [
            config["uv"],
            "pip",
            "install",
            "--python",
            str(python),
            "--no-deps",
            "--no-index",
            str(artifacts / f"mnemion-{release.version}-py3-none-any.whl"),
            *(str(artifacts / artifact.name) for artifact in native_wheels),
        ],
        cwd=source,
        environment=environment,
        log=root / "logs/package.log",
        timeout=120,
    )
    runtime = {
        "version": release.version,
        "python": str(python),
        "directory": str(slot),
        "isolated": True,
        "migrations": dict(release.migrations),
        "slot": slot.name,
    }
    runtime["generations"] = _models(runtime, settings, root)
    # Inspect the installed package without opening a listener or calling a model.
    code = (
        "import json,mnemion; from pathlib import Path; from mnemion.version import __version__; "
        "from mnemion.service.studio import resolve_studio; "
        "from mnemion.service import supervision as lifecycle; "
        "from mnemion.connectors import runner as connector; "
        "from mnemion.service.update_state import local_migrations; "
        "p,s=resolve_studio(); print(json.dumps({'version':__version__,'studio':p is not None,'migrations':local_migrations(),'package':str(Path(mnemion.__file__).parent),'readiness_protocol':getattr(lifecycle,'READINESS_PROTOCOL',0),'connector_protocol':getattr(connector,'MANAGED_PROTOCOL',0),'capture_protocol':getattr(connector,'HEADLESS_CAPTURE_PROTOCOL',0)}))"
    )
    output = _command(
        [str(python), "-I", "-c", code],
        cwd=slot,
        environment=_environment(),
        log=root / "logs/preflight.log",
        timeout=60,
    )
    try:
        preflight = json.loads(output)
        package = Path(preflight.pop("package"))
        protocol = preflight.pop("readiness_protocol")
        connector_protocol = preflight.pop("connector_protocol", 0)
        capture_protocol = preflight.pop("capture_protocol", 0)
        if type(protocol) is not int or protocol not in {0, supervision.READINESS_PROTOCOL}:
            raise ValueError("readiness protocol")
        if type(connector_protocol) is not int or connector_protocol not in {0, 1}:
            raise ValueError("connector protocol")
        if type(capture_protocol) is not int or capture_protocol not in {0, 1}:
            raise ValueError("capture protocol")
        if not package.resolve().is_relative_to((slot / "venv").resolve()):
            raise ValueError("package location")
        if preflight != {
            "version": release.version,
            "studio": True,
            "migrations": dict(release.migrations),
        }:
            raise ValueError("preflight")
    except (ValueError, TypeError):
        raise ManifestError("The installed runtime did not pass its offline preflight") from None
    runtime["package"] = str(package)
    runtime["readiness_protocol"] = protocol
    runtime["connector_protocol"] = connector_protocol
    runtime["capture_protocol"] = capture_protocol
    verify_installed_package(artifacts, release, package)
    runtime_wheels.verify_installed(artifacts, release, package, source / "uv.lock")
    compatible = _automatic_compatible(active, runtime)
    state_io.write(receipt, {"runtime": runtime, "automatic_compatible": compatible}, replace=False)
    state_io.record(root, "staged", version=release.version, automatic_compatible=compatible)
    return {"status": "staged", "version": release.version, "automatic_compatible": compatible}


def resolved_runtime(state: Path, *, runtime: dict | None = None) -> dict:
    """Only a configured baseline or a verified package can become executable."""
    _, root, _ = _root(state)
    runtime = runtime or state_io.read(root / "active.json")
    if runtime.get("slot") is None:
        if runtime != _configuration(root)["baseline"]:
            raise ManifestError("The original managed runtime configuration was modified")
        return runtime
    import base64

    slot_name = runtime.get("slot")
    if not isinstance(slot_name, str) or not SLOT.fullmatch(slot_name):
        raise ManifestError("Invalid managed runtime slot")
    slot = state_io.directory(root / "releases" / slot_name)
    envelope = state_io.read(slot / "envelope.json")
    release = verify_manifest(
        base64.b64decode(envelope["envelope"], validate=True), SERVICE_UPDATE_PUBLIC_KEY
    )
    if (
        slot != _slot(root, release)
        or runtime != state_io.read(slot / "ready.json")["runtime"]
        or runtime["version"] != release.version
        or runtime["migrations"] != dict(release.migrations)
        or runtime["python"] != str(slot / "venv/bin/python")
        or runtime["directory"] != str(slot)
        or runtime["isolated"] is not True
    ):
        raise ManifestError("Managed runtime does not match its verified staging record")
    package = Path(runtime["package"])
    if not package.resolve().is_relative_to((slot / "venv").resolve()):
        raise ManifestError("Managed application is outside its isolated environment")
    verify_installed_package(slot / "artifacts", release, package)
    runtime_wheels.verify_installed(slot / "artifacts", release, package, slot / "source/uv.lock")
    return runtime


def status(state: Path) -> dict:
    from ..connectors.managed import status as connector_status

    state, root, settings = _root(state)
    config = _configuration(root)
    active = state_io.read(root / "active.json")
    last_check = (
        state_io.read(root / "last-check.json") if (root / "last-check.json").exists() else None
    )
    from .managed_upgrade import pending_update, upgrade_status

    pending = pending_update(active, _release(root)) if (root / "candidate.json").exists() else None
    failed = state_io.read(root / "failed.json") if (root / "failed.json").exists() else None
    return {
        "enabled": config["enabled"],
        "current_version": active["version"],
        "interval_seconds": config["interval_seconds"],
        "version_policy": "same_major",
        "schema_policy": "identical",
        "retained_backups": KEEP_BACKUPS,
        "recovery_pending": (root / "journal.json").exists()
        or (root / "upgrade-journal.json").exists(),
        "pending_update": pending,
        "upgrade": upgrade_status(root),
        "last_check": last_check,
        "last_failure": (
            {
                "version": failed.get("version"),
                "at": failed.get("at"),
                "transition": transition_diagnostics(failed.get("transition")),
            }
            if failed is not None
            else None
        ),
        **schedule_status(
            root,
            enabled=config["enabled"],
            interval=config["interval_seconds"],
            last_check=last_check,
        ),
        "events": state_io.read(root / "history.json").get("events", []),
        "supervision": supervision.status(state),
        "connectors": connector_status(root),
    }


def preferences(state: Path, enabled: bool) -> dict:
    _, root, _ = _root(state)
    with state_io.lock(root):
        config = _configuration(root)
        config["enabled"] = enabled
        state_io.write(root / "config.json", config)
        state_io.record(root, "preferences", enabled=enabled)
    return {"enabled": enabled}


def _processes(
    state: Path, *, start: bool, updater_only: bool = False, service_only: bool = False
) -> None:
    """Operate only the two known service children, keeping the updater alive."""
    import xmlrpc.client

    _, settings = supervision.settings(state)
    names = ("mnemion-updater",) if updater_only else ("mnemion-api", "mnemion-worker")
    # Cold imports and initialization on a busy host need more time than the
    # supervisor's RUNNING state. Keep every readiness/identity check and a
    # finite bound; a process surviving startup alone never permits cutover.
    deadline = time.monotonic() + (START_BUDGET_SECONDS if start else STOP_BUDGET_SECONDS)
    transition_error = "The managed service did not complete its requested process transition"
    observation = {}
    # A busy supervisor can miss the short socket deadline during a restart.
    # Reconnect with fresh identity checks inside the original transition budget.
    # These named start/stop requests are idempotent, including a lost reply.
    while time.monotonic() < deadline:
        try:
            with supervision._rpc(settings) as client:
                for name in names:
                    try:
                        if start:
                            client.supervisor.startProcess(name, False)
                        else:
                            client.supervisor.stopProcess(name, False)
                    except xmlrpc.client.Fault as error:
                        if error.faultCode != (60 if start else 70):
                            raise
            break
        except TimeoutError:
            time.sleep(0.25)
    else:
        raise ProcessTransitionError(transition_error, reason="request_timeout", start=start)
    while time.monotonic() < deadline:
        try:
            with supervision._rpc(settings) as client:
                processes = {item["name"]: item for item in client.supervisor.getAllProcessInfo()}
            observation = {"processes": list(processes.values())}
            if not set(names).issubset(processes):
                raise ProcessTransitionError(
                    "The managed supervisor is missing a service child",
                    reason="missing_child",
                    start=start,
                    observation=observation,
                )
            if start:
                if any(processes[name]["statename"] == "FATAL" for name in names):
                    raise ProcessTransitionError(
                        "A service child could not start after the update",
                        reason="child_failed",
                        start=start,
                        observation=observation,
                    )
                observation = supervision.status(state)
                if observation["service_ready" if service_only else "ready"]:
                    return
            elif all(
                processes[name]["statename"] in {"STOPPED", "EXITED", "FATAL"} for name in names
            ):
                return
        except TimeoutError:
            pass
        time.sleep(0.25)
    raise ProcessTransitionError(
        transition_error,
        reason="readiness_timeout" if start else "stop_timeout",
        start=start,
        observation=observation,
    )


def _backup(
    root: Path,
    settings: dict,
    previous: dict,
    release: ServiceRelease,
    *,
    allow_migration: bool = False,
) -> str:
    from uuid import uuid4
    import psycopg

    config = _configuration(root)
    owner = state_io.read(root / "owner.json")["admin_database_url"]
    if _target(owner) != _target(
        state_io.read(root.parent / "api.json")["database_url"]
    ) or _target(owner) != _target(
        state_io.read(root.parent / "worker.json")["worker_database_url"]
    ):
        raise ManifestError("Backup and runtime credentials no longer target the same database")
    with psycopg.connect(owner, connect_timeout=5) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout='10s'")
        schema = dict(
            connection.execute("SELECT name, sha256 FROM mnemion.schema_migrations").fetchall()
        )
        size = connection.execute("SELECT pg_database_size(current_database())").fetchone()[0]
    if schema != previous["migrations"] or (
        not allow_migration and schema != dict(release.migrations)
    ):
        raise ManifestError("Database schema changed; automatic cutover is not permitted")
    if shutil.disk_usage(root).free < max(MIN_FREE_BYTES, size * 2):
        raise ManifestError("There is not enough free disk space for a verified pre-update backup")
    name = f"pre-update-{previous['version']}-to-{release.version}-{uuid4().hex}.zip"
    output = root / "backups" / name
    environment = _environment()
    environment["MNEMION_ADMIN_DATABASE_URL"] = owner
    if config["pg_bin"]:
        environment["MNEMION_PG_BIN"] = config["pg_bin"]
    _command(
        [
            previous["python"],
            *(["-I"] if previous.get("isolated") else []),
            "-m",
            "mnemion.service.cli",
            "backup",
            "--output",
            str(output),
        ],
        cwd=Path(previous["directory"]),
        environment=environment,
        log=root / "logs/backup.log",
        timeout=3600,
    )
    # The backup command already verifies before publishing. Independently
    # inspect its archive here before stopping any running service process.
    from ..archives import verified_archive
    from .recovery import BACKUP_FORMAT

    with verified_archive(output, BACKUP_FORMAT):
        pass
    retain_backup(root, name)
    return name


def _rollback(state: Path, root: Path, journal: dict) -> None:
    previous = resolved_runtime(state, runtime=journal["previous"])
    _processes(state, start=False)
    state_io.write(root / "active.json", previous)
    _processes(state, start=True)
    state_io.write(
        root / "failed.json",
        {
            "version": journal["candidate"]["version"],
            "at": state_io.timestamp(),
            "transition": transition_diagnostics(journal.get("transition")),
        },
    )
    state_io.record(
        root,
        "rolled_back",
        version=journal["candidate"]["version"],
        running_version=previous["version"],
        database_restored=False,
    )
    (root / "journal.json").unlink()


def _recover(state: Path, root: Path) -> None:
    path = root / "journal.json"
    if not path.exists():
        return
    journal = state_io.read(path)
    if journal.get("phase") not in {"prepared", "switching", "starting"}:
        raise ManifestError("The managed update recovery journal needs operator review")
    # All automatically applied updates require the same schema and generation
    # identities. Restore the known runtime only; never roll a database backwards.
    if (
        journal["previous"]["migrations"] != journal["candidate"]["migrations"]
        or journal["previous"]["generations"] != journal["candidate"]["generations"]
    ):
        raise ManifestError("An incompatible update journal requires explicit operator recovery")
    _rollback(state, root, journal)


def apply(state: Path, *, retry: bool = False) -> dict:
    state, root, settings = _root(state)
    with state_io.lock(root):
        if (root / "upgrade-journal.json").exists():
            raise ManifestError("Resume the pending managed schema upgrade before applying a patch")
        _recover(state, root)
        result = _apply(state, root, settings, retry=retry)
    if result["status"] == "updated":
        # Manual application also advances the updater itself. The unattended
        # watcher exits after success and Supervisor performs this handoff.
        try:
            _processes(state, start=False, updater_only=True)
            _processes(state, start=True, updater_only=True)
        except Exception:
            state_io.record(root, "updater_restart_failed", version=result["version"])
            raise ManifestError(
                "The service updated, but its updater needs a supervisor restart"
            ) from None
    return result


def _apply(state: Path, root: Path, settings: dict, *, retry: bool = False) -> dict:
    release = _release(root)
    previous = resolved_runtime(state)
    if not release.is_newer_than(previous["version"]):
        raise ManifestError(
            "The managed service will not reinstall or downgrade its current version"
        )
    slot = _slot(root, release)
    receipt = state_io.read(slot / "ready.json")
    candidate = resolved_runtime(state, runtime=receipt["runtime"])
    if not _automatic_compatible(previous, candidate):
        return {
            "status": "operator_required",
            "version": release.version,
            "reason": "schema_or_model_generation_changed",
        }
    failed = state_io.read(root / "failed.json") if (root / "failed.json").exists() else {}
    if failed.get("version") == release.version and not retry:
        return {"status": "held_after_failure", "version": release.version}
    if not supervision.status(state)["running"]:
        raise ManifestError("Start the managed supervisor before applying an update")
    # Re-read live profile configuration; a file can change since staging.
    if _models(candidate, settings, root) != _models(previous, settings, root):
        return {
            "status": "operator_required",
            "version": release.version,
            "reason": "model_configuration_changed",
        }
    backup = _backup(root, settings, previous, release)
    journal = {
        "phase": "prepared",
        "previous": previous,
        "candidate": candidate,
        "backup": backup,
        "at": state_io.timestamp(),
    }
    state_io.write(root / "journal.json", journal)
    try:
        _processes(state, start=False)
        journal["phase"] = "switching"
        state_io.write(root / "journal.json", journal)
        state_io.write(root / "active.json", candidate)
        journal["phase"] = "starting"
        state_io.write(root / "journal.json", journal)
        _processes(state, start=True)
    except Exception as error:
        # A supervisor shutdown or a failed rollback leaves the journal intact
        # for restart recovery. No database archive is restored here.
        if isinstance(error, ProcessTransitionError):
            journal["transition"] = error.diagnostics
        try:
            state_io.write(root / "journal.json", journal)
        finally:
            # An evidence write failure must not prevent runtime recovery.
            _rollback(state, root, journal)
        raise ManifestError(
            "The update failed; the previous service runtime was restored"
        ) from None
    state_io.write(root / "previous.json", previous)
    state_io.record(
        root,
        "updated",
        from_version=previous["version"],
        version=release.version,
        backup=backup,
        database_restored=False,
    )
    (root / "journal.json").unlink()
    return {
        "status": "updated",
        "from_version": previous["version"],
        "version": release.version,
        "backup": backup,
        "database_restored": False,
    }


def watch(state: Path) -> int:
    state, root, settings = _root(state)

    def shutdown(*_):
        raise UpdateInterrupted()

    previous_handlers = {
        sig: signal.signal(sig, shutdown) for sig in (signal.SIGTERM, signal.SIGINT)
    }
    try:
        schedule = UpdateSchedule(root, clock=time)
        schedule.after(random.uniform(60, 120), reason="startup")
        while True:
            config = _configuration(root)
            if (root / "upgrade-journal.json").exists():
                # An operator-owned migration may change the live schema. Its
                # explicit recovery command must finish before patch automation.
                return 1
            if not config["enabled"]:
                state_io.clear_connector_pause(root)
            if (root / "journal.json").exists():
                try:
                    with state_io.lock(root):
                        _recover(state, root)
                except state_io.OperationBusy:
                    # A manual operation may own the journal/lock. Retry after
                    # it releases ownership instead of exhausting Supervisor.
                    time.sleep(10)
                    continue
                except Exception as error:
                    # Keep the journal for operator review and avoid an endless
                    # silent retry. This bounded summary contains no DB secrets.
                    with state_io.lock(root):
                        state_io.record(
                            root,
                            "recovery_required",
                            detail=str(error)
                            if isinstance(error, ManifestError)
                            else "Inspect the private recovery journal before retrying",
                        )
                    return 1
            if config["enabled"] and schedule.due():
                try:
                    with state_io.lock(root):
                        state_io.clear_connector_pause(root)
                        schedule.attempt()
                        result = _check(root)
                        if result["status"] == "available" and not (
                            result["schema_compatible"] and result["version_compatible"]
                        ):
                            state_io.record(
                                root,
                                "operator_required",
                                version=result["available_version"],
                                reason="version_or_schema_changed",
                            )
                        elif result["status"] == "available":
                            staged = _stage(root, settings)
                            if staged["automatic_compatible"]:
                                outcome = _apply(state, root, settings)
                                if outcome["status"] == "updated":
                                    # Supervisor starts a fresh updater using the
                                    # newly verified runtime on its next launch.
                                    return 0
                except state_io.OperationBusy:
                    # Managed connector scans share the operation lease. Retry
                    # shortly after a complete scan, rather than losing a whole
                    # six-hour update window or interrupting source ingestion.
                    state_io.pause_new_connector_scans(root)
                    schedule.after(30, reason="operation_busy")
                    time.sleep(5)
                    continue
                except Exception as error:
                    # The bounded private logs retain diagnostics. Public state
                    # never serializes arbitrary provider/subprocess exceptions.
                    try:
                        with state_io.lock(root):
                            state_io.record(
                                root,
                                "check_failed",
                                detail=str(error)
                                if isinstance(error, ManifestError)
                                else "Inspect private update logs",
                            )
                    except ManifestError:
                        pass
                schedule.after(
                    config["interval_seconds"] * random.uniform(0.9, 1.1), reason="periodic"
                )
            time.sleep(10)
    except UpdateInterrupted:
        return 0
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)


def arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "action",
        choices=(
            "setup",
            "status",
            "check",
            "stage",
            "apply",
            "plan",
            "upgrade",
            "preferences",
            "watch",
        ),
    )
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--api-credentials", type=Path)
    parser.add_argument("--worker-credentials", type=Path)
    parser.add_argument("--admin-credentials", type=Path)
    parser.add_argument("--environment", type=Path)
    parser.add_argument("--connector-config", type=Path, action="append", default=[])
    parser.add_argument("--uv", type=Path)
    parser.add_argument("--pg-bin", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7892)
    parser.add_argument("--public-url")
    parser.add_argument("--enabled", choices=("true", "false"))
    parser.add_argument("--retry", action="store_true")
    parser.add_argument("--version", help="Exact signed target version for an operator upgrade")
    parser.add_argument(
        "--allow-migration",
        action="store_true",
        help="Authorize the planned schema/minor-version upgrade",
    )
    parser.add_argument("--resume", action="store_true", help="Resume a journaled operator upgrade")
    parser.add_argument(
        "--wait-for-turn",
        type=int,
        default=60,
        metavar="SECONDS",
        help="Plan/upgrade: wait 0–300 seconds for existing scans; default 60",
    )


def execute(args: argparse.Namespace) -> int:
    try:
        if args.action == "setup":
            if any(
                path is None
                for path in (args.api_credentials, args.worker_credentials, args.admin_credentials)
            ):
                raise ManifestError(
                    "Managed setup requires private API, worker and admin credential files"
                )
            result = setup(
                args.state_dir,
                args.api_credentials,
                args.worker_credentials,
                args.admin_credentials,
                uv=args.uv,
                pg_bin=args.pg_bin,
                host=args.host,
                port=args.port,
                public_url=args.public_url,
                environment=args.environment,
                connector_configs=tuple(args.connector_config),
            )
        elif args.action == "watch":
            return watch(args.state_dir)
        elif args.action == "preferences":
            if args.enabled is None:
                raise ManifestError("Choose --enabled true or --enabled false")
            result = preferences(args.state_dir, args.enabled == "true")
        elif args.action == "apply":
            result = apply(args.state_dir, retry=args.retry)
        elif args.action in {"plan", "upgrade"}:
            from .managed_upgrade import plan, upgrade

            result = (
                plan(args.state_dir, wait_seconds=args.wait_for_turn)
                if args.action == "plan"
                else upgrade(
                    args.state_dir,
                    version=args.version,
                    allow_migration=args.allow_migration,
                    resume=args.resume,
                    wait_seconds=args.wait_for_turn,
                )
            )
        else:
            result = {"status": status, "check": check, "stage": stage}[args.action](args.state_dir)
        print(json.dumps(result))
        return 0
    except state_io.OperationBusy:
        print(
            json.dumps(
                {
                    "status": "deferred",
                    "reason": "operation_in_progress",
                    "retry_after_seconds": 30,
                    "message": "The updater or a managed source scan is busy; retry shortly. Status remains available.",
                }
            )
        )
        return 75
    except Exception as error:
        message = (
            str(error)
            if isinstance(error, ManifestError)
            else "Managed service update failed; inspect private settings and logs"
        )
        print(json.dumps({"error": message}), file=sys.stderr)
        return 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    arguments(parser)
    return execute(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
