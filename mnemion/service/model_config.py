"""Operator-approved embedding configuration; credentials never enter a generation."""

from __future__ import annotations

import hashlib
import importlib.metadata
import re
from functools import cached_property
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .embeddings import Generation


class TokenizerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: Literal["utf8", "huggingface", "file"] = "utf8"
    repository: str | None = None
    revision: str | None = None
    sha256: str | None = None
    file_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,99}$")

    @model_validator(mode="after")
    def pinned(self):
        if self.kind == "utf8":
            if any((self.repository, self.revision, self.sha256, self.file_env)):
                raise ValueError("UTF-8 budgeting does not use tokenizer files")
        elif self.kind == "file":
            if (
                not self.file_env
                or self.repository
                or self.revision
                or not self.sha256
                or not re.fullmatch(r"[a-f0-9]{64}", self.sha256)
            ):
                raise ValueError("A local tokenizer needs an environment reference and SHA-256")
        elif self.file_env or not (
            self.repository
            and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository)
            and self.revision
            and re.fullmatch(r"[a-f0-9]{40}", self.revision)
            and self.sha256
            and re.fullmatch(r"[a-f0-9]{64}", self.sha256)
        ):
            raise ValueError("A Hugging Face tokenizer needs an immutable revision and SHA-256")
        return self


class RemoteEmbeddingProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    label: str = Field(min_length=1, max_length=200)
    protocol: Literal["openai", "ollama"]
    endpoint: str = Field(min_length=1, max_length=2000)
    model: str = Field(min_length=1, max_length=300)
    revision: str = Field(min_length=1, max_length=300)
    response_model: str | None = Field(default=None, min_length=1, max_length=300)
    dimensions: int = Field(ge=1, le=4096)
    send_dimensions: bool = False
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,99}$")
    api_key_header: Literal["Authorization", "api-key"] = "Authorization"
    ca_bundle_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,99}$")
    tokenizer: TokenizerSpec = Field(default_factory=TokenizerSpec)
    query_prefix: str = Field(default="", max_length=2000)
    document_prefix: str = Field(default="", max_length=2000)
    chunk_tokens: int = Field(default=512, ge=32, le=8192)
    overlap_tokens: int = Field(default=64, ge=0, le=4096)
    max_input_tokens: int = Field(default=4096, ge=64, le=32768)
    max_query_tokens: int = Field(default=2048, ge=32, le=32768)
    batch_size: int = Field(default=8, ge=1, le=32)
    max_document_bytes: int = Field(default=262144, ge=1024, le=1048576)
    max_response_bytes: int = Field(default=4194304, ge=4096, le=8388608)
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    document_timeout_seconds: int = Field(default=120, ge=1, le=600)
    max_queued: int = Field(default=4, ge=0, le=64)
    keep_alive_seconds: int = Field(default=30, ge=0, le=600)
    server_threads: int = Field(default=2, ge=1, le=32)

    @model_validator(mode="after")
    def safe_transport_and_limits(self):
        try:
            url = urlsplit(self.endpoint)
            port = url.port
        except ValueError:
            raise ValueError("Invalid embedding endpoint") from None
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.fragment
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in self.endpoint)
            or "\\" in self.endpoint
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise ValueError(
                "Embedding endpoints must be HTTP(S) URLs without embedded credentials"
            )
        if url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Non-loopback embedding endpoints require HTTPS")
        # Azure's api-version is permitted; credentials must use private headers.
        from urllib.parse import parse_qsl

        if any(key != "api-version" for key, _ in parse_qsl(url.query, keep_blank_values=True)):
            raise ValueError("Only the api-version endpoint query parameter is supported")
        if not url.path or url.path.endswith("/"):
            raise ValueError("Configure the complete embedding API endpoint path")
        if self.overlap_tokens >= self.chunk_tokens or self.overlap_tokens > self.chunk_tokens // 2:
            raise ValueError("Chunk overlap must be smaller than half the chunk budget")
        if (
            self.max_query_tokens > self.max_input_tokens
            or self.chunk_tokens > self.max_input_tokens
        ):
            raise ValueError("Query and chunk budgets cannot exceed the provider input limit")
        if self.document_timeout_seconds < self.timeout_seconds:
            raise ValueError("The document deadline cannot be shorter than one request timeout")
        if any(ord(c) < 32 for c in self.model + self.revision + (self.response_model or "")):
            raise ValueError("Model identities cannot contain control characters")
        return self

    @property
    def network_egress(self) -> bool:
        return urlsplit(self.endpoint).hostname not in {"localhost", "127.0.0.1", "::1"}

    @cached_property
    def generation(self) -> Generation:
        tokenizer = self.tokenizer.model_dump(exclude={"file_env"})
        if self.tokenizer.kind != "utf8":
            tokenizer["runtime_version"] = importlib.metadata.version("tokenizers")
        return Generation(
            self.model,
            self.dimensions,
            {
                "runtime": f"http-{self.protocol}",
                "pipeline": "mnemion-http-embeddings-v1",
                "revision": self.revision,
                "response_model": self.response_model or self.model,
                "endpoint_sha256": hashlib.sha256(self.endpoint.encode()).hexdigest(),
                "tokenizer": tokenizer,
                "token_count_unit": "utf8_bytes"
                if self.tokenizer.kind == "utf8"
                else "model_tokens",
                "chunk_tokens": self.chunk_tokens,
                "overlap_tokens": self.overlap_tokens,
                "max_query_tokens": self.max_query_tokens,
                "max_input_tokens": self.max_input_tokens,
                "send_dimensions": self.send_dimensions,
                "query_prefix": self.query_prefix,
                "document_prefix": self.document_prefix,
                "normalization": "l2",
                "offset_unit": "unicode_codepoints",
            },
        )


class EmbeddingConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    local_profiles: list[Literal["e5-small", "bge-small-en"]] = Field(
        default_factory=lambda: ["e5-small"]
    )
    remote_profiles: list[RemoteEmbeddingProfile] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def unique_profiles(self):
        ids = [*self.local_profiles, *(p.id for p in self.remote_profiles)]
        if len(ids) != len(set(ids)) or "e5-small" not in self.local_profiles:
            raise ValueError("Profile IDs must be unique and retain the existing E5 baseline")
        if any(p.id in {"e5-small", "bge-small-en"} for p in self.remote_profiles):
            raise ValueError("Remote profiles cannot replace a built-in local identity")
        generations = [p.generation.id for p in self.remote_profiles]
        if len(generations) != len(set(generations)):
            raise ValueError("Remote profiles must describe distinct embedding generations")
        return self

    @classmethod
    def from_file(cls, path: Path) -> "EmbeddingConfiguration":
        if not path.is_file() or path.stat().st_size > 131072:
            raise ValueError("Embedding configuration must be a file smaller than 128 KiB")
        try:
            with path.open("rb") as stream:
                content = stream.read(131073)
            if len(content) > 131072:
                raise ValueError("Embedding configuration exceeds 128 KiB")
            return cls.model_validate_json(content)
        except ValueError:
            # Operator files may accidentally contain a key in the wrong field.
            raise ValueError(
                "Invalid embedding configuration; values omitted from diagnostics"
            ) from None
