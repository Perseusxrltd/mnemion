"""Bounded source drainage for explicit host operations, without effect replay."""

from contextlib import contextmanager
from pathlib import Path

from ..service import update_state
from . import HostControlError


@contextmanager
def operator_lock(root: Path):
    # A full source scan can legitimately exceed the ordinary one-minute wait.
    # The native pause expires after five minutes or when its owner exits; it
    # stops new scans while letting current readers retain their runtime lease.
    try:
        with update_state.operator_lock(root, wait_seconds=300):
            yield
    except update_state.OperationBusy:
        raise HostControlError(
            "host_busy",
            "The host is finishing another operation or source scan. "
            "Inspect its status and the original operation before requesting new work.",
        ) from None
