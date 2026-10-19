"""Filesystem, Git and rclone adapters. No source file or Git hook is executed."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from .config import FilesystemConfig, GitConfig, RcloneConfig
from .protocol import Document, Scope
from .source_files import SourceReadError, read_selected


class ProviderError(RuntimeError):
    def __init__(self, code: str, *, access_lost=False):
        super().__init__(code)
        self.code, self.access_lost = code, access_lost


def relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or str(path) != value
        or ".." in path.parts
        or any(ord(c) < 32 for c in value)
        or "\\" in value
    ):
        raise ProviderError("invalid_source_path")
    return value


def selected(config, relative: str) -> bool:
    if PurePosixPath(relative).name.lower() == "vault-access.json":
        return False
    return any(fnmatch.fnmatchcase(relative, pattern) for pattern in config.include) and not any(
        fnmatch.fnmatchcase(relative, pattern) for pattern in config.exclude
    )


def private_vault_content(text: str) -> bool:
    """Never capture a host vault key or a vault archive as searchable memory."""
    return bool(
        re.search(r"\bmnv_[A-Za-z0-9_-]{43}\b", text)
        or re.search(r'"format"\s*:\s*"mnemion-vault-(?:export|contents)"', text)
    )


def document(
    config,
    relative: str,
    data: bytes,
    revision: str,
    uri: str | None = None,
    *,
    metadata: dict | None = None,
) -> Document | None:
    if len(data) > config.max_file_bytes:
        raise ProviderError("source_too_large")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ProviderError("source_is_not_utf8_text") from None
    if "\0" in text:
        raise ProviderError("source_contains_binary_data")
    if private_vault_content(text):
        return None
    if not config.include_generated and re.search(
        r"(?m)^mnemion_managed:\s*true\s*$", text[:16000]
    ):
        return None
    return Document(
        external_id=relative,
        revision=revision,
        title=relative,
        text=text,
        uri=uri,
        media_type="text/markdown"
        if Path(relative).suffix.lower() in {".md", ".markdown"}
        else "text/plain",
        metadata={
            "path": relative,
            "original_sha256": hashlib.sha256(data).hexdigest(),
            "original_size_bytes": len(data),
            **(metadata or {}),
        },
        normalize_conversations=config.normalize_conversations
        and Path(relative).suffix.lower() in {".json", ".jsonl"},
    )


def command(args: list[str], *, maximum=64_000_000, timeout=120, environment=None) -> bytes:
    """Bound disk, memory, diagnostics and execution time while the command runs."""
    with tempfile.SpooledTemporaryFile(max_size=min(maximum, 1_000_000)) as output:
        try:
            process = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                start_new_session=os.name != "nt",
            )
        except OSError:
            raise ProviderError("provider_command_unavailable") from None
        overflow = threading.Event()
        read_failed = threading.Event()

        def stop():
            if process.poll() is not None:
                return
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=5,
                        check=False,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                else:
                    os.killpg(process.pid, signal.SIGKILL)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()

        def drain(pipe, limit, destination=None):
            size = 0
            try:
                while chunk := pipe.read1(65536):
                    size += len(chunk)
                    if size > limit:
                        overflow.set()
                        stop()
                        return
                    if destination is not None:
                        destination.write(chunk)
            except (OSError, ValueError):
                read_failed.set()
                stop()
            finally:
                pipe.close()

        readers = [
            threading.Thread(target=drain, args=(process.stdout, maximum, output), daemon=True),
            threading.Thread(target=drain, args=(process.stderr, 1_000_000), daemon=True),
        ]
        for reader in readers:
            reader.start()
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            stop()
            process.wait(timeout=5)
        except BaseException:
            # Ctrl-C or managed shutdown must also drain a provider command in
            # its own process group; do not leave Git/rclone holding cache locks.
            stop()
            process.wait(timeout=5)
            raise
        finally:
            for reader in readers:
                reader.join(5)
        if overflow.is_set():
            raise ProviderError("provider_output_too_large")
        if timed_out or read_failed.is_set() or any(reader.is_alive() for reader in readers):
            raise ProviderError("provider_command_unavailable")
        if process.returncode:
            raise ProviderError("provider_command_failed")
        output.seek(0)
        return output.read(maximum + 1)


class FilesystemProvider:
    access_mode = "published"

    def __init__(self, config: FilesystemConfig):
        self.config = config

    def scopes(self):
        return ["filesystem:" + self.config.scope_id]

    def access(self, scope_id: str) -> Scope:
        if scope_id not in self.scopes() or not self.config.path.is_dir():
            raise ProviderError("source_folder_unavailable", access_lost=True)
        return Scope(scope_id, self.config.name, self.config.members)

    def documents(self, scope_id: str):
        root = self.config.path.expanduser().resolve()
        count = 0

        def failed(error):
            raise ProviderError("source_folder_unreadable") from None

        for parent, dirs, files in os.walk(root, followlinks=False, onerror=failed):
            dirs[:] = sorted(
                d
                for d in dirs
                if not any(
                    fnmatch.fnmatchcase(
                        (Path(parent) / d).relative_to(root).as_posix() + "/", pattern
                    )
                    for pattern in self.config.exclude
                )
            )
            if any(
                (Path(parent) / directory).is_symlink() or (Path(parent) / directory).is_junction()
                for directory in dirs
            ):
                raise ProviderError("source_symlinks_not_supported")
            for filename in sorted(files):
                path = Path(parent) / filename
                rel = relative_path(path.relative_to(root).as_posix())
                if not selected(self.config, rel):
                    continue
                if path.is_symlink() or not path.is_file():
                    raise ProviderError("source_symlinks_not_supported")
                count += 1
                if count > self.config.max_files:
                    raise ProviderError("source_inventory_limit")
                try:
                    data = read_selected(root, rel, self.config.max_file_bytes)
                except SourceReadError as exc:
                    raise ProviderError(exc.code) from None
                result = document(
                    self.config,
                    rel,
                    data,
                    hashlib.sha256(data).hexdigest(),
                    "mnemion-source://filesystem/"
                    + quote(self.config.scope_id, safe="")
                    + "/"
                    + quote(rel, safe="/"),
                )
                if result:
                    yield result
                if count % 10 == 0:
                    yield None


class GitProvider:
    access_mode = "published"

    def __init__(self, config: GitConfig):
        self.config = config
        self.environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
        self.commit = None

    def git(self, *args, maximum=64_000_000):
        return command(
            [
                "git",
                "-c",
                "core.hooksPath=" + os.devnull,
                "-c",
                "protocol.file.allow=never",
                "-C",
                str(self.config.path),
                *args,
            ],
            maximum=maximum,
            environment=self.environment,
        )

    def scopes(self):
        if self.config.remote:
            if not self.config.path.exists():
                self.config.path.parent.mkdir(parents=True, exist_ok=True)
                stage = Path(tempfile.mkdtemp(prefix="mnemion-git-", dir=self.config.path.parent))
                try:
                    command(
                        [
                            "git",
                            "-c",
                            "core.hooksPath=" + os.devnull,
                            "-c",
                            "protocol.file.allow=never",
                            "clone",
                            "--bare",
                            "--no-hardlinks",
                            "--",
                            self.config.remote,
                            str(stage),
                        ],
                        environment=self.environment,
                    )
                    stage.rename(self.config.path)
                finally:
                    shutil.rmtree(stage, ignore_errors=True)
            # Refuse to reuse an arbitrary repository for a different remote.
            origin = self.git("remote", "get-url", "origin").decode().strip()
            if origin != self.config.remote:
                raise ProviderError("git_cache_remote_mismatch")
            self.git("fetch", "--prune", "--no-tags", "origin", self.config.ref)
            reference = "FETCH_HEAD"
        else:
            reference = self.config.ref
        self.commit = (
            self.git("rev-parse", "--verify", "--end-of-options", reference + "^{commit}")
            .decode()
            .strip()
        )
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", self.commit):
            raise ProviderError("invalid_git_commit")
        return ["git:" + self.config.scope_id]

    def access(self, scope_id: str):
        if scope_id != "git:" + self.config.scope_id or not self.config.path.is_dir():
            raise ProviderError("git_repository_unavailable", access_lost=True)
        return Scope(scope_id, self.config.name, self.config.members)

    def documents(self, scope_id: str):
        if self.commit is None:
            raise ProviderError("git_snapshot_not_selected")
        entries = self.git("ls-tree", "-rlz", "--full-tree", self.commit).split(b"\0")
        count = 0
        for entry in entries:
            if not entry:
                continue
            attributes, raw_path = entry.split(b"\t", 1)
            mode, kind, oid, size = attributes.split()
            try:
                rel = relative_path(raw_path.decode("utf-8"))
            except UnicodeDecodeError:
                raise ProviderError("git_path_is_not_utf8") from None
            if not selected(self.config, rel):
                continue
            if kind != b"blob" or mode not in (b"100644", b"100755"):
                raise ProviderError("git_links_or_submodules_not_supported")
            count += 1
            if count > self.config.max_files:
                raise ProviderError("source_inventory_limit")
            if int(size) > self.config.max_file_bytes:
                raise ProviderError("source_too_large")
            blob = oid.decode("ascii")
            if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", blob):
                raise ProviderError("invalid_git_object")
            data = self.git("cat-file", "blob", blob, maximum=self.config.max_file_bytes)
            # Pin evidence to the last change of this path in the selected
            # snapshot. A repository-wide HEAD is not a document revision:
            # putting it in metadata or the URI revises every memory on every
            # unrelated commit. Literal pathspecs also handle names such as
            # "[draft].md" without accidentally selecting another document.
            commit_details = (
                self.git(
                    "--literal-pathspecs",
                    "log",
                    "-1",
                    "--format=%H%n%cI",
                    "--no-show-signature",
                    "--no-patch",
                    self.commit,
                    "--",
                    rel,
                    maximum=256,
                )
                .decode("ascii")
                .strip()
                .splitlines()
            )
            if len(commit_details) != 2:
                raise ProviderError("invalid_git_source_commit")
            source_commit, source_modified = commit_details
            if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", source_commit):
                raise ProviderError("invalid_git_source_commit")
            try:
                if datetime.fromisoformat(source_modified).utcoffset() is None:
                    raise ValueError
            except ValueError:
                raise ProviderError("invalid_git_source_time") from None
            uri = (
                self.config.web_url.rstrip("/")
                + "/blob/"
                + source_commit
                + "/"
                + quote(rel, safe="/")
                if self.config.web_url
                else "mnemion-source://git/" + source_commit + "/" + quote(rel, safe="/")
            )
            result = document(
                self.config,
                rel,
                data,
                # Backfill the new date once, then retain per-file stability.
                source_commit + ":" + blob + ":source-time-v1",
                uri,
                metadata={
                    "git_commit": source_commit,
                    "git_blob": blob,
                    "source_modified_at": source_modified,
                },
            )
            if result:
                yield result
            if count % 10 == 0:
                yield None


class RcloneProvider:
    access_mode = "published"

    def __init__(self, config: RcloneConfig):
        self.config = config

    def rclone(self, *args, maximum=64_000_000):
        options = ["--config", str(self.config.config_file)] if self.config.config_file else []
        return command(["rclone", *options, *args], maximum=maximum)

    def scopes(self):
        return ["rclone:" + self.config.scope_id]

    def access(self, scope_id):
        if scope_id not in self.scopes():
            raise ProviderError("unknown_source_scope")
        return Scope(scope_id, self.config.name, self.config.members)

    def documents(self, scope_id):
        entries = json.loads(
            self.rclone("lsjson", "--recursive", "--files-only", "--hash", "--", self.config.remote)
        )
        if not isinstance(entries, list) or len(entries) > self.config.max_files:
            raise ProviderError("source_inventory_limit")
        seen = set()
        for index, entry in enumerate(entries):
            rel = relative_path(entry["Path"])
            if rel in seen:
                raise ProviderError("ambiguous_remote_path")
            seen.add(rel)
            if entry.get("IsDir") or not selected(self.config, rel):
                continue
            if entry["Size"] > self.config.max_file_bytes or entry["Size"] < 0:
                raise ProviderError("source_too_large")
            data = self.rclone(
                "cat",
                "--",
                self.config.remote.rstrip("/") + "/" + rel,
                maximum=self.config.max_file_bytes,
            )
            # Verify provider hashes when available; a changed object aborts the
            # snapshot instead of authorizing a destructive missing-item sweep.
            for algorithm in ("sha256", "sha1", "md5"):
                expected = (entry.get("Hashes") or {}).get(algorithm)
                if (
                    expected
                    and hashlib.new(algorithm, data, usedforsecurity=False).hexdigest()
                    != expected.lower()
                ):
                    raise ProviderError("remote_object_changed_during_read")
            if len(data) != entry["Size"]:
                raise ProviderError("remote_object_changed_during_read")
            revision = hashlib.sha256(
                (
                    hashlib.sha256(data).hexdigest()
                    + json.dumps(
                        {"modified": entry.get("ModTime"), "id": entry.get("ID")}, sort_keys=True
                    )
                ).encode()
            ).hexdigest()
            result = document(
                self.config,
                rel,
                data,
                revision,
                "mnemion-source://rclone/"
                + quote(self.config.scope_id, safe="")
                + "/"
                + quote(rel, safe="/"),
                metadata={"remote_modified_at": entry.get("ModTime"), "remote_id": entry.get("ID")},
            )
            if result:
                yield result
            if index % 10 == 0:
                yield None
