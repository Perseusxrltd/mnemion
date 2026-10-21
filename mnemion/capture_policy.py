"""Portable, explicit selection rules for approved JSONL conversation sources."""

import fnmatch
import hashlib
from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .capture_identity import canonical_capture_json
from .service.models import Command

SOURCE_EXCLUSIONS = (
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
)


class CapturePolicy(Command):
    format: Literal["mnemion-capture-policy-v1"] = "mnemion-capture-policy-v1"
    preset: Literal["selected", "conversation", "detailed"]
    capture_mode: Literal["messages", "complete"]
    include: list[str] = Field(default_factory=lambda: ["*.jsonl"], min_length=1, max_length=64)
    exclude: list[str] = Field(default_factory=list, max_length=64)
    retention: Literal["source_mirror", "until_deleted"]
    max_file_bytes: int = Field(default=1_000_000_000, ge=1, le=1_000_000_000_000, strict=True)
    max_record_bytes: int = Field(default=2_000_000, ge=1, le=16_000_000, strict=True)

    @field_validator("include", "exclude")
    @classmethod
    def patterns(cls, values):
        if len(set(values)) != len(values) or any(
            not 1 <= len(value) <= 512
            or value.startswith("/")
            or ".." in value.split("/")
            or "\\" in value
            or ":" in value
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
            for value in values
        ):
            raise ValueError("Use distinct relative filename patterns with forward slashes")
        return values

    @model_validator(mode="after")
    def preset_mode(self):
        if (
            self.preset == "conversation"
            and self.capture_mode != "messages"
            or self.preset == "detailed"
            and self.capture_mode != "complete"
            or self.max_record_bytes > self.max_file_bytes
        ):
            raise ValueError("Match the preset's content and keep record size within file size")
        return self

    @property
    def revision(self):
        return hashlib.sha256(canonical_capture_json(self.model_dump(mode="json"))).hexdigest()

    def provider_fields(self):
        return {
            "include": self.include,
            "exclude": list(dict.fromkeys([*SOURCE_EXCLUSIONS, *self.exclude])),
            "max_file_bytes": self.max_file_bytes,
            "max_record_bytes": self.max_record_bytes,
            "capture_mode": self.capture_mode,
        }

    def allows_path(self, path):
        if not isinstance(path, str) or not path or len(path) > 4096:
            return False
        parts = PurePosixPath(path)
        if (
            parts.is_absolute()
            or ".." in parts.parts
            or "\\" in path
            or any(ord(char) < 32 or ord(char) == 127 for char in path)
            or not path.lower().endswith(".jsonl")
        ):
            return False
        return any(fnmatch.fnmatchcase(path, rule) for rule in self.include) and not any(
            fnmatch.fnmatchcase(path, rule) for rule in (*SOURCE_EXCLUSIONS, *self.exclude)
        )
