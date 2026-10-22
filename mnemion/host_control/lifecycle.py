"""The OS owner can run control independently of the memory Supervisor."""

import http.client
import os
from pathlib import Path
import shlex
import time
import xmlrpc.client

import psutil

from .. import process_identity
from ..service import service_updates as updates, supervision
from ..service import update_state as state_io
from . import HostControlError
from .installation import settings


def status(root: Path):
    root, value = settings(root)
    base = {"host_id": value["host_id"], "running": False, "ready": False}
    try:
        with supervision._rpc(value) as client:
            processes = client.supervisor.getAllProcessInfo()
    except (FileNotFoundError, ConnectionRefusedError):
        return base
    except xmlrpc.client.Fault as error:
        if error.faultCode == 6:
            return {**base, "running": True, "stopping": True}
        raise
    if len(processes) != 1 or processes[0]["name"] != "mnemion-host-control":
        raise HostControlError(
            "host_identity_changed", "Unexpected processes in the independent controller."
        )
    process = processes[0]
    ready, version = False, None
    if process["statename"] == "RUNNING":
        try:
            receipt = state_io.read(root / "ready.json")
            actual = psutil.Process(process["pid"])
            ready = (
                receipt["host_id"] == value["host_id"]
                and receipt["protocol"] == 1
                and receipt["pid"] == process["pid"]
                and actual.uids().real == os.getuid()
                and process_identity.matches(receipt["process_identity"], actual)
                and actual.status() != psutil.STATUS_ZOMBIE
            )
            if ready:
                version = receipt["version"]
        except (OSError, ValueError, KeyError, psutil.Error):
            pass
    return {**base, "running": True, "ready": ready, "version": version}


def start(root: Path):
    root, value = settings(root)
    with state_io.lock(root / "lifecycle"):
        current = status(root)
        if current["running"]:
            return {**current, "already_running": True}
        try:
            updates._command(
                [
                    value["python"],
                    "-m",
                    "supervisor.supervisord",
                    "-c",
                    str(root / "supervisord.conf"),
                ],
                cwd=Path(value["directory"]),
                environment=updates._environment(),
                log=root / "logs/startup.log",
                timeout=15,
                # Supervisor intentionally outlives this start command.
                # Only finite managed jobs may inherit their operation leases.
                retain_operation_locks=False,
            )
        except Exception:
            raise HostControlError(
                "control_start_unconfirmed",
                "Inspect control status and its private startup log before retrying.",
            ) from None
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            current = status(root)
            if current["ready"]:
                return current
            time.sleep(0.25)
        return current


def stop(root: Path):
    root, value = settings(root)
    with state_io.lock(root / "lifecycle"):
        if not status(root)["running"]:
            return {"stopped": True, "already_stopped": True}
        try:
            with supervision._rpc(value) as client:
                client.supervisor.shutdown()
        except (FileNotFoundError, ConnectionRefusedError):
            return {"stopped": True}
        except (ConnectionResetError, BrokenPipeError, http.client.RemoteDisconnected):
            pass  # Observe the first shutdown. A lost reply is not a new action.
        except xmlrpc.client.Fault as error:
            if error.faultCode != 6:
                raise
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if not status(root)["running"]:
                return {"stopped": True}
            time.sleep(0.25)
        return {"stopped": False, "inspection_required": True}


def startup(root: Path):
    """Local OS-owner instructions; no claim that boot has been registered."""
    root, value = settings(root)
    command = shlex.join(
        [
            value["python"],
            "-m",
            "supervisor.supervisord",
            "-c",
            str(root / "supervisord.conf"),
        ]
    )
    command = "cd " + shlex.quote(value["directory"]) + " && " + command
    return {
        "registered": False,
        "registration_checked": False,
        "cron_entry": "@reboot " + command.replace("%", r"\%"),
        "launchd_file": str(root / "launchd.plist"),
        "launchd_label": "com.mnemion.host-control." + value["identifier"],
        "boot_command": command,
    }
