"""Lightweight privacy helpers for source records."""

from __future__ import annotations

VALID_PRIVACY_CLASSES = {"private", "internal", "public", "sensitive"}


def normalize_privacy_class(value: str | None) -> str:
    normalized = (value or "private").strip().lower()
    if normalized not in VALID_PRIVACY_CLASSES:
        raise ValueError(
            "privacy_class must be one of: " + ", ".join(sorted(VALID_PRIVACY_CLASSES))
        )
    return normalized
