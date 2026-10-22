"""Fresh encrypted host backups before an independently authorized cutover."""

from contextlib import contextmanager
import hashlib
from pathlib import Path
import shutil

from pydantic import Field, field_validator

from .. import backup_encryption
from ..private_input import read_private
from ..service import host_package, service_updates as updates, update_state as state_io
from ..version import __version__
from . import HostControlError
from .backup_git import GitDestination, Repository, deliver, verify
from .installation import settings
from .protocol import Document, canonical, timestamp
from .store import identifier


class Configuration(Document):
    format: int = Field(default=1, strict=True, ge=1, le=1)
    destination: GitDestination
    secret_file: Path
    key_id: str = Field(pattern=r"^[a-f0-9]{24}$")
    independent_storage_confirmed: bool = Field(strict=True)
    independent_key_custody_confirmed: bool = Field(strict=True)
    maximum_bytes: int = Field(default=512 * 1024**2, strict=True, ge=1024**2, le=2 * 1024**3)
    keep_verified_backups: int = Field(default=3, strict=True, ge=2, le=20)

    @field_validator("secret_file")
    @classmethod
    def private_key_location(cls, value):
        if not value.is_absolute() or len(str(value)) > 4096:
            raise ValueError("Choose an absolute path to the private recovery key.")
        return value


def configure(root, spec):
    root, value = settings(root)
    key = host_package.key_file(spec.secret_file)
    if backup_encryption.key_id(key) != spec.key_id:
        raise HostControlError(
            "backup_key_changed", "Confirm the current independently held recovery key."
        )
    if spec.secret_file.resolve().is_relative_to(root / "backups"):
        raise HostControlError(
            "invalid_backup_key", "Keep the recovery key outside backup storage."
        )
    if not spec.independent_key_custody_confirmed or not spec.independent_storage_confirmed:
        raise HostControlError(
            "backup_custody_required",
            "Confirm independent storage and a separately held recovery key.",
        )
    if not spec.destination.remote_storage:
        raise HostControlError(
            "independent_backup_required",
            "A local Git repository does not prove independent backup custody.",
        )
    with state_io.operator_lock(Path(value["service_state"]) / "updates"):
        index = root / "backup-index.json"
        saved = state_io.read(index) if index.exists() else {"backups": []}
        if saved.get("retiring") is not None:
            raise HostControlError(
                "backup_retirement_pending", "Finish the recorded backup retirement first."
            )
        receipts = saved["backups"]
        if any(item["destination_identity"] != destination_identity(spec) for item in receipts):
            raise HostControlError(
                "backup_destination_review_required",
                "Retained backups belong to another destination; review their custody before moving it.",
            )
        state_io.write(root / "backup-config.json", spec.model_dump(mode="json"))
    return {"configured": True, "key_id": spec.key_id, "delivery_verified": False}


def configuration(root):
    try:
        spec = Configuration.model_validate(state_io.read(root / "backup-config.json"))
        key = host_package.key_file(spec.secret_file)
        if (
            backup_encryption.key_id(key) != spec.key_id
            or not spec.destination.remote_storage
            or not spec.independent_storage_confirmed
            or not spec.independent_key_custody_confirmed
        ):
            raise ValueError
        return spec
    except (ValueError, OSError):
        raise HostControlError(
            "backup_required",
            "Configure independent encrypted backup storage and recovery-key custody.",
        ) from None


def fingerprint(root):
    spec = configuration(root)
    credentials = {}
    if spec.destination.ssh is not None:
        for name in ("identity_file", "known_hosts_file"):
            credentials[name] = hashlib.sha256(
                read_private(getattr(spec.destination.ssh, name), maximum=128 * 1024)
            ).hexdigest()
    if spec.destination.token_file is not None:
        credentials["token"] = hashlib.sha256(
            read_private(spec.destination.token_file, maximum=16384)
        ).hexdigest()
    return hashlib.sha256(
        canonical(
            {
                "configuration": spec.model_dump(mode="json"),
                "credential_digests": credentials,
            }
        )
    ).hexdigest()


def destination_identity(spec):
    return hashlib.sha256(
        canonical(
            spec.destination.model_dump(
                mode="json",
                include={"remote", "local_repository", "branch_prefix"},
            )
        )
    ).hexdigest()


@contextmanager
def file_budget(maximum):
    """The detached worker and pg_dump cannot create an unbounded dump file."""
    import resource

    previous = resource.getrlimit(resource.RLIMIT_FSIZE)
    limits = [maximum, *(value for value in previous if value != resource.RLIM_INFINITY)]
    resource.setrlimit(resource.RLIMIT_FSIZE, (min(limits), previous[1]))
    try:
        yield
    finally:
        resource.setrlimit(resource.RLIMIT_FSIZE, previous)


def status(root):
    try:
        spec = configuration(root)
        configured, key_id = True, spec.key_id
    except HostControlError:
        configured, key_id = False, None
    index = root / "backup-index.json"
    try:
        receipts = state_io.read(index).get("backups", []) if index.exists() else []
    except ValueError:
        return {"configured": configured, "inspection_required": True}
    return {
        "configured": configured,
        "key_id": key_id,
        "last_verified_at": receipts[-1]["verified_at"] if receipts else None,
        "retained_verified_backups": len(receipts),
        "independence": "confirmed_by_host_owner" if configured else "unconfirmed",
    }


def fresh(root, value, operation_id):
    """Called under the host operation lease, before stopping any service."""
    spec = configuration(root)
    service = Path(value["service_state"])
    runtime = updates.resolved_runtime(service)
    if (
        runtime["version"] != __version__
        or Path(runtime["package"]).resolve() != Path(host_package.__file__).resolve().parents[1]
    ):
        raise HostControlError(
            "controller_update_required",
            "Let the controller adopt the current service runtime before upgrading.",
        )
    storage = state_io.directory(root / "backups")
    if (root / "backup-index.json").exists():
        prune(root, value, spec)
    from .backup_git import _disk_usage

    _disk_usage(storage, spec.maximum_bytes * (spec.keep_verified_backups + 1))
    if shutil.disk_usage(storage).free < spec.maximum_bytes * 3 + 64 * 1024**2:
        raise HostControlError("backup_capacity", "Make room for the bounded encrypted backup.")
    operation_id = identifier(operation_id)
    target = storage / operation_id
    if target.exists():
        raise HostControlError(
            "backup_delivery_unconfirmed",
            "Inspect the existing backup for this operation; it was preserved.",
        )
    state_io.directory(target)
    state_io.write(
        target / "intent.json",
        {
            "format": 1,
            "host_id": value["host_id"],
            "operation_id": operation_id,
            "created_at": timestamp(),
            "key_id": spec.key_id,
        },
        replace=False,
    )
    files = {"bundle": target / "host.mnemion-host", "ledger": target / "access.mnemion-ledger"}
    with file_budget(spec.maximum_bytes):
        bundle = host_package.snapshot(service, files["bundle"], spec.secret_file, lock_held=True)
        ledger = host_package.export_ledger(
            service, files["ledger"], spec.secret_file, lock_held=True
        )
    delivery = deliver(
        target,
        spec.destination,
        host_id=value["host_id"],
        operation_id=operation_id,
        files=files,
        maximum=spec.maximum_bytes,
    )
    if (
        delivery["files"]["bundle"]["sha256"] != bundle["sha256"]
        or delivery["files"]["ledger"]["sha256"] != ledger["sha256"]
        or delivery["remote_readback_verified"] is not True
        or delivery["remote_storage"] is not True
    ):
        raise HostControlError(
            "backup_delivery_unconfirmed", "Independent backup readback did not match."
        )
    receipt = {
        "operation_id": operation_id,
        "host_id": value["host_id"],
        "key_id": spec.key_id,
        "destination_identity": destination_identity(spec),
        "verified_at": timestamp(),
        "snapshot_at": bundle["plan"]["snapshot_at"],
        "ledger_at": ledger["snapshot_at"],
        **delivery,
        "independent_storage_confirmed": True,
        "independent_key_custody_confirmed": True,
    }
    state_io.write(target / "receipt.json", receipt, replace=False)
    index = root / "backup-index.json"
    prior = state_io.read(index).get("backups", []) if index.exists() else []
    state_io.write(index, {"backups": [*prior, receipt]})
    prune(root, value, spec)
    return receipt


def verify_existing(root, value, receipt):
    spec = configuration(root)
    if (
        receipt["host_id"] != value["host_id"]
        or receipt["key_id"] != spec.key_id
        or receipt["destination_identity"] != destination_identity(spec)
        or receipt["independent_storage_confirmed"] is not True
        or receipt["independent_key_custody_confirmed"] is not True
    ):
        raise HostControlError(
            "backup_required", "Revalidate the recorded independent backup custody."
        )
    original = root / "backups" / identifier(receipt["operation_id"]) / "receipt.json"
    if state_io.read(original) != receipt:
        raise HostControlError(
            "backup_required", "Inspect the original independent backup receipt."
        )
    result = verify(
        root,
        spec.destination,
        host_id=value["host_id"],
        operation_id=receipt["operation_id"],
        commit=receipt["commit"],
        manifest_sha256=receipt["manifest_sha256"],
        files=receipt["files"],
        maximum=spec.maximum_bytes,
    )
    if not result["remote_readback_verified"] or not result["remote_storage"]:
        raise HostControlError(
            "backup_required", "Verify the original independent backup before recovery."
        )
    return {"original_backup": receipt, "reverified_at": timestamp()}


def prune(root, value, spec):
    """Retire only an unchanged, verified branch created for this exact host."""
    from .. import local_state

    index = root / "backup-index.json"
    saved = state_io.read(index)
    receipts = saved["backups"]
    journal = Path(value["service_state"]) / "updates/upgrade-journal.json"
    protected = (
        state_io.read(journal).get("host_control", {}).get("backup", {}).get("operation_id")
        if journal.exists()
        else None
    )
    retiring_id = saved.get("retiring")
    if retiring_id is not None and (
        retiring_id == protected
        or not any(item["operation_id"] == retiring_id for item in receipts)
        or len(receipts) <= spec.keep_verified_backups
    ):
        raise HostControlError(
            "backup_retention_changed", "Inspect the unfinished backup retirement."
        )
    while len(receipts) > spec.keep_verified_backups:
        old = (
            next((item for item in receipts if item["operation_id"] == retiring_id), None)
            if retiring_id
            else next(
                (
                    item
                    for item in receipts[: -spec.keep_verified_backups]
                    if item["operation_id"] != protected
                ),
                None,
            )
        )
        if old is None:
            break
        operation_id = identifier(old["operation_id"])
        expected_ref = (
            f"refs/heads/{spec.destination.branch_prefix}/{value['host_id']}/{operation_id}"
        )
        if (
            old["host_id"] != value["host_id"]
            or old["ref"] != expected_ref
            or old["destination_identity"] != destination_identity(spec)
        ):
            raise HostControlError(
                "backup_retention_changed", "Inspect retained backup identities."
            )
        target = root / "backups" / operation_id
        retiring = saved.get("retiring") == operation_id
        if not retiring and state_io.read(target / "receipt.json") != old:
            raise HostControlError(
                "backup_retention_changed", "Inspect the retained backup receipt."
            )
        with local_state.temporary_directory(prefix="backup-retire-", dir=root) as temporary:
            repository = Repository(temporary / "remote", spec.destination, budget=16 * 1024**2)
            head = repository.head(expected_ref)
            if head != old["commit"] and not (head is None and retiring):
                raise HostControlError(
                    "backup_retention_changed", "The retained backup reference changed."
                )
            if head is not None:
                state_io.write(index, {"backups": receipts, "retiring": operation_id})
                repository.git(
                    "push",
                    "--porcelain",
                    "--force-with-lease=" + expected_ref + ":" + old["commit"],
                    "--",
                    repository.remote,
                    ":" + expected_ref,
                )
                if repository.head(expected_ref) is not None:
                    raise HostControlError(
                        "backup_retention_changed", "Backup retirement is unconfirmed."
                    )
        # Only this private operation's files are removed, after remote
        # compare-and-delete. Failed/uncertain backups are not silently pruned.
        if target.exists() or target.is_symlink():
            local_state._regular(target, directory=True)
            shutil.rmtree(target)
        receipts = [item for item in receipts if item["operation_id"] != operation_id]
        saved = {"backups": receipts}
        state_io.write(index, saved)
        retiring_id = None
