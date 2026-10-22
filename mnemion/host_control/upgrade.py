"""Bind every remote upgrade to a reviewed signed target and independent backup."""

import base64
from datetime import datetime, timezone
import hashlib
import hmac
from pathlib import Path

from ..service import managed_upgrade, service_updates as updates, update_state as state_io
from ..service.update_manifest import verify_manifest
from . import HostControlError, backup
from .protocol import canonical, timestamp


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def configuration_digest(service):
    _, _, settings = updates._root(service)
    return digest({"service": settings, "updates": updates._configuration(service / "updates")})


def envelope(root, runtime=None):
    if runtime is None:
        value = state_io.read(root / "candidate.json")
    else:
        if runtime["slot"] is None:
            raise HostControlError("plan_changed", "Choose a signed managed upgrade target.")
        value = state_io.read(root / "releases" / runtime["slot"] / "envelope.json")
    content = base64.b64decode(value["envelope"], validate=True)
    release = verify_manifest(content, updates.SERVICE_UPDATE_PUBLIC_KEY)
    return hashlib.sha256(content).hexdigest(), release


def plan(root, value, store, job, request):
    service = Path(value["service_state"])
    with state_io.operator_lock(service / "updates"):
        store.guard(job["operation_id"])
        result = managed_upgrade._plan(service, service / "updates")
        public = {
            key: result[key]
            for key in (
                "status",
                "current_version",
                "available_version",
                "version",
                "schema_compatible",
                "version_compatible",
                "source_commit",
                "migrations",
                "backup_before_changes",
                "service_interruption",
                "database_rollback_automatic",
            )
            if key in result
        }
        if result["status"] not in {"planned", "recovery_required"}:
            return public, None
        path = service / "updates" / managed_upgrade.JOURNAL
        journal = state_io.read(path) if path.exists() else None
        active = updates.resolved_runtime(service)
        previous = (
            updates.resolved_runtime(service, runtime=journal["previous"]) if journal else active
        )
        target = (
            updates.resolved_runtime(service, runtime=journal["candidate"]) if journal else None
        )
        manifest_hash, release = envelope(service / "updates", target)
        try:
            backup_configuration = backup.fingerprint(root)
        except (ValueError, OSError):
            backup_configuration = None
        context = {
            "format": 1,
            "host_id": value["host_id"],
            "plan_id": job["operation_id"],
            "valid_until": request.valid_until.isoformat(),
            "active": active,
            "previous": previous,
            "manifest_sha256": manifest_hash,
            "version": release.version,
            "source_commit": release.commit,
            "configuration_sha256": configuration_digest(service),
            "backup_configuration_sha256": backup_configuration,
            "journal_sha256": digest(journal) if journal else None,
            "resume": journal is not None,
        }
        return {
            **public,
            "plan_id": job["operation_id"],
            "plan_sha256": digest(context),
            "valid_until": context["valid_until"],
            "target_version": release.version,
            "source_commit": release.commit,
            "resume": context["resume"],
            "independent_backup_configured": backup_configuration is not None,
            "service_interruption": True,
            "database_rollback_automatic": False,
        }, context


def execute(root, value, store, job, request, *, before_effect):
    if request.action == "upgrade.plan":
        return plan(root, value, store, job, request)
    if request.action != "upgrade.apply":
        raise HostControlError("invalid_action", "Choose a documented host operation.")
    context = store.plan(job["actor"], value["host_id"], request.plan_id)
    if (
        context["host_id"] != value["host_id"]
        or context["plan_id"] != str(request.plan_id)
        or not hmac.compare_digest(digest(context), request.plan_sha256)
    ):
        raise HostControlError("plan_changed", "Review the exact current signed upgrade plan.")
    service = Path(value["service_state"])
    checked = False
    prior_operation = None
    recorded_backup = None

    def guard():
        nonlocal checked, prior_operation
        store.guard(job["operation_id"])
        if datetime.fromisoformat(context["valid_until"]) <= datetime.now(timezone.utc):
            raise HostControlError("plan_changed", "The reviewed upgrade plan expired.")
        if (
            configuration_digest(service) != context["configuration_sha256"]
            or backup.fingerprint(root) != context["backup_configuration_sha256"]
        ):
            raise HostControlError(
                "plan_changed", "The host configuration changed; review a fresh plan."
            )
        if checked:
            return
        with state_io.borrowed_lock(service / "updates"):
            path = service / "updates" / managed_upgrade.JOURNAL
            journal = state_io.read(path) if path.exists() else None
            if (
                updates.resolved_runtime(service) != context["active"]
                or (digest(journal) if journal else None) != context["journal_sha256"]
                or (service / "updates/journal.json").exists()
            ):
                raise HostControlError(
                    "plan_changed", "The host changed; review a fresh upgrade plan."
                )
            uncertain = store.uncertain()
            if journal:
                prior_operation = journal.get("host_control", {}).get("operation_id")
                if prior_operation is None or any(item != prior_operation for item in uncertain):
                    raise HostControlError(
                        "recovery_required", "Inspect existing host recovery before upgrading."
                    )
            elif uncertain:
                raise HostControlError(
                    "recovery_required", "Resolve the uncertain host operation first."
                )
            checked = True

    def before_cutover(previous, candidate, journal):
        nonlocal recorded_backup
        guard()
        manifest_hash, release = envelope(service / "updates", candidate)
        if (
            previous != context["previous"]
            or manifest_hash != context["manifest_sha256"]
            or release.commit != context["source_commit"]
            or release.version != context["version"]
        ):
            raise HostControlError(
                "plan_changed", "The signed target changed; review a fresh plan."
            )
        if journal:
            metadata = journal.get("host_control", {})
            recorded_backup = metadata.get("backup")
            if recorded_backup is None:
                raise HostControlError(
                    "backup_required", "Revalidate the original independent backup."
                )
            verification = backup.verify_existing(root, value, recorded_backup)
            return {
                **metadata,
                "recovery_operation_id": job["operation_id"],
                "backup_reverified_at": verification["reverified_at"],
            }
        recorded_backup = backup.fresh(root, value, job["operation_id"])
        guard()
        return {
            "operation_id": job["operation_id"],
            "plan_id": str(request.plan_id),
            "plan_sha256": request.plan_sha256,
            "backup": recorded_backup,
        }

    result = managed_upgrade.upgrade(
        service,
        version=context["version"],
        allow_migration=True,
        resume=context["resume"],
        guard=guard,
        before_cutover=before_cutover,
        before_effect=before_effect,
    )
    public = {
        key: result[key]
        for key in (
            "status",
            "from_version",
            "version",
            "migrations",
            "database_restored",
        )
        if key in result
    }
    public["observed_at"] = timestamp()
    public["backup"] = {
        key: recorded_backup[key]
        for key in (
            "operation_id",
            "key_id",
            "verified_at",
            "snapshot_at",
            "ledger_at",
            "remote_readback_verified",
            "independent_storage_confirmed",
        )
    }
    if prior_operation is not None:
        store.recovered(prior_operation, job["operation_id"], public)
    return public, None
