"""Encrypted backup delivery with a fresh Git readback, without a checkout."""

from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import threading
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .. import local_state
from ..journal.config import Destination, SshAuthentication
from ..journal.git import environment
from ..journal.process import run
from ..journal.ssh import transport
from ..private_input import read_private
from ..service import update_state as state_io
from . import HostControlError
from .protocol import Document, canonical

CHUNK = 8 * 1024 * 1024
OID = re.compile(r"^[a-f0-9]{40}(?:[a-f0-9]{24})?$")
STAGES = frozenset(
    {
        "init",
        "hash-object",
        "mktree",
        "commit-tree",
        "push",
        "ls-remote",
        "fetch",
        "rev-parse",
        "cat-file",
    }
)
FAILURES = frozenset({"deadline", "storage_guard", "git_exit", "process_io", "transport_setup"})


class BackupTransferError(HostControlError):
    """A small fixed diagnostic; never include Git output or exception text."""

    def __init__(self, stage, reason, exit_code=None):
        if stage not in STAGES or reason not in FAILURES:
            raise ValueError("Use a documented backup transfer diagnostic")
        if exit_code is not None and (type(exit_code) is not int or not -255 <= exit_code <= 255):
            raise ValueError("Use a bounded process exit code")
        super().__init__(
            "backup_delivery_unconfirmed", "Inspect the original backup transfer before recovery."
        )
        self.stage, self.reason, self.exit_code = stage, reason, exit_code

    def diagnostic(self):
        return {"stage": self.stage, "reason": self.reason, "exit_code": self.exit_code}


class GitDestination(Document):
    remote: str | None = Field(default=None, max_length=2048)
    local_repository: Path | None = None
    ssh: SshAuthentication | None = None
    token_file: Path | None = None
    token_username: str = Field(default="x-access-token", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    branch_prefix: str = Field(default="mnemion-host-backups", max_length=160)
    network_timeout_seconds: int = Field(default=300, strict=True, ge=30, le=1800)

    @field_validator("remote")
    @classmethod
    def remote_address(cls, value):
        return Destination.git_remote(value)

    @field_validator("branch_prefix")
    @classmethod
    def prefix(cls, value):
        return Destination.ref(value)

    @model_validator(mode="after")
    def destination(self):
        if bool(self.remote) == bool(self.local_repository):
            raise ValueError("Choose one explicitly configured Git backup destination.")
        scheme = urlsplit(self.remote).scheme if self.remote else None
        if (scheme == "ssh") != (self.ssh is not None):
            raise ValueError("SSH backup delivery requires a dedicated key and pinned host keys.")
        if self.token_file is not None and scheme != "https":
            raise ValueError("A Git HTTPS token is only used with an HTTPS destination.")
        for path in (self.local_repository, self.token_file):
            if path is not None and (not path.is_absolute() or len(str(path)) > 4096):
                raise ValueError("Choose absolute, bounded backup configuration paths.")
        return self

    @property
    def remote_storage(self):
        return self.remote is not None


def _disk_usage(root, maximum):
    pending, size, count = [root], 0, 0
    while pending:
        try:
            entries = os.scandir(pending.pop())
        except FileNotFoundError:
            continue
        with entries:
            for entry in entries:
                count += 1
                try:
                    info = entry.stat(follow_symlinks=False)
                except FileNotFoundError:
                    continue  # Git atomically renames its own temporary files.
                if count > 20000 or stat.S_ISLNK(info.st_mode):
                    raise HostControlError("backup_capacity", "Inspect backup transport storage.")
                if stat.S_ISDIR(info.st_mode):
                    pending.append(entry.path)
                elif stat.S_ISREG(info.st_mode):
                    size += info.st_size
                    if size > maximum:
                        raise HostControlError(
                            "backup_capacity", "Backup transport exceeded its disk budget."
                        )
                else:
                    raise HostControlError("backup_capacity", "Inspect backup transport storage.")
    return size


class Repository:
    def __init__(self, root, destination, *, budget, progress=None):
        self.root = local_state.directory(root, exist_ok=False)
        self.repository = self.root / "repository.git"
        self.destination = destination
        self.remote = destination.remote or str(destination.local_repository)
        self.budget = budget
        self.progress = progress
        self.env = environment()
        self.env.update(
            {
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_AUTHOR_NAME": "Perseus XR",
                "GIT_COMMITTER_NAME": "Perseus XR",
            }
        )
        if destination.token_file is not None:
            import base64

            token = read_private(destination.token_file, maximum=16384).decode().strip()
            if not token or any(ord(c) < 33 or ord(c) == 127 for c in token):
                raise HostControlError(
                    "backup_credentials", "Inspect the private Git backup token."
                )
            secret = base64.b64encode((destination.token_username + ":" + token).encode()).decode()
            self.env.update(
                {
                    "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "http.extraHeader",
                    "GIT_CONFIG_VALUE_0": "Authorization: Basic " + secret,
                }
            )
        self.git("init", "--bare", str(self.repository), in_repository=False)

    def git(self, *arguments, input=None, maximum=1024 * 1024, accepted=(0,), in_repository=True):
        stage = arguments[0]
        if stage not in STAGES:
            raise ValueError("Use a documented backup Git operation")
        network = arguments[0] in {"fetch", "push", "ls-remote"}
        command = [
            "git",
            "--literal-pathspecs",
            "-c",
            "core.hooksPath=" + os.devnull,
            "-c",
            "protocol.allow=never",
            "-c",
            "protocol.https.allow=always",
            "-c",
            "http.followRedirects=false",
            "-c",
            "credential.interactive=never",
            "-c",
            "gc.auto=0",
            "-c",
            "maintenance.auto=false",
            # Ciphertext cannot usefully compress or delta against other parts.
            # Avoid expensive packing and keep per-thread delta buffers bounded.
            "-c",
            "core.compression=0",
            "-c",
            "pack.compression=0",
            "-c",
            "pack.window=0",
            "-c",
            "pack.threads=1",
        ]
        if self.destination.local_repository is not None:
            command += ["-c", "protocol.file.allow=always"]
        if self.destination.ssh is not None:
            command += ["-c", "protocol.https.allow=never", "-c", "protocol.ssh.allow=always"]
        if in_repository:
            command += ["-C", str(self.repository)]
        cancelled, finished = threading.Event(), threading.Event()
        exceeded = []

        def monitor():
            while not finished.wait(0.1):
                try:
                    _disk_usage(self.root, self.budget)
                except Exception:
                    exceeded.append(True)
                    cancelled.set()
                    return

        guard = threading.Thread(target=monitor, daemon=True)
        guard.start()
        code = None
        try:
            self.record(stage, "running")
            with (
                transport(self.destination, self.root, self.env)
                if network and self.destination.ssh is not None
                else nullcontext(self.env)
            ) as env:
                code, output = run(
                    command + list(arguments),
                    input=input,
                    env=env,
                    timeout=self.destination.network_timeout_seconds if network else 60,
                    maximum=maximum,
                    cancel=cancelled,
                    pass_fds=state_io.inherited_locks(),
                )
            _disk_usage(self.root, self.budget)
            if exceeded or code not in accepted:
                raise BackupTransferError(stage, "storage_guard" if exceeded else "git_exit", code)
            self.record(stage, "succeeded")
            return output
        except (ValueError, OSError, TimeoutError) as error:
            if isinstance(error, BackupTransferError):
                failure = error
            else:
                from ..journal.format import JournalError

                reason = "transport_setup"
                if exceeded or (
                    isinstance(error, HostControlError) and error.code == "backup_capacity"
                ):
                    reason = "storage_guard"
                elif isinstance(error, TimeoutError):
                    reason = "deadline"
                elif isinstance(error, JournalError):
                    reason = (
                        "deadline" if str(error) == "journal_program_interrupted" else "process_io"
                    )
                failure = BackupTransferError(stage, reason, code)
            self.record(stage, "failed", failure.diagnostic())
            raise failure from None
        finally:
            finished.set()
            guard.join(2)

    def record(self, stage, state, diagnostic=None):
        if self.progress is not None:
            from .protocol import timestamp

            state_io.write(
                self.progress,
                {"stage": stage, "state": state, "at": timestamp(), "diagnostic": diagnostic},
            )

    @staticmethod
    def oid(data):
        value = data.decode("ascii").strip()
        if not OID.fullmatch(value):
            raise HostControlError("backup_delivery_unconfirmed", "Inspect the backup Git object.")
        return value

    def head(self, ref):
        output = self.git(
            "ls-remote",
            "--exit-code",
            "--heads",
            "--",
            self.remote,
            ref,
            maximum=1024,
            accepted=(0, 2),
        )
        if not output.strip():
            return None
        fields = output.decode("ascii").strip().split()
        if len(fields) != 2 or fields[1] != ref:
            raise HostControlError(
                "backup_delivery_unconfirmed", "Inspect the backup Git reference."
            )
        return self.oid(fields[0].encode())


def deliver(root, destination, *, host_id, operation_id, files, maximum):
    """A unique backup branch contains encrypted parts and a bounded manifest."""
    host, operation = str(UUID(str(host_id))), str(UUID(str(operation_id)))
    total = sum(path.stat().st_size for path in files.values())
    if not 1 <= total <= maximum or shutil.disk_usage(root).free < total * 3 + 64 * 1024**2:
        raise HostControlError("backup_capacity", "Make room for the bounded encrypted backup.")
    if set(files) != {"bundle", "ledger"}:
        raise HostControlError(
            "invalid_backup", "Deliver the encrypted host package and access ledger."
        )
    manifest = {
        "format": "mnemion-host-backup-v1",
        "host_id": host,
        "operation_id": operation,
        "parts": [],
        "files": {},
    }
    ref = f"refs/heads/{destination.branch_prefix}/{host}/{operation}"
    progress = root / "transfer-progress.json"
    with local_state.temporary_directory(prefix="backup-git-", dir=root) as temporary:
        upload = Repository(
            temporary / "upload", destination, budget=total * 2 + 16 * 1024**2, progress=progress
        )
        entries = []
        for kind, path in files.items():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                index = 0
                while content := stream.read(CHUNK):
                    digest.update(content)
                    name = f"{kind}-{index:04d}.enc"
                    oid = upload.oid(upload.git("hash-object", "-w", "--stdin", input=content))
                    entries.append(f"100644 blob {oid}\t{name}\0".encode())
                    manifest["parts"].append(
                        {
                            "name": name,
                            "sha256": hashlib.sha256(content).hexdigest(),
                            "bytes": len(content),
                            "kind": kind,
                        }
                    )
                    index += 1
            manifest["files"][kind] = {"sha256": digest.hexdigest(), "bytes": path.stat().st_size}
        document = canonical(manifest)
        if len(document) > 256 * 1024:
            raise HostControlError("backup_capacity", "The backup manifest exceeds its budget.")
        oid = upload.oid(upload.git("hash-object", "-w", "--stdin", input=document))
        entries.append(f"100644 blob {oid}\tmanifest.json\0".encode())
        tree = upload.oid(upload.git("mktree", "-z", input=b"".join(sorted(entries))))
        commit = upload.oid(upload.git("commit-tree", tree, "-m", "Encrypted Mnemion host backup"))
        manifest_hash = hashlib.sha256(document).hexdigest()
        state_io.write(
            root / "delivery-intent.json",
            {
                "format": 1,
                "host_id": host,
                "operation_id": operation,
                "commit": commit,
                "ref": ref,
                "manifest_sha256": manifest_hash,
                "manifest": manifest,
            },
            replace=False,
        )
        # No force push and no shared branch rewrite. If the acknowledgement
        # is lost, inspect this same unique branch through a clean reader.
        push_error = None
        try:
            upload.git("push", "--porcelain", "--", upload.remote, commit + ":" + ref)
        except Exception as error:
            push_error = error
        try:
            verify(
                temporary,
                destination,
                host_id=host,
                operation_id=operation,
                commit=commit,
                manifest_sha256=manifest_hash,
                files=manifest["files"],
                maximum=maximum,
                progress=progress,
            )
        except Exception:
            if isinstance(push_error, BackupTransferError):
                upload.record(push_error.stage, "failed", push_error.diagnostic())
                raise push_error from None
            raise
        return {
            "commit": commit,
            "ref": ref,
            "manifest_sha256": manifest_hash,
            "files": manifest["files"],
            "remote_readback_verified": True,
            "remote_storage": destination.remote_storage,
        }


def verify(
    root,
    destination,
    *,
    host_id,
    operation_id,
    commit,
    manifest_sha256,
    files,
    maximum,
    progress=None,
):
    """A fresh reader proves the original remote bytes without repeating a push."""
    host, operation = str(UUID(str(host_id))), str(UUID(str(operation_id)))
    ref = f"refs/heads/{destination.branch_prefix}/{host}/{operation}"
    if not OID.fullmatch(commit) or not re.fullmatch(r"[a-f0-9]{64}", manifest_sha256):
        raise HostControlError("invalid_backup", "Inspect the recorded backup identity.")
    with local_state.temporary_directory(prefix="backup-readback-", dir=root) as temporary:
        reader = Repository(
            temporary / "reader", destination, budget=maximum * 2 + 16 * 1024**2, progress=progress
        )
        if reader.head(ref) != commit:
            raise HostControlError(
                "backup_delivery_unconfirmed", "Inspect the original backup operation."
            )
        reader.git(
            "fetch", "--depth=1", "--no-tags", "--no-recurse-submodules", "--", reader.remote, ref
        )
        if reader.oid(reader.git("rev-parse", "--verify", "FETCH_HEAD^{commit}")) != commit:
            raise HostControlError("backup_delivery_unconfirmed", "The backup reference changed.")
        document = reader.git("cat-file", "blob", commit + ":manifest.json", maximum=256 * 1024)
        if hashlib.sha256(document).hexdigest() != manifest_sha256:
            raise HostControlError("backup_delivery_unconfirmed", "The backup manifest changed.")
        manifest = json.loads(document)
        if (
            manifest["format"] != "mnemion-host-backup-v1"
            or manifest["host_id"] != host
            or manifest["operation_id"] != operation
            or manifest["files"] != files
            or set(files) != {"bundle", "ledger"}
            or not 1 <= len(manifest["parts"]) <= maximum // CHUNK + 2
        ):
            raise HostControlError("invalid_backup", "Inspect the recorded backup manifest.")
        digests = {kind: hashlib.sha256() for kind in files}
        sizes = {kind: 0 for kind in files}
        seen = set()
        for part in manifest["parts"]:
            if (
                part["kind"] not in files
                or not re.fullmatch(r"(?:bundle|ledger)-[0-9]{4}\.enc", part["name"])
                or part["name"] in seen
                or type(part["bytes"]) is not int
                or not 1 <= part["bytes"] <= CHUNK
            ):
                raise HostControlError("invalid_backup", "Inspect the recorded backup parts.")
            seen.add(part["name"])
            content = reader.git("cat-file", "blob", commit + ":" + part["name"], maximum=CHUNK)
            if (
                len(content) != part["bytes"]
                or hashlib.sha256(content).hexdigest() != part["sha256"]
            ):
                raise HostControlError(
                    "backup_delivery_unconfirmed", "The encrypted backup readback failed."
                )
            digests[part["kind"]].update(content)
            sizes[part["kind"]] += len(content)
        if sum(sizes.values()) > maximum or any(
            digests[kind].hexdigest() != value["sha256"] or sizes[kind] != value["bytes"]
            for kind, value in files.items()
        ):
            raise HostControlError(
                "backup_delivery_unconfirmed", "The complete encrypted backup differs."
            )
        return {"remote_readback_verified": True, "remote_storage": destination.remote_storage}
