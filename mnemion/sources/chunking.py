"""Chunking helpers for immutable raw source text."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    text: str
    start_offset: int
    end_offset: int
    token_estimate: int
    content_hash: str


def sha256_hex(data: bytes | str) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def chunk_text(
    text: str,
    target_chars: int = 1800,
    overlap_chars: int = 200,
    min_chars: int = 300,
) -> list[TextChunk]:
    """Split text into overlapping chunks with stable offsets.

    Very small non-empty sources still produce one chunk; ``min_chars`` only
    suppresses tiny trailing fragments after larger chunks.
    """
    clean = text.strip()
    if not clean:
        return []

    if len(clean) <= target_chars:
        return [
            TextChunk(
                chunk_index=0,
                text=clean,
                start_offset=0,
                end_offset=len(clean),
                token_estimate=max(1, len(clean) // 4),
                content_hash=sha256_hex(clean),
            )
        ]

    chunks: list[TextChunk] = []
    start = 0
    chunk_index = 0
    while start < len(clean):
        end = min(start + target_chars, len(clean))
        if end < len(clean):
            para = clean.rfind("\n\n", start, end)
            line = clean.rfind("\n", start, end)
            sentence = max(clean.rfind(". ", start, end), clean.rfind("? ", start, end))
            for boundary in (para, line, sentence):
                if boundary > start + target_chars // 2:
                    end = boundary + (1 if boundary == sentence else 0)
                    break

        chunk = clean[start:end].strip()
        if chunk and (len(chunk) >= min_chars or not chunks):
            chunks.append(
                TextChunk(
                    chunk_index=chunk_index,
                    text=chunk,
                    start_offset=start,
                    end_offset=end,
                    token_estimate=max(1, len(chunk) // 4),
                    content_hash=sha256_hex(chunk),
                )
            )
            chunk_index += 1

        if end >= len(clean):
            break
        start = max(end - overlap_chars, start + 1)

    return chunks
