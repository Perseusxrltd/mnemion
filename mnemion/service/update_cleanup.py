"""Retain managed rollback files without deleting unrelated operator data."""

from __future__ import annotations

import base64
import os
from pathlib import Path
import re
import shutil
import stat

from . import update_state as state_io
from .update_manifest import ManifestError, verify_manifest

KEEP_BACKUPS = 3
_BACKUP = re.compile(
    r"pre-update-[0-9]+\.[0-9]+\.[0-9]+-to-[0-9]+\.[0-9]+\.[0-9]+-[a-f0-9]{32}\.zip"
)
SLOT = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+-[a-f0-9]{12}")


def _identity(path: Path) -> dict:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ManifestError("Managed backups must remain private regular files")
    return {
        "device": info.st_dev,
        "inode": info.st_ino,
        "size": info.st_size,
        "modified_ns": info.st_mtime_ns,
        "changed_ns": info.st_ctime_ns,
    }


def retain_backup(root: Path, name: str) -> None:
    """Index only a backup just created and verified by this updater, under its lock."""
    if not isinstance(name, str) or not _BACKUP.fullmatch(name):
        raise ManifestError("Invalid managed backup name")
    backups = state_io.directory(root / "backups")
    index = root / "backup-index.json"
    entries = state_io.read(index).get("backups") if index.exists() else []
    if not isinstance(entries, list) or len(entries) > 100:
        raise ManifestError("Invalid managed backup retention record")
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("name"), str)
            or not _BACKUP.fullmatch(entry["name"])
            or not isinstance(entry.get("identity"), dict)
        ):
            raise ManifestError("Invalid managed backup retention entry")
    entries = [entry for entry in entries if entry["name"] != name]
    entries.append({"name": name, "identity": _identity(backups / name)})
    state_io.write(index, {"backups": entries})
    protected = {
        state_io.read(root / journal).get("backup")
        for journal in ("journal.json", "upgrade-journal.json")
        if (root / journal).exists()
    }
    while len(entries) > KEEP_BACKUPS:
        removable = next(
            (i for i, entry in enumerate(entries) if entry["name"] not in protected), None
        )
        if removable is None:
            break
        entry = entries[removable]
        path = backups / entry["name"]
        try:
            unchanged = _identity(path) == entry["identity"]
        except (OSError, ManifestError):
            unchanged = False
        if unchanged:
            path.unlink()
        # A replaced, moved or modified backup belongs to the operator. Stop
        # managing it; never follow a link or delete a replacement by filename.
        entries.pop(removable)
        state_io.write(index, {"backups": entries})


def retain_runtimes(root: Path, public_key: bytes, *, pending: str) -> int:
    """Keep active, previous, pending and any interrupted cutover's runtimes."""
    keep = {pending}
    from .runtime_pins import protected

    keep.update(protected(root))
    for name in ("active.json", "previous.json"):
        path = root / name
        if path.exists():
            keep.add(state_io.read(path).get("slot"))
    for name in ("journal.json", "upgrade-journal.json"):
        journal = root / name
        if journal.exists():
            value = state_io.read(journal)
            keep.update(value[key].get("slot") for key in ("previous", "candidate"))
    removed = 0
    for slot in state_io.directory(root / "releases").iterdir():
        if slot.name in keep or not SLOT.fullmatch(slot.name) or slot.is_symlink():
            continue
        try:
            state_io.directory(slot)
            envelope = state_io.read(slot / "envelope.json")
            release = verify_manifest(
                base64.b64decode(envelope["envelope"], validate=True), public_key
            )
        except (ManifestError, KeyError, TypeError, OSError, ValueError):
            continue
        if slot.name != f"{release.version}-{release.commit[:12]}":
            continue
        # rmtree does not traverse symlinks inside the exclusively managed tree.
        shutil.rmtree(slot)
        removed += 1
    return removed
