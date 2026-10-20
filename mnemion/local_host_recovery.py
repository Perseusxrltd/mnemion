"""Read a server custody package for an isolated native database recovery.

Host credentials, source runners, model providers and network settings remain
in the original encrypted package. None is activated on the replacement PC.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import zipfile

from . import local_state as state
from .archives import MANIFEST, file_hash
from .service import host_package, recovery


@dataclass(frozen=True)
class HostContents:
    snapshot: Path
    ledger: Path
    manifest: dict
    description: dict
    ledger_sha256: str
    ledger_at: str


@contextmanager
def open_contents(archive: Path, scratch: Path, *, cancelled=None):
    """Authenticate the complete inventory; expose only fixed recovery facts."""
    with host_package.opened_archive(archive, temporary_directory=scratch, cancelled=cancelled) as (
        host,
        members,
    ):
        snapshot, ledger = members / "database.mnemion", members / "ledger.json"
        with zipfile.ZipFile(snapshot) as database:
            if database.getinfo(MANIFEST).file_size > 1024 * 1024:
                raise state.LocalSetupError(
                    "backup_format", "The backup setup inventory is too large."
                )
            manifest = json.loads(database.read(MANIFEST))
        plan = host_package.public_plan(host["plan"])
        current = recovery.read_ledger(ledger)
        if (
            not isinstance(manifest, dict)
            or manifest.get("format") != recovery.BACKUP_FORMAT
            or manifest.get("backup_id") != plan["backup_id"]
            or recovery._time(manifest.get("snapshot_at")) != recovery._time(plan["snapshot_at"])
            or sorted(manifest.get("tenant_ids", [])) != sorted(plan["tenant_ids"])
            or not set(plan["tenant_ids"]).issubset(current["tenant_ids"])
            or recovery._time(current["snapshot_at"]) < recovery._time(plan["snapshot_at"])
            or recovery._time(current["snapshot_at"]) != recovery._time(plan["ledger_at"])
            or len(plan["connectors"]) > 64
        ):
            raise state.LocalSetupError(
                "backup_format", "The host package and its database or access ledger disagree."
            )
        ledger_at = current["snapshot_at"]
        # The full ledger is read again by canonical database restoration;
        # do not hold its potentially large JSON graph across that operation.
        del current
        yield HostContents(
            snapshot=snapshot,
            ledger=ledger,
            manifest=manifest,
            ledger_sha256=file_hash(ledger, check_cancelled=lambda: recovery._cancel(cancelled)),
            ledger_at=ledger_at,
            description={
                "package_id": plan["package_id"],
                "service_version": plan["service_version"],
                "source_connectors": len(plan["connectors"]),
                "private_files": len(host["assets"]),
                "host_configuration_restored": False,
            },
        )
