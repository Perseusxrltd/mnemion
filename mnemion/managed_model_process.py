"""Private native model custody shared by local Mnemion processes.

Only a recorded process birth and its currently verified descendants can be
stopped. Names, listening ports and a responding model endpoint prove no custody.
Start scripts must keep their server in the foreground. WSL guest ownership is
not inferred from the native wsl.exe launcher.
"""

from __future__ import annotations

from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from uuid import uuid4

import psutil

from . import local_state, process_identity

MAX_PROCESSES = 512
MAX_LEASES = 128


class ModelControlError(RuntimeError):
    def __init__(self):
        super().__init__("The model process could not be verified; its saved custody was retained.")


class ModelController:
    def __init__(self, root: Path, *, clock=time.monotonic_ns):
        self.root = root
        self.path = root / "process.json"
        self.clock = clock
        self._child = None

    def _prepare(self):
        missing = []
        parent = self.root
        while not os.path.lexists(parent):
            missing.append(parent)
            parent = parent.parent
        for directory in reversed(missing):
            local_state.directory(directory)
        local_state.directory(self.root)

    def _read(self):
        try:
            record = local_state.read(self.path)
        except FileNotFoundError:
            return None
        if (
            set(record)
            != {"version", "state", "command", "launch", "process", "last_used_ns", "leases"}
            or type(record["version"]) is not int
            or record["version"] != 1
            or record["state"] not in ("active", "stopped")
            or type(record["command"]) is not str
            or re.fullmatch(r"[a-f0-9]{64}", record["command"]) is None
            or type(record["launch"]) is not str
            or re.fullmatch(r"[a-f0-9]{32}", record["launch"]) is None
            or type(record["last_used_ns"]) is not int
            or not 0 <= record["last_used_ns"] < 2**64
            or type(record["leases"]) is not dict
            or len(record["leases"]) > MAX_LEASES
            or (record["state"] == "stopped" and record["leases"])
        ):
            raise ModelControlError
        self._validate_identity(record["process"])
        for token, identity in record["leases"].items():
            if type(token) is not str or re.fullmatch(r"[a-f0-9]{32}", token) is None:
                raise ModelControlError
            self._validate_identity(identity)
        return record

    @staticmethod
    def _validate_identity(identity):
        if (
            type(identity) is not dict
            or type(identity.get("pid")) is not int
            or not 0 < identity["pid"] < 2**32
            or type(identity.get("format")) is not int
            or identity["format"] != 1
        ):
            raise ModelControlError
        if identity.get("kind") == "linux-start":
            if (
                set(identity) != {"format", "kind", "pid", "boot", "ticks"}
                or type(identity["boot"]) is not str
                or re.fullmatch(r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}", identity["boot"])
                is None
                or type(identity["ticks"]) is not int
                or not 0 <= identity["ticks"] < 2**64
            ):
                raise ModelControlError
        elif identity.get("kind") == "creation-time":
            if (
                set(identity) != {"format", "kind", "pid", "created"}
                or type(identity["created"]) not in (int, float)
                or not 0 < identity["created"] < 2**63
            ):
                raise ModelControlError
        else:
            raise ModelControlError

    @staticmethod
    def _process(identity):
        try:
            process = psutil.Process(identity["pid"])
            if process.status() == psutil.STATUS_ZOMBIE or not process_identity.matches(
                identity, process
            ):
                return None
            return process
        except (psutil.NoSuchProcess, ProcessLookupError, FileNotFoundError):
            return None

    @staticmethod
    def _protected_pids():
        return {os.getpid(), *(parent.pid for parent in psutil.Process().parents())}

    def owned(self, *, launch=None):
        if not os.path.lexists(self.root):
            return False
        with local_state.lock(self.root):
            record = self._read()
            return bool(
                record
                and record["state"] == "active"
                and (launch is None or record["launch"] == launch)
                and self._process(record["process"])
            )

    def launch_identity(self):
        if not os.path.lexists(self.root):
            return None
        with local_state.lock(self.root):
            record = self._read()
            return (
                record["launch"]
                if record and record["state"] == "active" and self._process(record["process"])
                else None
            )

    def launch(self, command, *, _locked=False):
        if (
            not isinstance(command, list)
            or not command
            or any(type(part) is not str or not part or "\0" in part for part in command)
        ):
            raise ModelControlError
        self._prepare()
        signature = hashlib.sha256(json.dumps(command, ensure_ascii=True).encode()).hexdigest()
        with nullcontext() if _locked else local_state.lock(self.root):
            previous = self._read()
            if previous and previous["state"] == "active" and self._process(previous["process"]):
                if previous["command"] != signature:
                    raise ModelControlError
                return False
            options = (
                {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
                if os.name == "nt"
                else {"start_new_session": True}
            )
            child = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                **options,
            )
            self._child = child
            identity = None
            try:
                process = psutil.Process(child.pid)
                if process.ppid() != os.getpid() or process.pid in self._protected_pids():
                    raise ModelControlError
                identity = process_identity.capture(process)
                local_state.write(
                    self.path,
                    {
                        "version": 1,
                        "state": "active",
                        "command": signature,
                        "launch": uuid4().hex,
                        "process": identity,
                        "last_used_ns": self.clock(),
                        "leases": {},
                    },
                )
            except BaseException:
                # This live Popen handle belongs to this launch, never a lookup
                # by executable name. Retain uncertain custody instead of retrying.
                if identity is not None:
                    self._terminate(identity)
                elif child.poll() is None:
                    child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)
                raise
            return True

    def begin_activity(self):
        if not os.path.lexists(self.root):
            return None
        with local_state.lock(self.root):
            record = self._read()
            if not record or record["state"] != "active" or not self._process(record["process"]):
                return None
            self._prune_leases(record)
            if len(record["leases"]) >= MAX_LEASES:
                raise ModelControlError
            token = uuid4().hex
            record["leases"][token] = process_identity.capture(psutil.Process())
            record["last_used_ns"] = self.clock()
            local_state.write(self.path, record)
            return record["launch"], token

    def end_activity(self, activity):
        if activity is None:
            return
        with local_state.lock(self.root):
            record = self._read()
            if record and record["launch"] == activity[0] and activity[1] in record["leases"]:
                del record["leases"][activity[1]]
                record["last_used_ns"] = self.clock()
                local_state.write(self.path, record)

    def _prune_leases(self, record):
        # A long request is still active. Only a verifiably ended/reused caller
        # can lose its lease; unreadable identity prevents automatic stopping.
        for token, identity in list(record["leases"].items()):
            if self._process(identity) is None:
                del record["leases"][token]

    def _signal(self, identity, *, force=False):
        try:
            process = self._process(identity)
            if process is None:
                return None
            if (
                sys.platform == "linux"
                and hasattr(os, "pidfd_open")
                and hasattr(signal, "pidfd_send_signal")
            ):
                descriptor = os.pidfd_open(process.pid)
                try:
                    # Bind the signal to this kernel process, then verify its
                    # birth again. PID recycling cannot retarget this handle.
                    if self._process(identity) is None:
                        return None
                    signal.pidfd_send_signal(
                        descriptor, signal.SIGKILL if force else signal.SIGTERM
                    )
                finally:
                    os.close(descriptor)
            elif force:
                process.kill()
            else:
                process.terminate()
            return process
        except (psutil.NoSuchProcess, ProcessLookupError, FileNotFoundError):
            return None

    def _terminate(self, identity):
        parent = self._process(identity)
        if parent is None:
            return True
        protected = self._protected_pids()
        if parent.pid in protected:
            raise ModelControlError
        children = parent.children(recursive=True)
        if len(children) >= MAX_PROCESSES:
            raise ModelControlError
        targets = []
        for process in [*reversed(children), parent]:
            try:
                if process.pid in protected:
                    raise ModelControlError
                target = process_identity.capture(process)
                if process.pid != parent.pid and not any(
                    ancestor.pid == parent.pid and process_identity.matches(identity, ancestor)
                    for ancestor in process.parents()
                ):
                    continue
                if process_identity.matches(target, process):
                    targets.append(target)
            except (psutil.NoSuchProcess, FileNotFoundError, ProcessLookupError):
                continue
        if self._process(identity) is None:
            return True
        waiting = []
        for target in targets:
            process = self._signal(target)
            if process is not None:
                waiting.append(process)
        psutil.wait_procs(waiting, timeout=5)
        waiting = []
        for target in targets:
            process = self._signal(target, force=True)
            if process is not None:
                waiting.append(process)
        psutil.wait_procs(waiting, timeout=2)
        if self._child is not None:
            self._child.poll()
        return all(self._process(target) is None for target in targets)

    def stop(self, *, launch=None, idle_seconds=None, only_unused=False, _locked=False):
        if not os.path.lexists(self.root):
            return False
        with nullcontext() if _locked else local_state.lock(self.root):
            record = self._read()
            if not record or (launch is not None and record["launch"] != launch):
                return False
            if record["state"] == "stopped":
                return idle_seconds is None and not only_unused
            original = {**record, "leases": dict(record["leases"])}
            if idle_seconds is not None or only_unused:
                self._prune_leases(record)
                if record["leases"]:
                    return False
            if idle_seconds is not None:
                if type(idle_seconds) is not int or idle_seconds <= 0:
                    return False
                elapsed = self.clock() - record["last_used_ns"]
                if elapsed < idle_seconds * 1_000_000_000:
                    return False
            if not self._terminate(record["process"]):
                return False
            if self._read() != original:
                raise ModelControlError
            record["state"] = "stopped"
            record["leases"] = {}
            local_state.write(self.path, record)
            return True

    def restart(self, command, *, may_start=lambda: True):
        """Keep stop/relaunch under one lock; explicit stopped state wins."""
        if not os.path.lexists(self.root):
            return False
        with local_state.lock(self.root):
            record = self._read()
            if not record or record["state"] != "active":
                return False
            if not self.stop(launch=record["launch"], only_unused=True, _locked=True):
                return False
            if may_start() is not True:
                return False
            return self.launch(command, _locked=True)
