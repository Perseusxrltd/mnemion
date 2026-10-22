"""Keep the controller independently runnable as the memory service updates."""

from pathlib import Path
from uuid import uuid4

from ..service import runtime_pins, service_updates as updates, update_state as state_io
from ..version import __version__
from . import HostControlError
from .installation import compatible_runtime


def current(root, value):
    updates_root = Path(value["service_state"]) / "updates"
    pins = runtime_pins.read(updates_root)
    if pins is None or pins["host_id"] != value["host_id"] or pins["state"] != str(root):
        raise HostControlError("runtime_unavailable", "Inspect independent runtime custody.")
    return pins


def acknowledge(root, value):
    """Called only after the restricted listener has actually bound its socket."""
    with state_io.lock(root / "runtime-control"):
        pins = current(root, value)
        runtime = updates.resolved_runtime(Path(value["service_state"]), runtime=pins["current"])
        if (
            runtime["version"] != __version__
            or Path(runtime["package"]).resolve() != Path(__file__).resolve().parents[1]
        ):
            raise HostControlError(
                "runtime_changed", "The controller started in a different runtime."
            )
        if pins["pending"]:
            pins.update(pending=False, attempts=0, revision=str(uuid4()))
            state_io.write(Path(value["service_state"]) / "updates" / runtime_pins.FILE, pins)


def promote(root, value, store):
    """No active/queued work may be displaced by a controller runtime change."""
    service = Path(value["service_state"])
    try:
        with state_io.lock(root / "worker"), state_io.lock(service / "updates"):
            if store.needs_worker():
                return False
            with state_io.lock(root / "runtime-control"):
                pins = current(root, value)
                active = state_io.read(service / "updates/active.json")
                if pins["pending"] or active == pins["current"]:
                    return False
                if active["slot"] == pins["rejected_slot"]:
                    return False
                target = compatible_runtime(service, active)
                if store.needs_worker():
                    return False
                pins.update(
                    current=target,
                    previous=pins["current"],
                    pending=True,
                    attempts=0,
                    revision=str(uuid4()),
                    fallback=False,
                )
                state_io.write(service / "updates" / runtime_pins.FILE, pins)
                return True
    except state_io.OperationBusy:
        return False
