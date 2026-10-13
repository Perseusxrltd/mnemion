"""Bounded, verbatim passages with offsets in the original Unicode text."""

from __future__ import annotations

import re
from collections import Counter, deque

_WORDS = re.compile(r"\w+", re.UNICODE)
MAX_PASSAGE = 4000


def passage_span(
    text: str, query: str, preferred: tuple[int, int] | None = None
) -> tuple[int, int]:
    """Prefer local query coverage, using the embedding span when words do not match.

    This selects a display passage, not a relevance score or proof of an answer.
    Token offsets come from the original text: Unicode case folding may change
    a word's length, so positions in a folded copy must never become citations.
    Only matches inside one display window are retained during the scan.
    """
    valid_preferred = preferred is not None and 0 <= preferred[0] < preferred[1] <= len(text)
    width = min(MAX_PASSAGE, preferred[1] - preferred[0]) if valid_preferred else MAX_PASSAGE
    if len(text) <= width:
        return 0, len(text)
    terms: set[str] = set()
    for word in _WORDS.finditer(query):
        terms.add(word.group().casefold())
        if len(terms) == 64:
            break
    matches: deque[tuple[int, int, str]] = deque()
    counts: Counter[str] = Counter()
    support = 0
    best, best_score = None, None
    preferred_center = sum(preferred) / 2 if valid_preferred else 0
    for word in _WORDS.finditer(text):
        if word.end() - word.start() > width:
            continue
        term = word.group().casefold()
        if term not in terms:
            continue
        matches.append((word.start(), word.end(), term))
        if counts[term] < 2:
            support += 1
        counts[term] += 1
        while word.end() - matches[0][0] > width:
            _, _, old = matches.popleft()
            if counts[old] <= 2:
                support -= 1
            counts[old] -= 1
            if not counts[old]:
                del counts[old]
        first, last = matches[0][0], word.end()
        score = (
            len(counts),
            support,
            -(last - first),
            -abs((first + last) / 2 - preferred_center),
        )
        if best_score is None or score > best_score:
            best, best_score = (first, last), score
    if best:
        first, last = best
        start = min(max(0, first - min(300, width // 4), last - width), len(text) - width)
        return start, start + width
    if valid_preferred:
        return preferred[0], preferred[0] + width
    return 0, MAX_PASSAGE


def evidence_passage(evidence: dict, query: str, content: str, span: tuple[int, int]) -> None:
    """Narrow only the cited source span; derived memory and source can differ."""
    excerpt = evidence["excerpt"]
    start, end = span if excerpt == content else passage_span(excerpt, query)
    origin = evidence["start"]
    evidence.update(
        excerpt=excerpt[start:end],
        start=origin + start,
        end=origin + end,
        excerpt_truncated=start != 0 or end != len(excerpt),
    )
