"""Optional operator-approved language models; no model is started or downloaded."""

from __future__ import annotations

import hashlib
import json
import os
from functools import cached_property
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .librarian_models import PIPELINE_VERSION
from .model_config import TokenizerSpec


class LibrarianProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    label: str = Field(min_length=1, max_length=200)
    protocol: Literal["openai", "ollama"]
    endpoint: str = Field(min_length=1, max_length=2000)
    model: str = Field(min_length=1, max_length=300)
    revision: str = Field(min_length=1, max_length=300)
    response_model: str | None = Field(default=None, min_length=1, max_length=300)
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,99}$")
    api_key_header: Literal["Authorization", "api-key"] = "Authorization"
    ca_bundle_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,99}$")
    tokenizer: TokenizerSpec = Field(default_factory=TokenizerSpec)
    context_budget: int = Field(default=8192, ge=2048, le=32768)
    chat_overhead_reserve: int = Field(default=512, ge=128, le=2048)
    max_output_tokens: int = Field(default=1024, ge=256, le=8192)
    max_response_bytes: int = Field(default=262144, ge=4096, le=1048576)
    timeout_seconds: int = Field(default=45, ge=1, le=90)
    output_token_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_completion_tokens"
    json_mode: bool = True
    temperature: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    keep_alive_seconds: int = Field(default=0, ge=0, le=60)
    server_threads: int = Field(default=2, ge=1, le=8)
    thinking: bool | None = False

    @model_validator(mode="after")
    def transport(self):
        try:
            url = urlsplit(self.endpoint)
            port = url.port
        except ValueError:
            raise ValueError("Invalid librarian endpoint") from None
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.fragment
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in self.endpoint)
            or "\\" in self.endpoint
            or (port is not None and not 1 <= port <= 65535)
            or not url.path
            or url.path.endswith("/")
        ):
            raise ValueError("Use a complete HTTP(S) endpoint without URL credentials")
        if url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Non-loopback model endpoints require HTTPS")
        query = parse_qsl(url.query, keep_blank_values=True)
        if any(key != "api-version" for key, _ in query) or len(query) > 1:
            raise ValueError("Only one api-version query parameter is supported")
        if any(ord(c) < 32 for c in self.model + self.revision + (self.response_model or "")):
            raise ValueError("Model identities cannot contain control characters")
        if self.max_output_tokens + self.chat_overhead_reserve + 1024 > self.context_budget:
            raise ValueError("Reserve room for the prompt and evidence within the context budget")
        return self

    @property
    def network_egress(self) -> bool:
        return urlsplit(self.endpoint).hostname not in {"localhost", "127.0.0.1", "::1"}

    @cached_property
    def fingerprint(self) -> str:
        # Secret values are never read into configuration identity or public data.
        value = {"pipeline": PIPELINE_VERSION, **self.model_dump(exclude={"label"})}
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    def describe(self) -> dict:
        url = urlsplit(self.endpoint)
        return {
            "id": self.id,
            "label": self.label,
            "model": self.model,
            "revision": self.revision,
            "fingerprint": self.fingerprint,
            "protocol": self.protocol,
            "endpoint_origin": f"{url.scheme}://{url.netloc}",
            "network_egress": self.network_egress,
            "context_budget": self.context_budget,
            "token_count_unit": "utf8_bytes" if self.tokenizer.kind == "utf8" else "model_tokens",
            "max_output_tokens": self.max_output_tokens,
            "timeout_seconds": self.timeout_seconds,
        }


class LibrarianConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    profiles: list[LibrarianProfile] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def unique(self):
        if len({p.id for p in self.profiles}) != len(self.profiles):
            raise ValueError("Librarian profile IDs must be unique")
        return self

    @classmethod
    def from_environment(cls):
        value = os.environ.get("MNEMION_LIBRARIAN_CONFIG")
        if not value:
            return cls()
        try:
            path = Path(value)
            if not path.is_file() or path.stat().st_size > 131072:
                raise ValueError()
            with path.open("rb") as stream:
                content = stream.read(131073)
            if len(content) > 131072:
                raise ValueError()
            return cls.model_validate_json(content)
        except (OSError, ValueError):
            raise ValueError(
                "Invalid librarian configuration; values omitted from diagnostics"
            ) from None
