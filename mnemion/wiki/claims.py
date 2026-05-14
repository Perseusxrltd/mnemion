"""Claim extraction and stable claim identifiers."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from ..sources.chunking import sha256_hex


def claim_id(page_id: str, claim_text: str, evidence_id: str = "") -> str:
    raw = f"{page_id}:{claim_text}:{evidence_id}".encode("utf-8")
    return "claim_" + hashlib.sha1(raw).hexdigest()[:12]


def sentence_claims(
    page_id: str,
    source_id: str,
    chunk_id: str,
    text: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    sentences = [
        part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if len(part.strip()) >= 20
    ]
    claims = []
    now = datetime.now(timezone.utc).isoformat()
    for sentence in sentences[:limit]:
        cid = claim_id(page_id, sentence, chunk_id)
        start = text.find(sentence)
        claims.append(
            {
                "id": cid,
                "claim_text": sentence,
                "source_id": source_id,
                "source_chunk_id": chunk_id,
                "evidence_span_start": start if start >= 0 else None,
                "evidence_span_end": start + len(sentence) if start >= 0 else None,
                "confidence": 0.9,
                "trust_status": "current",
                "generated_at": now,
                "content_hash": sha256_hex(sentence),
            }
        )
    return claims
