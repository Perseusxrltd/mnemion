"""Strict, portable connector configuration with credential references only."""

from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from ..service.models import Command


def service_url(value: str) -> str:
    url = urlsplit(value)
    local = url.hostname in {"localhost", "127.0.0.1", "::1"}
    if url.scheme != "https" and not (url.scheme == "http" and local):
        raise ValueError("Use HTTPS for a remote memory service")
    if not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("Service URLs cannot contain credentials, queries, or fragments")
    return value.rstrip("/")


class Token(Command):
    env: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    file: Path | None = None

    @model_validator(mode="after")
    def one_reference(self):
        if bool(self.env) == bool(self.file):
            raise ValueError("Choose one environment variable or private token file")
        return self

    def read(self) -> str:
        import os

        if self.env:
            token = os.environ.get(self.env, "")
        else:
            with self.file.expanduser().open("r", encoding="utf-8") as stream:
                token = stream.read(16385)
        token = token.strip()
        if not token or len(token) > 16384 or any(ord(c) < 33 or ord(c) > 126 for c in token):
            raise ValueError("The credential reference does not contain a valid token")
        return token


class FileSelection(Command):
    include: list[str] = Field(
        default_factory=lambda: ["*.md", "*.markdown", "*.txt", "*.json", "*.jsonl", "*.csv"]
    )
    exclude: list[str] = Field(
        default_factory=lambda: [
            ".git/*",
            "*/.git/*",
            ".obsidian/*",
            "*/.obsidian/*",
            ".mnemion*",
            "*/.mnemion*",
            "node_modules/*",
            "*/node_modules/*",
            ".env*",
            "*/.env*",
            "*credentials*.json",
            "*secrets*.json",
            "*service-account*.json",
            "*.pem",
            "*.key",
        ]
    )
    max_files: int = Field(default=100000, ge=1, le=1000000)
    max_file_bytes: int = Field(default=20_000_000, ge=1, le=100_000_000)
    include_generated: bool = False
    normalize_conversations: bool = False


class PublishedSource(FileSelection):
    scope_id: str = Field(min_length=1, max_length=400)
    name: str = Field(min_length=1, max_length=200)
    members: list[str] = Field(max_length=10000)
    # Required acknowledgement: these sources do not expose effective provider ACLs.
    publish_to_mapped_members: Literal[True]


class FilesystemConfig(PublishedSource):
    type: Literal["filesystem"] = "filesystem"
    path: Path


class GitConfig(PublishedSource):
    type: Literal["git"] = "git"
    path: Path
    remote: str | None = None
    ref: str = Field(default="HEAD", min_length=1, max_length=512, pattern=r"^[^-\x00-\x20]+$")
    web_url: str | None = None

    @field_validator("remote")
    @classmethod
    def safe_remote(cls, value):
        if value is None:
            return value
        url = urlsplit(value)
        if url.scheme not in {"https", "ssh"} or not url.hostname or url.password:
            raise ValueError("Git remotes require an HTTPS or ssh:// URL without embedded secrets")
        if url.scheme == "https" and url.username:
            raise ValueError("Use the Git credential manager instead of URL credentials")
        return value


class RcloneConfig(PublishedSource):
    type: Literal["rclone"] = "rclone"
    remote: str = Field(min_length=3, max_length=4096, pattern=r"^[A-Za-z0-9_-]+:[^\r\n\x00]*$")
    config_file: Path | None = None


class SlackConfig(Command):
    type: Literal["slack"] = "slack"
    token: Token
    team_id: str = Field(pattern=r"^[TE][A-Z0-9]+$")
    channels: list[str] = Field(min_length=1, max_length=10000)
    include_threads: bool = True
    page_size: int = Field(default=15, ge=1, le=200)
    max_messages: int = Field(default=100000, ge=1, le=1000000)

    @field_validator("channels")
    @classmethod
    def channel_ids(cls, value):
        import re

        if any(not re.fullmatch(r"[CGD][A-Z0-9]+", channel) for channel in value):
            raise ValueError("Use Slack channel IDs")
        return list(dict.fromkeys(value))


class DriveConfig(FileSelection):
    type: Literal["gdrive"] = "gdrive"
    token: Token
    folder_ids: list[str] = Field(default_factory=list, max_length=10000)
    file_ids: list[str] = Field(default_factory=list, max_length=10000)
    recursive: bool = True

    @model_validator(mode="after")
    def selected_roots(self):
        import re

        if not self.folder_ids and not self.file_ids:
            raise ValueError("Select Drive folder or file IDs explicitly")
        if any(
            not re.fullmatch(r"[A-Za-z0-9_-]+", identifier)
            for identifier in self.folder_ids + self.file_ids
        ):
            raise ValueError("Invalid Drive ID")
        return self


Provider = Annotated[
    FilesystemConfig | GitConfig | RcloneConfig | SlackConfig | DriveConfig,
    Field(discriminator="type"),
]


class ConnectorConfig(Command):
    version: Literal[1] = 1
    service_url: str
    service_token: Token
    connector_id: UUID
    provider: Provider
    access_lease_seconds: int = Field(default=900, ge=60, le=86400)
    poll_seconds: int = Field(default=300, ge=30, le=86400)

    _service_url = field_validator("service_url")(service_url)


def read_config(path: Path) -> ConnectorConfig:
    if path.stat().st_size > 1_000_000:
        raise ValueError("Connector configuration exceeds 1 MB")
    result = ConnectorConfig.model_validate_json(path.read_text(encoding="utf-8"))
    # Relative paths consistently resolve beside the configuration on every OS.
    base = path.resolve().parent
    tokens = [result.service_token]
    if isinstance(result.provider, (SlackConfig, DriveConfig)):
        tokens.append(result.provider.token)
    for token in tokens:
        if token.file is not None and not token.file.is_absolute():
            token.file = base / token.file
    for field in ("path", "config_file"):
        value = getattr(result.provider, field, None)
        if value is not None and not value.is_absolute():
            setattr(result.provider, field, base / value)
    return result
