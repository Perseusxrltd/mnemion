"""Run complete source scans using a local managed service's verified runtime."""

from __future__ import annotations

import json
from datetime import datetime
from itertools import islice
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time
from uuid import UUID

import psutil

from .. import process_identity
from ..service import service_updates, supervision, update_state
from ..service.update_manifest import ManifestError, version_tuple
from ..version import __version__
from .config import read_config
from .provenance import git_commit
from .runner import SCAN_REPORT_ENV, SCAN_TRIGGER_ENV, scan_trigger, wait_for_sync

MAX_CONNECTORS = 64
STATES = {"starting", "scanning", "waiting", "waiting_for_update", "service_unavailable", "stopped"}


class Stopped(Exception):
    """A normal operator stop; never leave a scan child behind."""


class Handoff(Exception):
    def __init__(self, runtime: dict, trigger: str = "startup"):
        self.runtime = runtime
        self.trigger = trigger


class Control:
    def __init__(self):
        self.stopped = False

    def stop(self, *_):
        self.stopped = True

    def sleep(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.stopped:
                raise Stopped()
            time.sleep(min(0.25, max(0, deadline - time.monotonic())))
        if self.stopped:
            raise Stopped()


def _alive(identity) -> bool:
    try:
        process = psutil.Process(identity["pid"])
        return (
            process.uids().real == os.getuid()
            and process.status() != psutil.STATUS_ZOMBIE
            and process_identity.matches(identity, process)
        )
    except (KeyError, TypeError, ValueError, OSError, psutil.Error):
        return False


def status(root: Path) -> dict:
    """Bounded host-local observations, without provider paths or credentials."""
    registry = root / "connectors"
    if not registry.exists():
        return {"items": [], "unmanaged_processes_included": False}
    update_state.directory(registry)
    entries = []
    for entry in registry.iterdir():
        if len(entries) >= MAX_CONNECTORS:
            raise ManifestError("Managed connector inventory exceeds its host limit")
        try:
            identifier = str(UUID(entry.name))
        except ValueError:
            raise ManifestError("Unexpected file in managed connector state") from None
        update_state.directory(entry)
        row = {"connector_id": identifier, "state": "unavailable", "running": False}
        if (entry / "status.json").exists():
            value = update_state.read(entry / "status.json")
            if value.get("state") not in STATES or value.get("connector_id") != identifier:
                raise ManifestError("Invalid managed connector observation")
            for key in ("launcher_version", "scan_version"):
                if value.get(key) is not None:
                    version_tuple(value[key])
            running = _alive(value.get("process_identity"))
            scan_running = _alive(value.get("scan_identity"))
            commit = git_commit("git:" + str(value.get("scanned_commit", "")))
            row.update(
                state=value["state"] if running else "orphan_scan" if scan_running else "stopped",
                running=running,
                scan_running=scan_running,
                launcher_version=value["launcher_version"],
                scan_version=value.get("scan_version"),
                updated_at=value["updated_at"],
                last_exit_code=value.get("last_exit_code"),
                scanned_commit=commit,
                scanned_at=value.get("scanned_at") if commit else None,
            )
        entries.append(row)
    return {
        "items": sorted(entries, key=lambda row: row["connector_id"]),
        "unmanaged_processes_included": False,
    }


def _configuration(path: Path, identifier: str | None = None):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ManifestError("Use a private regular connector configuration owned by this account")
    config = read_config(path)
    if identifier is not None and str(config.connector_id) != identifier:
        raise ManifestError("Stop and restart managed mode before changing the connector identity")
    return config


def _environment(config) -> dict[str, str]:
    # Keep the operator's Git/SSH/proxy and referenced provider configuration,
    # but do not give the source runner a database or memory-owner login.
    blocked = supervision.ROLE_VARIABLES | {
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        SCAN_TRIGGER_ENV,
        SCAN_REPORT_ENV,
    }
    tokens = [config.service_token]
    if hasattr(config.provider, "token"):
        tokens.append(config.provider.token)
    references = {token.env for token in tokens if token.env}
    if any(name in blocked - {"MNEMION_API_KEY"} for name in references):
        raise ManifestError(
            "Use dedicated connector/provider token variables, not database or owner variables"
        )
    return {key: value for key, value in os.environ.items() if key not in blocked - references}


def _snapshot(path: Path, config) -> None:
    data = (config.model_dump_json() + "\n").encode()
    if len(data) > 1_000_000:
        raise ManifestError("Managed connector configuration exceeds 1 MB")
    descriptor, name = tempfile.mkstemp(prefix=".scan-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _stop(process: subprocess.Popen) -> None:
    # Provider commands may own a separate process group (Git/rclone timeouts).
    # Keep birth identities so cleanup also works with older rollback runners.
    descendants = []
    if process.poll() is None:
        try:
            descendants = [
                (child, process_identity.capture(child))
                for child in psutil.Process(process.pid).children(recursive=True)
            ]
        except (OSError, ValueError, psutil.Error):
            pass
    for sig, timeout in ((signal.SIGINT, 5), (signal.SIGTERM, 5), (signal.SIGKILL, 5)):
        if process.poll() is not None:
            break
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=timeout)
            break
        except subprocess.TimeoutExpired:
            continue
    for child, identity in reversed(descendants):
        try:
            if process_identity.matches(identity, child):
                child.kill()
        except (OSError, ValueError, psutil.Error):
            pass
    if descendants:
        psutil.wait_procs([child for child, _ in descendants], timeout=5)
    if process.poll() is None:
        raise ManifestError("The managed connector scan did not stop; inspect its local process")


class Observation:
    def __init__(self, entry: Path, identifier: str):
        self.entry = entry
        self.value = {
            "connector_id": identifier,
            "launcher_version": __version__,
            "process_identity": process_identity.capture(psutil.Process()),
            "scan_identity": None,
            "scan_version": None,
        }

    def record(self, state: str, **fields):
        value = {**self.value, **fields, "state": state}
        if value == self.value:
            return
        value["updated_at"] = update_state.timestamp()
        update_state.write(self.entry / "status.json", value)
        self.value = value
        print(
            json.dumps(
                {
                    "event": "managed_connector",
                    **{
                        key: value[key]
                        for key in ("connector_id", "state", "scan_version", "updated_at")
                    },
                }
            ),
            flush=True,
        )


def _scan(
    state, root, config, entry, singleton, observation, control, *, handoff=False, trigger="startup"
):
    with update_state.lock(root, shared=True) as runtime_lease:
        if (root / "journal.json").exists() or update_state.connector_update_waiting(root):
            observation.record("waiting_for_update")
            return None
        if not supervision.status(state)["ready"]:
            observation.record("service_unavailable")
            return None
        # Resolve afresh for every scan, after obtaining the lease. This checks
        # the signature, immutable staging identity and installed package bytes.
        runtime = service_updates.resolved_runtime(state)
        if (
            handoff
            and runtime.get("connector_protocol") == 1
            and runtime["isolated"]
            and Path(runtime["package"]).resolve() != Path(__file__).resolve().parent.parent
        ):
            # The verified runtime explicitly advertises the launcher protocol.
            # Older rollback targets still run their ordinary one-shot scanner.
            raise Handoff(runtime, trigger)
        snapshot = entry / "scan.json"
        # Absolute file references retain the original configuration's meaning.
        # Replacement is atomic and this connector's singleton owns the snapshot.
        _snapshot(snapshot, config)
        environment = _environment(config)
        environment["PYTHONUNBUFFERED"] = "1"
        environment[SCAN_TRIGGER_ENV] = trigger
        receipt = entry / "scan-result.json"
        receipt.unlink(missing_ok=True)
        environment[SCAN_REPORT_ENV] = str(receipt)
        command = [
            runtime["python"],
            *(["-I"] if runtime["isolated"] else []),
            "-m",
            "mnemion.connectors.runner",
            "--config",
            str(snapshot),
        ]
        process = subprocess.Popen(
            command,
            cwd=runtime["directory"],
            env=environment,
            start_new_session=True,
            pass_fds=(singleton, runtime_lease),
        )
        try:
            observation.record(
                "scanning",
                scan_version=runtime["version"],
                scan_identity=process_identity.capture(psutil.Process(process.pid)),
            )
            while process.poll() is None:
                control.sleep(0.25)
            code = process.wait()
        finally:
            _stop(process)
        source = {}
        if code == 0:
            # Never mistake an old receipt, a failed scan, or an older runtime
            # without receipts for newly verified source freshness.
            source = {"scanned_commit": None, "scanned_at": None}
            if receipt.exists():
                try:
                    value = update_state.read(receipt)
                    commit = git_commit("git:" + str(value.get("scanned_commit", "")))
                    if (
                        value.get("format") == 1
                        and value.get("connector_id") == str(config.connector_id)
                        and value.get("runner_version") == runtime["version"]
                        and value.get("completed") is True
                        and commit
                    ):
                        observed = datetime.fromisoformat(value["scanned_at"])
                        if observed.utcoffset() is not None:
                            source = {"scanned_commit": commit, "scanned_at": observed.isoformat()}
                except (KeyError, TypeError, ValueError, OSError):
                    # Missing/invalid optional provenance cannot claim freshness
                    # or prevent the next source scan from running.
                    pass
        observation.record("waiting", scan_identity=None, last_exit_code=code, **source)
        return code


def run(state: Path, config_path: Path, control: Control) -> int:
    state, root, _ = service_updates._root(state)
    config_path = config_path.expanduser().absolute()
    config = _configuration(config_path)
    identifier = str(config.connector_id)
    # Registration and update operations cannot race. Only the configuration's
    # UUID becomes a directory name; no provider content is used as a path.
    while True:
        try:
            with update_state.lock(root):
                registry = update_state.directory(root / "connectors")
                entry = registry / identifier
                if (
                    not entry.exists()
                    and len(list(islice(registry.iterdir(), MAX_CONNECTORS))) >= MAX_CONNECTORS
                ):
                    raise ManifestError("This host already has 64 managed connector registrations")
                entry = update_state.directory(entry)
            break
        except update_state.OperationBusy:
            control.sleep(5)
    with update_state.lock(entry) as singleton:
        observation = Observation(entry, identifier)
        observation.record("starting")
        trigger = scan_trigger()
        try:
            while True:
                if control.stopped:
                    raise Stopped()
                config = _configuration(config_path, identifier)
                try:
                    code = _scan(
                        state,
                        root,
                        config,
                        entry,
                        singleton,
                        observation,
                        control,
                        handoff=True,
                        trigger=trigger,
                    )
                except update_state.OperationBusy:
                    observation.record("waiting_for_update")
                    code = None
                if code is None:
                    control.sleep(5)
                else:
                    trigger = wait_for_sync(config, failed=code != 0, sleep=control.sleep)
        finally:
            observation.record("stopped")


def main(state: Path, config: Path) -> int:
    state = state.expanduser().absolute()
    config = config.expanduser().absolute()
    control = Control()
    handlers = {sig: signal.signal(sig, control.stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        try:
            return run(state, config, control)
        except Handoff as handoff:
            runtime = handoff.runtime
            environment = _environment(_configuration(config.expanduser().absolute()))
            environment[SCAN_TRIGGER_ENV] = handoff.trigger
            os.chdir(runtime["directory"])
            os.execve(
                runtime["python"],
                [
                    runtime["python"],
                    "-I",
                    "-m",
                    "mnemion.connectors.runner",
                    "--config",
                    str(config.expanduser().absolute()),
                    "--watch",
                    "--managed-state",
                    str(state.expanduser().absolute()),
                ],
                environment,
            )
            raise ManifestError("The managed connector runtime handoff did not execute")
    except Stopped:
        return 0
    except (OSError, ValueError, psutil.Error, supervision.SupervisionError) as error:
        # Config validation and provider diagnostics can contain submitted data.
        message = (
            str(error)
            if isinstance(error, ManifestError)
            else "Managed connector could not run; inspect its private configuration and host state"
        )
        print(json.dumps({"error": "managed_connector_failed", "detail": message}), file=sys.stderr)
        return 2
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
