"""Data models for raw sources and source chunks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RawSource:
    id: str
    uri: str = ""
    file_path: str = ""
    source_type: str = "unknown"
    title: str = ""
    author: str = ""
    captured_at: str = ""
    content_hash: str = ""
    raw_text_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    trust_status: str = "current"
    privacy_class: str = "private"
    extraction_status: str = "pending"
    error: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class SourceChunk:
    id: str
    source_id: str
    chunk_index: int
    text: str
    start_offset: int
    end_offset: int
    token_estimate: int
    content_hash: str
    embedding_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
