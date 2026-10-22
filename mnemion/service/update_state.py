"""Private host state and exclusive coordination for managed service updates."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time

from .update_manifest import ManifestError

MAX_STATE_BYTES = 262144
_COMMAND_LOCKS = ContextVar("mnemion_managed_command_locks", default=())


@contextmanager
def command_custody(descriptor: int):
    """A verified owned child retains this lease if its launcher disappears."""
    token = _COMMAND_LOCKS.set((*_COMMAND_LOCKS.get(), descriptor))
    try:
        yield
    finally:
        _COMMAND_LOCKS.reset(token)


def inherited_locks() -> tuple[int, ...]:
    return tuple(dict.fromkeys(_COMMAND_LOCKS.get()))


@contextmanager
def borrowed_lock(root: Path):
    """Reuse an already held lease without acquiring a conflicting second FD."""
    expected = (root / "operation.lock").lstat()
    if not stat.S_ISREG(expected.st_mode):
        raise ManifestError("The managed operation lease needs inspection")
    for descriptor in inherited_locks():
        actual = os.fstat(descriptor)
        if (actual.st_dev, actual.st_ino) == (expected.st_dev, expected.st_ino):
            yield descriptor
            return
    raise ManifestError("This operation must hold the adopted host's update lease")


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
def lock(root: Path, *, shared: bool = False):
    import fcntl

    directory(root)
    descriptor = os.open(root / "operation.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ManifestError("The update operation lock must be a private regular file")
        try:
            mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
            fcntl.flock(descriptor, mode | fcntl.LOCK_NB)
        except BlockingIOError:
            raise OperationBusy("Another managed update operation is already running") from None
        # Managed scans pass this descriptor to their child. An interrupted
        # launcher cannot release runtime protection while that scan still runs.
        with command_custody(descriptor):
            yield descriptor
    finally:
        os.close(descriptor)


def local_migrations() -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files("mnemion.service").joinpath("migrations").iterdir()
        if path.name.endswith(".sql")
    }


def pause_new_connector_scans(root: Path) -> dict:
    """A live updater announces its turn; existing scans can finish normally."""
    import psutil
    from .. import process_identity

    value = {
        "format": 1,
        "process_identity": process_identity.capture(psutil.Process()),
        "until_monotonic": time.monotonic() + 300,
    }
    write(root / "connector-update-pending.json", value)
    return value


def connector_update_waiting(root: Path) -> bool:
    import psutil
    from .. import process_identity

    path = root / "connector-update-pending.json"
    if not path.exists():
        return False
    value = read(path)
    try:
        remaining = value["until_monotonic"] - time.monotonic()
        identity = value["process_identity"]
        process = psutil.Process(identity["pid"])
        return (
            value["format"] == 1
            and 0 < remaining <= 300
            and process.uids().real == os.getuid()
            and process.status() != psutil.STATUS_ZOMBIE
            and process_identity.matches(identity, process)
        )
    except (KeyError, TypeError, ValueError, OSError, psutil.Error):
        return False


def clear_connector_pause(root: Path) -> None:
    path = root / "connector-update-pending.json"
    if path.exists():
        read(path)
        path.unlink(missing_ok=True)


@contextmanager
def operator_lock(root: Path, *, wait_seconds: int = 60):
    """Let existing scans finish before an explicit operator gets its turn.

    Only lock acquisition is retried. Once yielded, a failed operation is never
    replayed. The existing process-identity/expiry check releases intake even
    when an operator dies before its finally block can run.
    """
    if type(wait_seconds) is not int or not 0 <= wait_seconds <= 300:
        raise ManifestError("Operator wait must be an integer from 0 to 300 seconds")
    deadline = time.monotonic() + wait_seconds
    owned_pause = None
    path = root / "connector-update-pending.json"
    try:
        with ExitStack() as stack:
            while True:
                try:
                    descriptor = stack.enter_context(lock(root))
                except OperationBusy:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise
                    if owned_pause is None and not connector_update_waiting(root):
                        owned_pause = pause_new_connector_scans(root)
                    time.sleep(min(0.25, remaining))
                else:
                    break
            yield descriptor
    finally:
        if owned_pause is not None and path.exists():
            if read(path) == owned_pause:
                clear_connector_pause(root)


def record(root: Path, event: str, **fields) -> None:
    path = root / "history.json"
    previous = read(path).get("events", []) if path.exists() else []
    if not isinstance(previous, list):
        raise ManifestError("Invalid managed update event history")
    # Reviewed public summaries only, never subprocess output or credentials.
    value = {"at": timestamp(), "event": event, **fields}
    write(path, {"events": [*previous[-19:], value]})
