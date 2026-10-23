"""Detached durable work, protected for the full lifetime of its subprocesses."""

import fcntl
import os
from pathlib import Path
import stat
import subprocess

import psutil

from .. import process_identity
from ..service import service_updates as updates, update_state as state_io
from . import HostControlError
from .installation import settings
from .protocol import canonical, parse, timestamp
from .runtime import current
from .store import Store


def launch(root, value, store):
    if not store.needs_worker():
        return None
    try:
        with state_io.lock(root / "worker") as descriptor:
            runtime = updates.resolved_runtime(
                Path(value["service_state"]), runtime=current(root, value)["current"]
            )
            command = [
                runtime["python"],
                *(["-I"] if runtime["isolated"] else []),
                "-m",
                "mnemion.host_control.cli",
                "work",
                "--state-dir",
                str(root),
                "--lock-fd",
                str(descriptor),
            ]
            # This program writes only its reviewed CLI outcome. Subcommands
            # have their existing bounded, private managed-update logs.
            log_path = root / "logs/worker.log"
            log_fd = os.open(
                log_path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600
            )
            try:
                info = os.fstat(log_fd)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.getuid()
                    or info.st_mode & 0o077
                ):
                    raise HostControlError("invalid_state", "Inspect the private host worker log.")
                os.ftruncate(log_fd, 0)
                return subprocess.Popen(
                    command,
                    cwd=runtime["directory"],
                    env=updates._environment(),
                    stdin=subprocess.DEVNULL,
                    stdout=log_fd,
                    stderr=log_fd,
                    start_new_session=True,
                    pass_fds=(descriptor,),
                )
            finally:
                os.close(log_fd)
    except state_io.OperationBusy:
        return None


def work(root: Path, descriptor: int):
    root, value = settings(root)
    info = os.fstat(descriptor)
    lock = root / "worker/operation.lock"
    expected = lock.lstat()
    if (
        descriptor < 3
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
        or (info.st_dev, info.st_ino) != (expected.st_dev, expected.st_ino)
    ):
        raise HostControlError("invalid_worker", "Use the independently supervised host worker.")
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    store = Store(root / "authority")
    from . import adapter

    try:
        with state_io.command_custody(descriptor):
            store.interrupted()
            state_io.write(
                root / "worker/process.json",
                {
                    "process_identity": process_identity.capture(psutil.Process()),
                    "started_at": timestamp(),
                },
            )
            while job := store.claim():
                changed = False

                def before_effect():
                    nonlocal changed
                    store.guard(job["operation_id"], record_effect=True)
                    changed = True

                try:
                    result, context = adapter.execute(
                        root,
                        value,
                        store,
                        job,
                        parse(canonical(job["request"])),
                        before_effect=before_effect,
                    )
                    store.finish(job["operation_id"], result=result, context=context)
                except Exception as error:
                    if changed:
                        from .backup_git import BackupTransferError

                        result = (
                            {"backup_transfer": error.diagnostic()}
                            if isinstance(error, BackupTransferError)
                            else None
                        )
                        store.inspection(job["operation_id"], result=result)
                        break
                    code = error.code if isinstance(error, HostControlError) else "operation_failed"
                    if code not in {
                        "host_busy",
                        "host_unavailable",
                        "authority_changed",
                        "plan_changed",
                        "backup_required",
                        "backup_configuration_changed",
                        "backup_not_found",
                        "request_expired",
                    }:
                        code = "operation_failed"
                    store.finish(job["operation_id"], error=code)
            return 0
    finally:
        os.close(descriptor)
