"""Reduce prompt-contaminated search text to the actual query intent."""

from __future__ import annotations

import re

MAX_QUERY_LENGTH = 250
SAFE_QUERY_LENGTH = 200
MIN_QUERY_LENGTH = 10

_EXPLICIT_QUERY_PATTERNS = [
    re.compile(r"\bquery\s*:\s*(.+?)(?:\s+(?:return|respond|cite|use|do not)\b|$)", re.I | re.S),
    re.compile(r"\bsearch(?:\s+for)?\s*:\s*(.+?)(?:\s+(?:return|respond|cite|use|do not)\b|$)", re.I | re.S),
    re.compile(r"\bfind\s*:\s*(.+?)(?:\s+(?:return|respond|cite|use|do not)\b|$)", re.I | re.S),
]


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" \t\n\r\"'")


def _result(raw: str, clean: str, was_sanitized: bool, method: str) -> dict:
    return {
        "clean_query": clean,
        "was_sanitized": was_sanitized,
        "original_length": len(raw),
        "clean_length": len(clean),
        "method": method,
    }


def _extract_explicit(raw: str) -> str | None:
    for pattern in _EXPLICIT_QUERY_PATTERNS:
        match = pattern.search(raw)
        if not match:
            continue
        candidate = _clean(match.group(1))
        if candidate.endswith(".") and "?" not in candidate:
            candidate = candidate[:-1]
        if len(candidate) >= MIN_QUERY_LENGTH:
            return candidate
    return None


def _extract_question(raw: str) -> str | None:
    sentences = re.split(r"(?<=[.!?])\s+", raw)
    questions = [_clean(s) for s in sentences if "?" in s and len(_clean(s)) >= MIN_QUERY_LENGTH]
    if not questions:
        return None
    return questions[-1]


def sanitize_query(raw_query: str) -> dict:
    """Return a safe search query plus metadata about any shortening performed."""
    raw = _clean(raw_query or "")
    if len(raw) <= SAFE_QUERY_LENGTH:
        return _result(raw_query or "", raw, False, "passthrough")

    explicit = _extract_explicit(raw)
    if explicit:
        return _result(raw_query, explicit[:MAX_QUERY_LENGTH], True, "explicit_query")

    question = _extract_question(raw)
    if question:
        return _result(raw_query, question[:MAX_QUERY_LENGTH], True, "question")

    sentences = [_clean(s) for s in re.split(r"(?<=[.!?])\s+", raw) if _clean(s)]
    if sentences:
        tail = sentences[-1]
        if len(tail) >= MIN_QUERY_LENGTH:
            return _result(raw_query, tail[:MAX_QUERY_LENGTH], True, "tail_sentence")

    return _result(raw_query, raw[-MAX_QUERY_LENGTH:], True, "tail_truncate")
