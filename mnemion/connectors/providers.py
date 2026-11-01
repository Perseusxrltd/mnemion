"""Filesystem, Git and rclone adapters. No source file or Git hook is executed."""

from __future__ import annotations

import errno
import fnmatch
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from .config import FilesystemConfig, GitConfig, RcloneConfig
from .protocol import Document, Scope, SkippedDocument
from .source_files import (
    INVENTORY_STOP_CODES,
    SourceReadError,
    classify_source_os_error,
    read_selected,
    relative_evidence,
)
from ..journal.format import journal_candidate


class ProviderError(RuntimeError):
    def __init__(self, code: str, *, access_lost=False, relative: str | None = None):
        super().__init__(code)
        self.code, self.access_lost, self.relative = code, access_lost, relative


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
    name = PurePosixPath(relative).name.lower()
    if name in {"vault-access.json", "host-secrets.json"} or name.endswith(
        (".mnemion-host", ".mnemion-ledger")
    ):
        return False
    return any(fnmatch.fnmatchcase(relative, pattern) for pattern in config.include) and not any(
        fnmatch.fnmatchcase(relative, pattern) for pattern in config.exclude
    )


def private_vault_content(text: str) -> bool:
    """Keep host keys, recovery controls and credential archives out of memory."""
    if re.search(r"\b(?:mnv_|mnm_bk_|mnm_)[A-Za-z0-9_-]{43}\b", text) or re.search(
        r'"format"\s*:\s*"mnemion-vault-(?:export|contents)"', text
    ):
        return True
    # Recognize actual control documents, including renamed copies, without
    # excluding prose that merely explains these configuration fields.
    if not text.lstrip().startswith("{"):
        return False
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        return False
    return isinstance(value, dict) and (
        any(
            isinstance(value.get(field), str)
            for field in ("database_url", "worker_database_url", "admin_database_url")
        )
        or value.get("format") == "mnemion-host-recovery-state"
        or isinstance(value.get("identifier"), str)
        and value["identifier"].startswith("mnemion-")
        and isinstance(value.get("environment"), dict)
    )


def document(
    config,
    relative: str,
    data: bytes,
    revision: str,
    uri: str | None = None,
    *,
    metadata: dict | None = None,
) -> Document | SkippedDocument | None:
    if len(data) > config.max_file_bytes:
        return SkippedDocument(relative, "source_too_large")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return SkippedDocument(relative, "source_is_not_utf8_text")
    if "\0" in text:
        return SkippedDocument(relative, "source_contains_binary_data")
    if private_vault_content(text) and not journal_candidate(relative, text):
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


def _directory_relative(root: Path, filename) -> str | None:
    """Source-relative directory, or nothing when that path is not safe to publish."""
    if not isinstance(filename, (str, bytes)):
        return None
    try:
        candidate = Path(os.fsdecode(filename))
        relative = candidate.relative_to(root).as_posix()
    except (TypeError, ValueError, UnicodeError):
        return None
    if relative in ("", "."):
        return None
    try:
        return relative_path(relative)
    except ProviderError:
        return None


def filesystem_paths(config, *, verify_files=True):
    """A complete selected path catalog; unreadable directories never mean empty."""
    root = config.path.expanduser().resolve()
    if not root.is_dir():
        raise ProviderError("source_folder_unavailable", access_lost=True)
    count = 0

    def failed(error):
        # The host path and strerror stay on the OSError and are not published.
        if isinstance(error, OSError):
            code = classify_source_os_error(error)
        else:
            code = "source_io_failed"
        raise ProviderError(
            code, relative=_directory_relative(root, getattr(error, "filename", None))
        ) from None

    for parent, dirs, files in os.walk(root, followlinks=False, onerror=failed):
        parent_path = Path(parent)
        dirs[:] = sorted(
            d
            for d in dirs
            if not any(
                fnmatch.fnmatchcase((parent_path / d).relative_to(root).as_posix() + "/", pattern)
                for pattern in config.exclude
            )
        )
        # Ordinary files in this directory are real selected files. Read them
        # before refusing a child link so the abort does not pretend they were unread.
        for filename in sorted(files):
            path = parent_path / filename
            rel = relative_path(path.relative_to(root).as_posix())
            if not selected(config, rel):
                continue
            # A symlink file is opened below and refused there, on Linux and
            # Windows, with a path and category. A catalog check alone can race.
            if verify_files and not path.is_symlink() and not path.is_file():
                raise ProviderError("source_symlinks_not_supported", relative=rel)
            count += 1
            if count > config.max_files:
                raise ProviderError("source_inventory_limit")
            yield rel
        for directory in dirs:
            candidate = parent_path / directory
            if not (candidate.is_symlink() or candidate.is_junction()):
                continue
            try:
                relative = relative_path(candidate.relative_to(root).as_posix())
            except (ProviderError, ValueError):
                relative = None
            raise ProviderError("source_symlinks_not_supported", relative=relative)


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
        paths = filesystem_paths(self.config)
        count = 0
        while True:
            try:
                rel = next(paths)
            except StopIteration:
                break
            except ProviderError as exc:
                if exc.code in INVENTORY_STOP_CODES:
                    evidence = relative_evidence(exc.relative)
                    # Stop with a receipt the owned run can finish. Do not walk on.
                    yield SkippedDocument(evidence.get("path", ""), exc.code, abort_inventory=True)
                    return
                raise
            count += 1
            try:
                data = read_selected(root, rel, self.config.max_file_bytes)
            except SourceReadError as exc:
                if exc.code == "source_too_large":
                    yield SkippedDocument(rel, exc.code)
                    yield None
                    continue
                if exc.code in INVENTORY_STOP_CODES:
                    # One unverified file ends the inventory. Later files are not skipped
                    # silently, and this receipt is not a successful scan.
                    yield SkippedDocument(exc.relative or rel, exc.code, abort_inventory=True)
                    return
                raise ProviderError(exc.code, relative=exc.relative) from None
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


def _permission_denied(exc: OSError) -> bool:
    if exc.errno in {errno.EACCES, errno.EPERM}:
        return True
    # Windows ERROR_ACCESS_DENIED. Do not infer this from POSIX mode bits.
    return getattr(exc, "winerror", None) == 5


def _invoking_process_can(path: Path, mode: int) -> bool:
    """Ask the OS about this process. Execute bits are not Windows ACLs."""
    if os.name == "nt":
        mode &= ~os.X_OK
        if mode == 0:
            return False
    return os.access(path, mode)


def _remote_cache_location(path: Path) -> str:
    """Classify a remote cache without creating it.

    "absent" means a missing leaf whose existing ancestor can hold Git's normal
    parent and cache creation. "present" means Git can be started at the path.
    A symlink is followed only as ``git -C`` and mkdir would follow it. The
    leaf is not created.
    """
    current = path
    while True:
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            parent = current.parent
            if parent == current:
                raise ProviderError("git_cache_ancestor_invalid")
            current = parent
            continue
        except OSError as exc:
            code = (
                "git_cache_ancestor_inaccessible"
                if _permission_denied(exc)
                else "git_cache_ancestor_invalid"
            )
            raise ProviderError(code) from None
        break
    if current != path:
        try:
            followed = os.stat(current)
        except OSError as exc:
            code = (
                "git_cache_ancestor_inaccessible"
                if _permission_denied(exc)
                else "git_cache_ancestor_invalid"
            )
            raise ProviderError(code) from None
        if not stat.S_ISDIR(followed.st_mode):
            raise ProviderError("git_cache_ancestor_invalid")
        if not _invoking_process_can(current, os.W_OK | os.X_OK):
            raise ProviderError("git_cache_ancestor_unusable")
        return "absent"
    try:
        followed = os.stat(path) if stat.S_ISLNK(info.st_mode) else info
    except OSError as exc:
        code = "git_cache_inaccessible" if _permission_denied(exc) else "git_cache_invalid"
        raise ProviderError(code) from None
    if not stat.S_ISDIR(followed.st_mode):
        raise ProviderError("git_cache_invalid")
    if not _invoking_process_can(path, os.R_OK | os.X_OK):
        raise ProviderError("git_cache_inaccessible")
    return "present"


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

    def _require_configured_origin(self) -> None:
        origin = self.git("remote", "get-url", "origin").decode().strip()
        if origin != self.config.remote:
            raise ProviderError("git_cache_remote_mismatch")

    def _runner_git_environment(self) -> dict[str, str]:
        """Environment the supervised connector actually gives Git.

        ``service_updates._environment`` drops ambient ``GIT_DIR``,
        ``GIT_WORK_TREE`` and Git config overrides. The two Git safety
        variables are set by this provider, as they are when the runner
        constructs ``GitProvider`` inside that filtered process.
        """
        from ..service.service_updates import _environment

        environment = _environment()
        environment["GIT_TERMINAL_PROMPT"] = "0"
        environment["GIT_OPTIONAL_LOCKS"] = "0"
        return environment

    def _inspect_git(self, *args: str) -> bytes:
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
            environment=self._runner_git_environment(),
        )

    def _inspect_text(self, *args: str) -> str:
        try:
            raw = self._inspect_git(*args)
        except ProviderError as exc:
            if exc.code != "provider_command_failed" or args[:2] != (
                "rev-parse",
                "--path-format=absolute",
            ):
                raise
            raw = self._inspect_git("rev-parse", *args[2:])
        try:
            return raw.decode()
        except UnicodeDecodeError:
            raise ProviderError("git_cache_invalid") from None

    def _metadata_path(self, text: str) -> Path:
        # ``git -C`` makes a relative answer relative to the configured path.
        path = Path(text)
        if not path.is_absolute():
            path = self.config.path / path
        return path

    def _metadata_directories(self) -> tuple[Path, Path, Path]:
        text = self._inspect_text(
            "rev-parse",
            "--path-format=absolute",
            "--absolute-git-dir",
            "--git-common-dir",
            "--git-path",
            "FETCH_HEAD",
        )
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) != 3:
            raise ProviderError("git_cache_invalid")
        git_dir, common_dir, fetch_head = (self._metadata_path(line) for line in lines)
        return git_dir, common_dir, fetch_head

    def _require_metadata_writable(self, git_dir: Path, common_dir: Path, fetch_head: Path) -> None:
        """Write and search on Git metadata only. Do not create files or locks."""
        checked = set()
        for directory in (git_dir, common_dir):
            key = os.fspath(directory)
            if key in checked:
                continue
            checked.add(key)
            try:
                info = os.lstat(directory)
                if stat.S_ISLNK(info.st_mode):
                    info = os.stat(directory)
            except OSError as exc:
                code = "git_cache_inaccessible" if _permission_denied(exc) else "git_cache_invalid"
                raise ProviderError(code) from None
            if not stat.S_ISDIR(info.st_mode):
                raise ProviderError("git_cache_invalid")
            if not _invoking_process_can(directory, os.W_OK | os.X_OK):
                raise ProviderError("git_cache_inaccessible")
        try:
            os.lstat(fetch_head)
        except FileNotFoundError:
            return
        except OSError as exc:
            code = "git_cache_inaccessible" if _permission_denied(exc) else "git_cache_invalid"
            raise ProviderError(code) from None
        if not _invoking_process_can(fetch_head, os.W_OK):
            raise ProviderError("git_cache_inaccessible")

    def _inspect_configured_origin(self) -> None:
        try:
            origin = self._inspect_text("remote", "get-url", "origin").strip()
        except UnicodeDecodeError:
            raise ProviderError("git_cache_invalid") from None
        if origin != self.config.remote:
            raise ProviderError("git_cache_remote_mismatch")

    def inspect_remote_cache(self) -> None:
        """Readiness for a remote cache this process can create or reuse.

        Does not clone, fetch, create the cache, or decide that the remote
        authorized this host. An absent cache is acceptable when an existing
        ancestor can hold the normal parent and cache creation performed later
        by scopes(). An existing bare repository or working tree is acceptable
        when its origin matches and this process can write the Git metadata
        the later fetch updates. Documents in a working tree are not required
        to be writable. The check uses the managed runner's filtered Git
        environment and this process's OS permissions only.
        """
        if not self.config.remote:
            return
        if _remote_cache_location(self.config.path) == "absent":
            return
        git_dir, common_dir, fetch_head = self._metadata_directories()
        self._require_metadata_writable(git_dir, common_dir, fetch_head)
        self._inspect_configured_origin()

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
            self._require_configured_origin()
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
                yield SkippedDocument(rel, "source_too_large")
                yield None
                continue
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
            if entry["Size"] < 0:
                raise ProviderError("source_too_large")
            if entry["Size"] > self.config.max_file_bytes:
                yield SkippedDocument(rel, "source_too_large")
                yield None
                continue
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
