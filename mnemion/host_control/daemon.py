"""Restricted independent listener, with detached work and bounded restart."""

import asyncio
from pathlib import Path
import signal
import time

import psutil

from .. import process_identity
from ..service import supervision, update_state as state_io
from ..version import __version__
from . import adapter, runtime, worker
from .installation import settings
from .protocol import timestamp
from .server import listen
from .store import Store


async def serve(root: Path):
    root, value = settings(root)
    store = Store(root / "authority")
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stopped.set)
    children = set()
    check_runtime_at = 0
    receipt = {
        "host_id": value["host_id"],
        "protocol": 1,
        "pid": psutil.Process().pid,
        "process_identity": process_identity.capture(psutil.Process()),
        "version": __version__,
        "ready_at": timestamp(),
    }
    try:
        async with listen(
            store,
            supervision._bytes(root / "host.key", 16384),
            host=value["bind"],
            port=value["port"],
            host_status=lambda: adapter.status(root, value, store),
        ):
            await asyncio.to_thread(runtime.acknowledge, root, value)
            state_io.write(root / "ready.json", receipt)
            while not stopped.is_set():
                children = {child for child in children if child.poll() is None}
                try:
                    child = await asyncio.to_thread(worker.launch, root, value, store)
                    if child is not None:
                        children.add(child)
                except Exception:
                    state_io.write(
                        root / "worker-attention.json",
                        {
                            "at": timestamp(),
                            "code": "host_worker_needs_inspection",
                        },
                    )
                if not children and time.monotonic() >= check_runtime_at:
                    check_runtime_at = time.monotonic() + 30
                    try:
                        if await asyncio.to_thread(runtime.promote, root, value, store):
                            return 0
                    except Exception:
                        # The accepted controller remains available. No failed
                        # runtime is executed and no raw exception is published.
                        state_io.write(
                            root / "runtime-attention.json",
                            {
                                "at": timestamp(),
                                "code": "control_update_needs_inspection",
                            },
                        )
                try:
                    await asyncio.wait_for(stopped.wait(), timeout=2)
                except TimeoutError:
                    pass
        return 0
    finally:
        path = root / "ready.json"
        try:
            if state_io.read(path) == receipt:
                path.unlink()
        except (OSError, ValueError):
            pass
        for child in children:
            child.poll()  # Live detached jobs retain their own locks and receipts.
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(signum)
