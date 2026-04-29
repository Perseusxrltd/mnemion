"""Query sanitizer for MCP search input."""

import logging
import re

logger = logging.getLogger("mnemion_mcp")

MAX_QUERY_LENGTH = 250
SAFE_QUERY_LENGTH = 200
MIN_QUERY_LENGTH = 10
QUOTE_CHARS = {"'", '"'}

_SENTENCE_SPLIT = re.compile(r"[.!?。！？\n]+")
_QUESTION_MARK = re.compile(r'[?？]\s*["\']?\s*$')


def sanitize_query(raw_query: str) -> dict:
    if not raw_query or not raw_query.strip():
        return {
            "clean_query": raw_query or "",
            "was_sanitized": False,
            "original_length": len(raw_query) if raw_query else 0,
            "clean_length": len(raw_query) if raw_query else 0,
            "method": "passthrough",
        }

    raw_query = raw_query.strip()
    original_length = len(raw_query)

    def _strip_wrapping_quotes(candidate: str) -> str:
        candidate = candidate.strip()
        while (
            len(candidate) >= 2 and candidate[:1] in QUOTE_CHARS and candidate[:1] == candidate[-1:]
        ):
            candidate = candidate[1:-1].strip()
        if candidate[:1] in QUOTE_CHARS:
            candidate = candidate[1:].strip()
        if candidate[-1:] in QUOTE_CHARS:
            candidate = candidate[:-1].strip()
        return candidate

    def _trim_candidate(candidate: str) -> str:
        candidate = _strip_wrapping_quotes(candidate)
        if len(candidate) <= MAX_QUERY_LENGTH:
            return candidate
        fragments = [
            _strip_wrapping_quotes(f) for f in _SENTENCE_SPLIT.split(candidate) if f.strip()
        ]
        for fragment in reversed(fragments):
            if MIN_QUERY_LENGTH <= len(fragment) <= MAX_QUERY_LENGTH:
                return fragment
        return candidate[-MAX_QUERY_LENGTH:].strip()

    if original_length <= SAFE_QUERY_LENGTH:
        return {
            "clean_query": raw_query,
            "was_sanitized": False,
            "original_length": original_length,
            "clean_length": original_length,
            "method": "passthrough",
        }

    segments = [seg.strip() for seg in raw_query.split("\n") if seg.strip()]
    for segment in reversed(segments):
        if _QUESTION_MARK.search(segment):
            candidate = _trim_candidate(segment)
            if len(candidate) >= MIN_QUERY_LENGTH:
                logger.warning(
                    "Query sanitized: %d -> %d chars (method=question_extraction)",
                    original_length,
                    len(candidate),
                )
                return {
                    "clean_query": candidate,
                    "was_sanitized": True,
                    "original_length": original_length,
                    "clean_length": len(candidate),
                    "method": "question_extraction",
                }

    for segment in reversed(segments):
        candidate = _trim_candidate(segment)
        if len(candidate) >= MIN_QUERY_LENGTH:
            logger.warning(
                "Query sanitized: %d -> %d chars (method=tail_sentence)",
                original_length,
                len(candidate),
            )
            return {
                "clean_query": candidate,
                "was_sanitized": True,
                "original_length": original_length,
                "clean_length": len(candidate),
                "method": "tail_sentence",
            }

    candidate = raw_query[-MAX_QUERY_LENGTH:].strip()
    return {
        "clean_query": candidate,
        "was_sanitized": True,
        "original_length": original_length,
        "clean_length": len(candidate),
        "method": "tail_truncation",
    }
