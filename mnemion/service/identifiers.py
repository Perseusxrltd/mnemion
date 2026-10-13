"""Bounded literal identifiers for retrieval, without interpreting query regexes."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

MAX_IDENTIFIERS = 8
MAX_IDENTIFIER_LENGTH = 256
IDENTIFIER_WEIGHT = 1
IDENTIFIER_LABEL_WEIGHT = 3
TOKENS = re.compile(r"[\w./\\-]+", re.UNICODE)
EXTENSION = re.compile(r"\.[a-zA-Z][a-zA-Z0-9]{1,11}$|\.[chr]$", re.IGNORECASE)


@dataclass(frozen=True)
class IdentifierQuery:
    terms: tuple[str, ...]
    patterns: tuple[str, ...]
    truncated: bool


def query_identifiers(query: str) -> IdentifierQuery:
    """Recognize alphanumeric IDs and filenames; numbers/prose keep normal recall."""
    normalized = unicodedata.normalize("NFC", query)
    # A separate positive-ID channel must not resurrect results explicitly
    # excluded by web-search syntax. Keep those queries on existing channels.
    if re.search(r"(?<!\S)-(?=\S)", normalized):
        return IdentifierQuery((), (), False)
    terms, patterns, seen = [], [], set()
    truncated = False
    for token in TOKENS.finditer(normalized):
        raw = token.group()
        value = raw.rstrip(".").replace("\\", "/")
        filename = bool(EXTENSION.search(value))
        identifier = any(character.isalpha() for character in value) and any(
            character.isdigit() for character in value
        )
        if len(value) < 3 or not (filename or identifier):
            continue
        if len(value) > MAX_IDENTIFIER_LENGTH:
            truncated = True
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        if len(terms) == MAX_IDENTIFIERS:
            truncated = True
            continue
        forms = dict.fromkeys((value, unicodedata.normalize("NFD", value)))
        literal = "(?:" + "|".join(re.escape(form).replace("/", r"[/\\]") for form in forms) + ")"
        # Underscores delimit IDs inside Git filenames. Alphanumeric suffixes
        # do not: TASK-73120 must never count as the complete ID TASK-7312.
        before = r"(?<![[:alnum:]_.-])" if filename else r"(?<![[:alnum:]])"
        after = r"(?![[:alnum:]_]|[.-][[:alnum:]_])" if filename else r"(?![[:alnum:]])"
        terms.append(value)
        patterns.append(before + literal + after)
    return IdentifierQuery(tuple(terms), tuple(patterns), truncated)


# One additional scoped query; no per-result model calls or regex supplied by
# the caller. Check short labels before the bounded memory body. A repeated ID
# counts once, so repetition cannot manufacture additional identifier coverage.
IDENTIFIER_CANDIDATES = r"""
 , identifier_matches AS MATERIALIZED (
SELECT e.memory_id, e.space_id, e.revision_id,
       matches.matched AS identifier_matches,
       matches.labelled AS identifier_label_matches
FROM eligible e JOIN mnemion.memory_revisions r
  ON r.tenant_id=mnemion.tenant() AND r.space_id=e.space_id AND r.id=e.revision_id
CROSS JOIN LATERAL (
    SELECT count(*) AS matched, count(*) FILTER (WHERE in_label) AS labelled
    FROM (
        SELECT pattern,
            coalesce(r.subject,'') ~* pattern
            OR coalesce(r.metadata->>'path','') ~* pattern AS in_label
        FROM unnest(%(identifier_patterns)s::text[]) AS identifiers(pattern)
    ) labelled
    WHERE CASE WHEN in_label THEN true ELSE r.content ~* pattern END
) matches
WHERE matches.matched > 0
), ranked_identifiers AS (
    SELECT *, row_number() OVER (
        ORDER BY identifier_matches DESC, identifier_label_matches DESC, memory_id
    ) AS identifier_rank,
    CASE WHEN identifier_label_matches>0 THEN row_number() OVER (
        ORDER BY (identifier_label_matches>0) DESC,
                 identifier_label_matches DESC, identifier_matches DESC, memory_id
    ) END AS identifier_label_rank
    FROM identifier_matches
)
SELECT * FROM ranked_identifiers
WHERE identifier_rank<=%(limit)s OR identifier_label_rank<=%(limit)s
ORDER BY identifier_rank
"""
