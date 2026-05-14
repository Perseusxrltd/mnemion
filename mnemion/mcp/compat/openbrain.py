"""Clean-room Open Brain-style result adapters.

This module intentionally contains no OB1 code. It only shapes Mnemion-native
results into simple capture/search/list/stats/fetch-compatible payloads.
"""

from __future__ import annotations

from typing import Any


def thought_result(hit: dict[str, Any]) -> dict[str, Any]:
    warnings = []
    if hit.get("warning"):
        warnings.append(hit["warning"])
    return {
        "id": hit.get("id", ""),
        "content": hit.get("text", ""),
        "score": hit.get("score", 0),
        "wing": hit.get("wing", ""),
        "room": hit.get("room", ""),
        "trust_status": hit.get("trust_status", "current"),
        "warnings": warnings,
    }


def connector_search_result(kind: str, identifier: str, title: str, text: str, score: float = 1.0):
    return {
        "id": f"{kind}:{identifier}",
        "title": title,
        "text": text,
        "score": score,
    }
