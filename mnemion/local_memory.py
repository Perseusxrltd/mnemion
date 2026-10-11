"""Private host-operator RAM policy shared by Studio and local agents."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import os
import threading
import time
from uuid import uuid4

from pydantic import Field, ValidationError

from . import local_state as state
from .service.memory_budget import MemoryBudget, MemoryOptions


class MemoryChange(MemoryOptions):
    expected_revision: str | None = Field(default=None, min_length=1, max_length=64)


def policy(root: Path, fallback: MemoryOptions | None = None) -> dict:
    path = root / "resource-policy" / "memory.json"
    try:
        value = state.read(path)
    except FileNotFoundError:
        return {
            "format": 1,
            "revision": "default",
            "settings": (fallback or MemoryOptions()).model_dump(),
        }
    try:
        if (
            value["format"] != 1
            or not isinstance(value["revision"], str)
            or len(value["revision"]) > 64
        ):
            raise ValueError("Invalid policy record")
        options = MemoryOptions.model_validate(value["settings"])
        return {**value, "settings": options.model_dump()}
    except (KeyError, ValueError, TypeError):
        raise state.LocalSetupError(
            "memory_policy_damaged",
            "The saved RAM policy needs recovery. Model work is paused until it can be read safely.",
        ) from None


def configure(root: Path, change: MemoryChange) -> dict:
    state.directory(root)
    if not (root / "configuration.json").exists():
        raise state.LocalSetupError(
            "not_configured", "Create the local workspace before changing its RAM budget."
        )
    state.read(root / "configuration.json")
    directory = state.directory(root / "resource-policy")
    with state.lock(directory):
        current = policy(root)
        if change.expected_revision is not None and change.expected_revision != current["revision"]:
            raise state.LocalSetupError(
                "memory_policy_changed",
                "The RAM budget changed in another session. Refresh it before applying your changes.",
            )
        value = {
            "format": 1,
            "revision": uuid4().hex,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "settings": change.model_dump(exclude={"expected_revision"}),
        }
        state.write(directory / "memory.json", value)
        return value


def live_status(root: Path) -> dict | None:
    """Do not represent a stale snapshot or reused process PID as live."""
    import psutil

    try:
        value = state.read(root / "runtime-memory.json")
        if (
            value["format"] != 1
            or time.time() - value["sampled_at"] > 15
            or value["sampled_at"] > time.time() + 1
        ):
            return None
        process = psutil.Process(value["pid"])
        if process.create_time() != value["created_at"]:
            return None
        return value["memory"]
    except (
        FileNotFoundError,
        KeyError,
        TypeError,
        ValueError,
        psutil.Error,
        state.LocalSetupError,
    ):
        return None


class MemoryMonitor:
    def __init__(self, root: Path, budget: MemoryBudget, emit):
        import psutil

        self.root, self.budget, self.emit = root, budget, emit
        self.created_at = psutil.Process().create_time()
        self.last_write = 0.0
        self.last_revision = ""
        self.stopped = threading.Event()
        self.thread = None

    def start(self):
        self.tick()

        def monitor():
            while not self.stopped.wait(2):
                try:
                    self.tick()
                except (state.LocalSetupError, OSError):
                    self.budget.policy_unavailable()

        self.thread = threading.Thread(target=monitor, name="mnemion-memory-budget", daemon=True)
        self.thread.start()

    def tick(self):
        try:
            value = policy(self.root)
            if value["revision"] == "default" and self.last_revision not in {"", "default"}:
                raise state.LocalSetupError(
                    "memory_policy_missing", "The saved RAM policy is missing."
                )
            if value["revision"] != self.last_revision:
                self.last_revision = value["revision"]
                self.last_write = 0
            self.budget.configure(
                MemoryOptions.model_validate(value["settings"]), value["revision"]
            )
        except (state.LocalSetupError, ValidationError, OSError):
            self.budget.policy_unavailable()
        self.budget.trim()
        memory = self.budget.snapshot()
        now = time.time()
        self.emit({"event": "resources", "memory": memory})
        if now - self.last_write >= 5:
            state.write(
                self.root / "runtime-memory.json",
                {
                    "format": 1,
                    "pid": os.getpid(),
                    "created_at": self.created_at,
                    "sampled_at": now,
                    "memory": memory,
                },
            )
            self.last_write = now

    def close(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=5)
        (self.root / "runtime-memory.json").unlink(missing_ok=True)
