"""Explicit encrypted transfers through the independently enrolled host worker."""

import hashlib
from pathlib import Path

from ..service import update_state as state_io
from . import HostControlError, backup
from .locking import operator_lock
from .protocol import canonical


def execute(root, value, store, job, request, *, before_effect):
    service = Path(value["service_state"])
    with operator_lock(service / "updates"):
        # Recheck expiry, current role and approval after an existing scan drains.
        store.guard(job["operation_id"])
        if request.action == "backup.create" and any(
            (service / "updates" / name).exists()
            for name in ("journal.json", "upgrade-journal.json")
        ):
            raise HostControlError(
                "recovery_required", "Inspect the existing managed update before making backups."
            )
        if backup.fingerprint(root) != request.configuration_sha256:
            raise HostControlError(
                "backup_configuration_changed",
                "The backup destination, key or budget changed. Refresh and approve its current settings.",
            )
        if request.action == "backup.create":
            before_effect()
            receipt = backup.fresh(root, value, job["operation_id"])
            return {"status": "created", **backup.public_receipt(root, receipt)}, None
        receipts = backup.recorded(root)
        receipt = next(
            (item for item in receipts if item["operation_id"] == str(request.backup_id)), None
        )
        if receipt is None:
            raise HostControlError(
                "backup_not_found", "This backup is no longer retained. Refresh the backup list."
            )
        before_effect()
        result = backup.verify_existing(root, value, receipt)
        # The original delivery receipt stays immutable. A separate observation
        # binds this fresh readback to its exact bytes, including destination/key.
        state_io.write(
            root / "backups" / str(request.backup_id) / "readback.json",
            {
                "receipt_sha256": hashlib.sha256(canonical(receipt)).hexdigest(),
                "verified_at": result["reverified_at"],
            },
        )
        return {"status": "verified", **backup.public_receipt(root, receipt)}, None
