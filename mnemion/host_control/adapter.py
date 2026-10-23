"""Whitelisted managed-service operations under the host's existing locks."""

from pathlib import Path

from ..service import service_updates as updates, supervision, update_state as state_io
from ..service.update_manifest import version_tuple
from . import HostControlError
from .locking import operator_lock
from .protocol import timestamp
from .runtime import current


def status(root, value, store):
    from . import backup, memory_lifecycle

    service, update_root, _ = updates._root(Path(value["service_state"]))
    try:
        observed = supervision.status(service)
        state = {
            "running": observed["running"],
            "ready": observed["ready"],
            "stopping": observed.get("stopping", False),
        }
    except Exception:
        state = {"running": None, "ready": False, "inspection_required": True}
    active = state_io.read(update_root / "active.json")
    version_tuple(active["version"])
    pins = current(root, value)
    return {
        **state,
        "observed_at": timestamp(),
        "version": active["version"],
        "updates_enabled": updates._configuration(update_root)["enabled"],
        "recovery_required": any(
            (update_root / name).exists() for name in ("journal.json", "upgrade-journal.json")
        ),
        "operations": store.work_status(),
        "service_policy": memory_lifecycle._policy(root, value, store),
        "backups": backup.status(root),
        "controller": {
            "version": pins["current"]["version"],
            "update_pending": pins["pending"],
            "fallback": pins["fallback"],
            "update_needs_inspection": (root / "runtime-attention.json").exists(),
        },
    }


def execute(root, value, store, job, request, *, before_effect):
    service = Path(value["service_state"])
    if request.action in {"backup.create", "backup.verify"}:
        from .backup_jobs import execute as backup_job

        return backup_job(root, value, store, job, request, before_effect=before_effect)
    if request.action in {"service.start", "service.stop", "operations.resolve"}:
        with operator_lock(service / "updates"):
            store.guard(job["operation_id"])
            if any(
                (service / "updates" / name).exists()
                for name in ("journal.json", "upgrade-journal.json")
            ):
                raise HostControlError(
                    "recovery_required", "Inspect and resume the existing managed update first."
                )
            if request.action == "operations.resolve":
                if request.settle == "stop":
                    before_effect()
                    if not supervision.stop(service)["stopped"]:
                        raise HostControlError(
                            "host_unavailable", "Inspect the pending service stop."
                        )
                observed = supervision.status(service)
                if observed["running"] and not observed.get("service_ready", observed["ready"]):
                    raise HostControlError(
                        "host_unavailable", "Inspect the unstable memory service first."
                    )
                before_effect()
                return store.resolve(
                    job["actor"],
                    request,
                    {
                        "running": observed["running"],
                        "ready": observed["ready"],
                        "observed_at": timestamp(),
                    },
                ), None
            if request.action == "service.start":
                observed = supervision.status(service)
                if observed["running"]:
                    from ..service.managed_upgrade import _schema

                    active = updates.resolved_runtime(service)
                    if _schema(service, service / "updates") != active["migrations"]:
                        raise HostControlError(
                            "recovery_required", "Inspect the current runtime and schema first."
                        )
                    before_effect()
                    updates._processes(service, start=True)
                    observed = supervision.status(service)
                else:
                    before_effect()
                    observed = supervision.start(service)
                result = {"running": observed["running"], "ready": observed["ready"]}
            else:
                before_effect()
                result = supervision.stop(service)
                if not result["stopped"]:
                    raise HostControlError("host_unavailable", "Inspect the pending service stop.")
                result = {"stopped": True}
            return {**result, "observed_at": timestamp()}, None
    from .upgrade import execute as upgrade

    return upgrade(root, value, store, job, request, before_effect=before_effect)
