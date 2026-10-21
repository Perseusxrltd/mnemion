"""Per-command RSS guard for the headless CLI on Windows, macOS and Linux."""

from contextlib import contextmanager
import json
import os
import sys
import threading

import psutil

from .conversation_inbox import InboxError


@contextmanager
def bounded(memory_limit_mib):
    process, stopped = psutil.Process(), threading.Event()
    limit = memory_limit_mib * 1024**2
    if process.memory_info().rss > limit:
        raise InboxError("capture_memory_limit")

    def watch():
        while not stopped.wait(1):
            if process.memory_info().rss > limit:
                # Never race the active SQLite writer by trying to repair it
                # from this thread. Its transaction rolls back on exit; the
                # durable process record reports an interrupted scan next time.
                print(
                    json.dumps({"event": "connector_scan_failed", "error": "capture_memory_limit"}),
                    file=sys.stderr,
                    flush=True,
                )
                os._exit(2)

    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=2)
