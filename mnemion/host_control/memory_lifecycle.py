"""OS supervision which honors the adopted host's durable service decisions.

The outer systemd/launchd job stays alive while an administrator stops memory.
It must not treat an approved stop, queued work or interrupted migration as a
crash. This entry point replaces an unconditional memory restart command; it
does not install OS jobs or confer host authority.
"""

from datetime import datetime
import os
from pathlib import Path
import signal
from threading import Event

import psutil

from .. import process_identity
from ..service import service_updates as updates, supervision, update_state as state_io
from ..version import __version__
from . import HostControlError
from .installation import settings
from .runtime import current
from .store import Store, identifier
from .protocol import timestamp


def _policy(root, value, store):
    result = store.service_policy()
    service = Path(value["service_state"])
    result["recovery_required"] = any(
        (service / "updates" / name).exists() or (service / "updates" / name).is_symlink()
        for name in ("journal.json", "upgrade-journal.json")
    )
    pending = root / "memory-supervision/start-intent.json"
    saved = state_io.read(pending) if pending.exists() or pending.is_symlink() else None
    if saved is not None:
        if (
            not isinstance(saved, dict)
            or set(saved) != {"format", "host_id", "operation_id", "kind", "at"}
            or type(saved["format"]) is not int
            or saved["format"] != 1
            or saved["host_id"] != value["host_id"]
            or saved["kind"] not in {"start", "repair"}
            or not isinstance(saved["at"], str)
            or datetime.fromisoformat(saved["at"]).tzinfo is None
        ):
            raise HostControlError("host_identity_changed", "Inspect the recorded service start.")
        if saved["operation_id"] is not None:
            identifier(saved["operation_id"])
    result["start_needs_inspection"] = bool(
        saved and saved["operation_id"] == result["operation_id"]
    )
    result["automatic_start_allowed"] = (
        result["automatic_start_allowed"]
        and not result["recovery_required"]
        and not result["start_needs_inspection"]
    )
    result["observed_at"] = timestamp()
    return result


def policy(root):
    """OS-owner/monitor observation; an error must never authorize a restart."""
    root, value = settings(root)
    return _policy(root, value, Store(root / "authority"))


def observe(root, value, store, *, repair=False):
    """One bounded reconciliation, serialized with host operations and updates."""
    service = Path(value["service_state"])
    with state_io.lock(root / "worker"), state_io.lock(service / "updates"):
        desired = _policy(root, value, store)
        observed = supervision.status(service)
        pending = root / "memory-supervision/start-intent.json"
        if observed["running"]:
            # Observing the original start is not a request to start again.
            if pending.exists():
                saved = state_io.read(pending)
                if saved.get("kind") != "repair" or observed.get("ready"):
                    pending.unlink()
            if not repair or observed.get("ready") or not desired["automatic_start_allowed"]:
                return {"running": True, "start_requested": False, "policy": desired}
        if not desired["automatic_start_allowed"]:
            return {"running": False, "start_requested": False, "policy": desired}
        state_io.directory(pending.parent)
        state_io.write(
            pending,
            {
                "format": 1,
                "host_id": value["host_id"],
                "operation_id": desired["operation_id"],
                "at": timestamp(),
                "kind": "repair" if repair else "start",
            },
        )
        if observed["running"]:
            if not supervision.stop(service)["stopped"]:
                raise HostControlError(
                    "host_unavailable", "Inspect the interrupted service repair."
                )
        # Never retry an unconfirmed start. The next observation may confirm
        # its supervisor; otherwise an explicit new service.start is required.
        observed = supervision.start(service)
        if observed["running"] and (not repair or observed.get("ready")):
            pending.unlink()
        return {"running": observed["running"], "start_requested": True, "policy": desired}


def repair(root):
    """The OS watchdog uses the same locks and decision, never systemctl restart."""
    root, value = settings(root)
    return observe(root, value, Store(root / "authority"), repair=True)


def run(root):
    root, value = settings(root)
    store = Store(root / "authority")
    stopping = Event()
    previous = {
        number: signal.signal(number, lambda *_: stopping.set())
        for number in (signal.SIGTERM, signal.SIGINT)
    }
    try:
        with state_io.lock(root / "memory-supervision"):
            while not stopping.is_set():
                try:
                    result = observe(root, value, store)
                    state_io.write(
                        root / "memory-supervision/status.json",
                        {
                            "at": timestamp(),
                            "host_id": value["host_id"],
                            **result,
                            "process_identity": process_identity.capture(psutil.Process()),
                            "version": __version__,
                        },
                    )
                    pins = current(root, value)
                    # Keep the stable OS job current without restarting memory
                    # or executing an unverified slot. The copied launcher
                    # performs the normal managed-runtime verification again.
                    if not pins["pending"] and (
                        Path(pins["current"]["package"]).resolve()
                        != Path(__file__).resolve().parents[1]
                    ):
                        command = [value["python"], str(root / "launcher.py"), str(root), "memory"]
                        os.chdir(value["directory"])
                        os.execve(command[0], command, updates._environment())
                except state_io.OperationBusy:
                    pass  # Existing work owns its lifetime; never interrupt it.
                except Exception:
                    state_io.write(
                        root / "memory-supervision/attention.json",
                        {
                            "at": timestamp(),
                            "code": "memory_start_needs_inspection",
                        },
                    )
                stopping.wait(10)
        return 0
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
