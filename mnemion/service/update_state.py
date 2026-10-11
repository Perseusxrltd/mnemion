"""Private host state and exclusive coordination for managed service updates."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

from .update_manifest import ManifestError

MAX_STATE_BYTES = 262144


class OperationBusy(ManifestError):
    """Another updater owns the host operation lock."""


@contextmanager
def adoption(path: Path):
    """Roll back only this new, empty installation if setup cannot complete."""
    existed = path.exists()
    directory(path)
    if any(path.iterdir()):
        raise ManifestError("Managed adoption requires an empty state directory")
    identity = (path.stat().st_dev, path.stat().st_ino)
    try:
        yield
    except BaseException:
        # Setup never starts Supervisor. Credentials are copies, and callers'
        # input files, Python installation and database are outside this tree.
        if not path.is_symlink() and path.exists():
            info = path.stat()
            if (info.st_dev, info.st_ino) == identity:
                shutil.rmtree(path)
                if existed:
                    path.mkdir(mode=0o700)
        raise


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def directory(path: Path) -> Path:
    if os.name != "posix" or os.geteuid() == 0:
        raise ManifestError("Managed service updates require an unprivileged Linux/macOS account")
    if path.is_symlink():
        raise ManifestError("Managed update state cannot be a symbolic link")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ManifestError("Managed update state must be private and owned by this user")
    return path.resolve()


def read(path: Path) -> dict:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
                or info.st_size > MAX_STATE_BYTES
            ):
                raise ManifestError("Managed update records must be private bounded regular files")
            content = stream.read(MAX_STATE_BYTES + 1)
        if len(content) > MAX_STATE_BYTES:
            raise ManifestError("Managed update record exceeds its size budget")
        value = json.loads(content)
        if not isinstance(value, dict):
            raise ManifestError("Managed update record must be an object")
        return value
    except (OSError, ValueError, RecursionError) as error:
        if isinstance(error, ManifestError):
            raise
        raise ManifestError("Cannot read the managed update record") from None


def write(path: Path, value: dict, *, replace: bool = True) -> None:
    directory(path.parent)
    if path.exists() or path.is_symlink():
        read(path)
        if not replace:
            raise ManifestError("Managed update record already exists")
    content = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    )
    if len(content) > MAX_STATE_BYTES:
        raise ManifestError("Managed update record exceeds its size budget")
    descriptor, name = tempfile.mkstemp(prefix=".update-state-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def lock(root: Path):
    import fcntl

    directory(root)
    descriptor = os.open(root / "operation.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ManifestError("The update operation lock must be a private regular file")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise OperationBusy("Another managed update operation is already running") from None
        yield
    finally:
        os.close(descriptor)


def local_migrations() -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files("mnemion.service").joinpath("migrations").iterdir()
        if path.name.endswith(".sql")
    }


def record(root: Path, event: str, **fields) -> None:
    path = root / "history.json"
    previous = read(path).get("events", []) if path.exists() else []
    if not isinstance(previous, list):
        raise ManifestError("Invalid managed update event history")
    # Reviewed public summaries only, never subprocess output or credentials.
    value = {"at": timestamp(), "event": event, **fields}
    write(path, {"events": [*previous[-19:], value]})
