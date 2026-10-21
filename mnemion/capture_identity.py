"""Stable, scoped identities shared by local capture and service ingestion."""

import hashlib
import json
from uuid import UUID


def canonical_capture_json(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def capture_event_id(source_id, producer_scope: str, item_dict: dict) -> str:
    """Transport retries and devices share identity; grants never change evidence."""
    return hashlib.sha256(
        canonical_capture_json(
            ["mnemion-capture-event-v1", str(UUID(str(source_id))), producer_scope, item_dict]
        )
    ).hexdigest()


def capture_lineage_id(producer_scope: str, item_dict: dict) -> str:
    """One captured fragment owns all its parts, projections and revisions.

    Explicit forgetting removes this entire fragment family, which can include
    adjacent messages. A new producer generation is not a semantic identity.
    """
    metadata = item_dict["memory"]["metadata"]
    return hashlib.sha256(
        canonical_capture_json(
            [
                "mnemion-capture-family-v1",
                producer_scope,
                metadata["source_generation"],
                metadata["source_byte_start"],
            ]
        )
    ).hexdigest()
