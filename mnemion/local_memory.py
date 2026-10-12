"""Private host-operator RAM policy shared by Studio and local agents."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import os
import re
import threading
import time
from uuid import uuid4

from pydantic import Field, ValidationError

from . import local_state as state
from . import process_identity
from .service.memory_budget import MemoryBudget, MemoryOptions


class MemoryChange(MemoryOptions):
    expected_revision: str | None = Field(default=None, min_length=1, max_length=64)


class MemoryRepair(MemoryOptions):
    repair_token: str = Field(pattern=r"^[a-f0-9]{64}$")


def _parse(content: bytes) -> dict:
    try:
        value = json.loads(content)
        if (
            not isinstance(value, dict)
            or type(value["format"]) is not int
            or value["format"] != 1
            or not isinstance(value["revision"], str)
            or not re.fullmatch(r"[a-z0-9-]{1,64}", value["revision"])
            or value["revision"] == "default"
        ):
            raise ValueError("Invalid policy record")
        options = MemoryOptions.model_validate(value["settings"])
        return {
            "format": 1,
            "revision": value["revision"],
            "settings": options.model_dump(),
            **(
                {"updated_at": value["updated_at"]}
                if isinstance(value.get("updated_at"), str) and len(value["updated_at"]) <= 64
                else {}
            ),
        }
    except (KeyError, ValueError, TypeError, RecursionError):
        raise state.LocalSetupError(
            "memory_policy_damaged",
            "The saved RAM policy needs repair. New model work is paused until you choose a replacement budget.",
        ) from None


def policy(root: Path) -> dict:
    try:
        state._regular(root / "resource-policy", directory=True)
        return _parse(state.read_bytes(root / "resource-policy" / "memory.json"))
    except FileNotFoundError:
        raise state.LocalSetupError(
            "memory_policy_missing",
            "The saved RAM policy is missing. Choose a replacement budget before resuming model work.",
        ) from None


def _observed(root: Path) -> tuple[bytes | None, str]:
    path = root / "resource-policy" / "memory.json"
    folder = state._regular(root, directory=True)
    workspace = repr(
        (folder.st_dev, folder.st_ino, os.path.normcase(str(root.absolute())))
    ).encode()
    try:
        before = state._regular(path)
        content = state.read_bytes(path)
        after = state._regular(path)

        def identity(info):
            return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

        if identity(before) != identity(after):
            raise state.LocalSetupError(
                "memory_policy_changed", "The RAM policy changed. Refresh its status."
            )
        digest = hashlib.sha256(
            workspace + repr(identity(after)).encode() + b"\0" + content
        ).hexdigest()
        return content, digest
    except FileNotFoundError:
        return None, hashlib.sha256(workspace + b"\0missing-memory-policy").hexdigest()


def inspection(root: Path) -> dict:
    """Keep local setup usable without exposing damaged bytes or inventing settings."""
    try:
        state.directory(root)
        if (root / "resource-policy").exists() or (root / "resource-policy").is_symlink():
            state.directory(root / "resource-policy")
        content, token = _observed(root)
        if content is not None:
            try:
                return {"memory_policy": _parse(content), "memory_recovery": None}
            except state.LocalSetupError:
                pass
        return {
            "memory_policy": None,
            "memory_recovery": {
                "code": "memory_policy_missing" if content is None else "memory_policy_damaged",
                "message": "The saved RAM policy is missing."
                if content is None
                else "The saved RAM policy cannot be understood.",
                "repair_token": token,
            },
        }
    except (state.LocalSetupError, OSError):
        return {
            "memory_policy": None,
            "memory_recovery": {
                "code": "memory_policy_inaccessible",
                "message": "The RAM policy cannot be read safely. Check that its folder belongs to this OS account, has no links, and its file is readable and no larger than 256 KiB. Refresh after correcting storage access.",
                "repair_token": None,
            },
        }


def _configured_directory(root: Path) -> Path:
    state.directory(root)
    if not (root / "configuration.json").exists():
        raise state.LocalSetupError(
            "not_configured", "Create the local workspace before changing its RAM budget."
        )
    state.read(root / "configuration.json")
    return state.directory(root / "resource-policy")


def _replacement(options: MemoryOptions) -> dict:
    return {
        "format": 1,
        "revision": uuid4().hex,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "settings": {"mode": options.mode, "limit_mib": options.limit_mib},
    }


def configure(root: Path, change: MemoryChange, *, initial: bool = False) -> dict:
    directory = _configured_directory(root)
    with state.lock(directory):
        if initial:
            value = _replacement(change)
            state.write(directory / "memory.json", value, replace=False)
            return value
        current = policy(root)
        if change.expected_revision is not None and change.expected_revision != current["revision"]:
            raise state.LocalSetupError(
                "memory_policy_changed",
                "The RAM budget changed in another session. Refresh it before applying your changes.",
            )
        value = _replacement(change)
        state.write(directory / "memory.json", value)
        return value


def repair(root: Path, change: MemoryRepair) -> dict:
    directory = _configured_directory(root)
    with state.lock(directory):
        content, token = _observed(root)
        if token != change.repair_token:
            raise state.LocalSetupError(
                "memory_policy_changed",
                "The RAM policy changed after inspection. Refresh before repairing it.",
            )
        if content is not None:
            try:
                _parse(content)
            except state.LocalSetupError:
                pass
            else:
                raise state.LocalSetupError(
                    "memory_policy_changed",
                    "The RAM policy is already valid. Refresh to use its current settings.",
                )
        value = _replacement(change)
        if content is None:
            state.write(directory / "memory.json", value, replace=False)
        else:
            state.replace_damaged(directory / "memory.json", value, expected=content)
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
        if not process_identity.matches_record(value, process, legacy_field="created_at"):
            return None
        return value["memory"]
    except (
        OSError,
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
        process = psutil.Process()
        self.created_at = process.create_time()
        self.process_identity = process_identity.capture(process)
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
        now = time.monotonic()
        self.emit({"event": "resources", "memory": memory})
        if now - self.last_write >= 5:
            state.write(
                self.root / "runtime-memory.json",
                {
                    "format": 1,
                    "pid": os.getpid(),
                    "created_at": self.created_at,
                    "process_identity": self.process_identity,
                    "sampled_at": time.time(),
                    "memory": memory,
                },
            )
            self.last_write = now

    def close(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=5)
        (self.root / "runtime-memory.json").unlink(missing_ok=True)
