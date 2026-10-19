"""Host-approved destinations; network credentials remain under OS-account control."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from ..portable_paths import portable_part
from ..private_input import read_private
from ..service.models import Command
from .format import JournalError


class SshAuthentication(Command):
    identity_file: Path
    known_hosts_file: Path

    @field_validator("identity_file", "known_hosts_file")
    @classmethod
    def private_path(cls, value):
        if (
            not value.is_absolute()
            or len(str(value)) > 4096
            or any(ord(c) < 32 or ord(c) == 127 for c in str(value))
        ):
            raise ValueError("Use an absolute path to a private SSH credential file")
        return value


class Destination(Command):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    label: str = Field(min_length=1, max_length=200)
    tenant_id: UUID
    space_id: UUID
    state_directory: Path
    remote: str | None = Field(default=None, max_length=2048)
    local_repository: Path | None = None
    ssh: SshAuthentication | None = None
    branch: str = Field(default="main", min_length=1, max_length=200)
    prefix: str = Field(default="memory/buffer", min_length=1, max_length=200)
    personal_data_scan: bool = True
    scanner: tuple[str, ...] = Field(default=(), max_length=16)
    max_batch_entries: int = Field(default=250, ge=1, le=2000)
    max_batch_bytes: int = Field(default=8 * 1024**2, ge=384 * 1024, le=32 * 1024**2)

    @field_validator("remote")
    @classmethod
    def git_remote(cls, value):
        if value is None:
            return value
        try:
            url = urlsplit(value)
            if (
                url.scheme not in {"https", "ssh"}
                or not url.hostname
                or url.hostname.startswith("-")
                or not url.hostname.isascii()
                or any(c in url.hostname for c in "%\\")
                or url.scheme == "https"
                and url.username is not None
                or url.scheme == "ssh"
                and not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}", url.username or "")
                or url.password is not None
                or url.query
                or url.fragment
                or not url.path
                or "\\" in value
                or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
                or url.port is not None
                and not 1 <= url.port <= 65535
            ):
                raise ValueError
        except ValueError:
            raise ValueError(
                "Use HTTPS without credentials or ssh://user@host/repository, without passwords, queries or fragments"
            ) from None
        return value

    @field_validator("branch")
    @classmethod
    def ref(cls, value):
        if (
            value.startswith(("-", "/"))
            or value.endswith(("/", "."))
            or ".." in value
            or "@{" in value
            or "//" in value
            or value == "@"
            or any(ord(c) < 33 or ord(c) == 127 or c in "~^:?*[\\" for c in value)
            or any(part.startswith(".") or part.endswith(".lock") for part in value.split("/"))
        ):
            raise ValueError("Use a literal Git branch name")
        return value

    @field_validator("prefix")
    @classmethod
    def portable_prefix(cls, value):
        path = PurePosixPath(value)
        if (
            not path.parts
            or path.is_absolute()
            or str(path) != value
            or any(not portable_part(p) or p.startswith(".") for p in path.parts)
        ):
            raise ValueError("Use a portable relative journal folder")
        return value

    @model_validator(mode="after")
    def destination(self):
        if bool(self.remote) == bool(self.local_repository):
            raise ValueError(
                "Choose an HTTPS/SSH remote or an explicitly selected local bare repository"
            )
        if (self.remote is not None and urlsplit(self.remote).scheme == "ssh") != (
            self.ssh is not None
        ):
            raise ValueError(
                "SSH requires a dedicated private key and pinned known-hosts file; other destinations must not include SSH settings"
            )
        for path in (self.state_directory, self.local_repository):
            if path is not None and not path.is_absolute():
                raise ValueError("Host destination paths must be absolute")
        if self.scanner and (
            not Path(self.scanner[0]).is_absolute()
            or any("\0" in arg or len(arg) > 4096 for arg in self.scanner)
        ):
            raise ValueError(
                "Use an absolute, operator-approved scanner executable and bounded arguments"
            )
        return self

    @property
    def fingerprint(self):
        # Adding optional SSH support must not invalidate existing approvals,
        # private spools or retry indexes for HTTPS/local destinations.
        excluded = {"label"} if self.ssh is not None else {"label", "ssh"}
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json", exclude=excluded), sort_keys=True).encode()
        ).hexdigest()

    @property
    def kind(self):
        return (
            "local_repository"
            if self.local_repository is not None
            else "ssh_repository"
            if self.ssh is not None
            else "https_repository"
        )


class Configuration(Command):
    destinations: list[Destination] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def unique(self):
        for values in (
            [d.id for d in self.destinations],
            [(d.tenant_id, d.space_id) for d in self.destinations],
            [str(d.state_directory).casefold() for d in self.destinations],
            [
                (d.remote or str(d.local_repository), d.branch, d.prefix.casefold())
                for d in self.destinations
            ],
        ):
            if len(values) != len(set(values)):
                raise ValueError(
                    "Each journal destination needs its own space, state folder and repository prefix"
                )
        return self

    @classmethod
    def from_environment(cls):
        path = os.environ.get("MNEMION_WRITEBACK_CONFIG")
        if not path:
            return cls()
        return cls.from_file(Path(path))

    @classmethod
    def from_file(cls, path):
        try:
            return cls.model_validate_json(read_private(Path(path), maximum=128 * 1024))
        except (OSError, ValueError):
            raise JournalError("invalid_writeback_configuration") from None
