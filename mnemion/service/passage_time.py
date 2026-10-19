"""Bounded text-change chronology, separate from the truth of a source's claims."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re
import unicodedata

MAX_SEGMENTS = 2048
_DATE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?)(Z|[+-]\d{2}:\d{2})?)?(?!\d)"
)
_NUMBERED = re.compile(r"(?<!\S)\(\d{1,3}\)\s+")
_WORDS = re.compile(r"[^\W_]+", re.UNICODE)
_STOP = frozenset(
    "a an and are as at be been by can could did do does for from had has have how i if in is it "
    "me my of on or our should that the their them there these they this those to was we were "
    "what when where which who why will with would you your "
    "au aux avec ce ces cet cette dans de des du elle en est et eux il ils je la le les leur "
    "lui ma mais mes mon ne nos notre nous on ou par pas pour qu que quel quelle quels quelles "
    "qui sa se ses son sont sous sur ta te tes ton tu un une vos votre vous y".split()
)


@dataclass(frozen=True)
class Passage:
    start: int
    end: int
    declared_at: datetime | None = None
    basis: str = "recorded_at"


def timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        date = datetime.fromisoformat(value)
        return date.astimezone(timezone.utc) if date.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def source_time(metadata: dict, recorded_at: datetime) -> tuple[datetime, str]:
    date = timestamp(metadata.get("source_modified_at"))
    if date is not None and date <= recorded_at:
        return date, "source_modified_at"
    return recorded_at, "recorded_at"


def _leading_date(line: str, ceiling: datetime) -> tuple[datetime | None, str]:
    value = re.sub(r"^(?:#{1,6}\s+|[-*]\s+|\|\s*)", "", line.strip()).lstrip("[")
    match = _DATE.match(value)
    if not match:
        return None, "recorded_at"
    date, clock, zone = match.groups()
    # A time without an offset has unknown timezone. Keep only its calendar
    # day; do not invent a precise UTC instant or interpret an inline deadline.
    precise = bool(clock and zone)
    parsed = timestamp(date + "T" + clock + zone) if precise else timestamp(date + "T00:00:00Z")
    if parsed is None or parsed > ceiling:
        return None, "recorded_at"
    return parsed, "source_timestamp" if precise else "source_date"


def passages(text: str, ceiling: datetime) -> list[Passage]:
    """Use exact Unicode spans; numbered decisions are independent of their row."""
    result = []
    offset = 0
    section_date, section_basis, section_level = None, "recorded_at", 0
    fence = None
    for line in text.splitlines(keepends=True):
        raw = line.strip()
        marker = re.match(r"^(`{3,}|~{3,})", raw)
        inside_code = fence is not None
        if marker:
            symbol = marker[1][0]
            if fence is None:
                fence = (symbol, len(marker[1]))
            elif symbol == fence[0] and len(marker[1]) >= fence[1]:
                fence = None
            inside_code = True
        heading = re.match(r"^(#{1,6})\s+", raw) if not inside_code else None
        date, basis = (None, "recorded_at") if inside_code else _leading_date(line, ceiling)
        if heading:
            level = len(heading[1])
            if date is not None:
                section_date, section_basis, section_level = date, basis, level
            elif section_level and level <= section_level:
                section_date, section_basis, section_level = None, "recorded_at", 0
        if date is None:
            date, basis = section_date, section_basis
        cuts = [0]
        if not inside_code:
            cuts.extend(match.start() for match in _NUMBERED.finditer(line) if match.start())
        cuts.append(len(line))
        for begin, finish in zip(cuts, cuts[1:]):
            # Bound long prose lines without altering or dropping source text.
            for start in range(begin, finish, 2000):
                end = min(start + 2000, finish)
                while start < end and line[start].isspace():
                    start += 1
                while end > start and line[end - 1].isspace():
                    end -= 1
                if start < end:
                    result.append(Passage(offset + start, offset + end, date, basis))
                if len(result) > MAX_SEGMENTS:
                    return [Passage(0, len(text))]
        offset += len(line)
    return result or [Passage(0, len(text))]


def _fingerprint(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode()).hexdigest()


def _stored(value: object, length: int) -> list[tuple[int, int, datetime, str]]:
    if (
        not isinstance(value, dict)
        or type(value.get("version")) is not int
        or value["version"] != 1
    ):
        return []
    rows = value.get("segments")
    if not isinstance(rows, list) or len(rows) > MAX_SEGMENTS:
        return []
    result = []
    previous = 0
    for row in rows:
        if (
            not isinstance(row, list)
            or len(row) != 4
            or type(row[0]) is not int
            or type(row[1]) is not int
            or not previous <= row[0] < row[1] <= length
            or not isinstance(row[3], str)
            or row[3]
            not in {"recorded_at", "source_modified_at", "source_timestamp", "source_date"}
        ):
            return []
        date = timestamp(row[2])
        if date is None:
            return []
        result.append((row[0], row[1], date, row[3]))
        previous = row[1]
    return result


def times(
    text: str, value: object, metadata: dict, recorded_at: datetime
) -> list[tuple[Passage, datetime, str]]:
    stored = _stored(value, len(text))
    fallback, fallback_basis = source_time(metadata, recorded_at)
    result = []
    cursor = 0
    for part in passages(text, recorded_at):
        while cursor < len(stored) and stored[cursor][1] <= part.start:
            cursor += 1
        matches = []
        index = cursor
        while index < len(stored) and stored[index][0] < part.end:
            start, end, date, basis = stored[index]
            if start <= part.start and end >= part.end and date <= recorded_at:
                matches.append((date, basis))
            index += 1
        date, basis = (
            max(matches)
            if matches
            else (
                (part.declared_at, part.basis) if part.declared_at else (fallback, fallback_basis)
            )
        )
        result.append((part, date, basis))
    return result


def capture(text: str, metadata: dict, recorded_at: datetime, previous: dict | None = None) -> dict:
    """Retain an unchanged passage's earlier observation across cosmetic edits."""
    prior = {}
    declared_before = set()
    if previous and previous.get("content") is not None:
        for part, date, basis in times(
            previous["content"],
            previous.get("passage_times"),
            previous["metadata"],
            previous["recorded_at"],
        ):
            if part.declared_at is not None:
                declared_before.add(part.declared_at)
            digest = _fingerprint(previous["content"][part.start : part.end])
            # Duplicate text keeps its earliest observed age, not arbitrary
            # order or a newly appended duplicate's timestamp.
            if digest not in prior or date < prior[digest][0]:
                prior[digest] = date, basis
    output = []
    for part, date, basis in times(text, None, metadata, recorded_at):
        old = prior.get(_fingerprint(text[part.start : part.end]))
        if old and old[0] <= date:
            date, basis = old
        elif previous and part.declared_at in declared_before:
            # An old heading does not make a newly changed statement old.
            # New explicit date labels are retained; a changed statement under
            # an already-known label gets its observed update time.
            date, basis = source_time(metadata, recorded_at)
        row = [part.start, part.end, date.isoformat(), basis]
        if output and output[-1][2:] == row[2:]:
            output[-1][1] = part.end
        else:
            output.append(row)
    return {"version": 1, "segments": output}


def query_terms(query: str) -> set[str]:
    terms = set()
    for word in _WORDS.finditer(unicodedata.normalize("NFC", query).casefold()):
        if word[0] not in _STOP:
            terms.add(word[0])
        if len(terms) == 64:
            break
    return terms


def select(
    text: str,
    value: object,
    metadata: dict,
    recorded_at: datetime,
    query: str,
    *,
    recent: bool,
    preferred: tuple[int, int] | None = None,
) -> dict:
    terms = query_terms(query)
    best = None
    fallback, fallback_basis = source_time(metadata, recorded_at)
    observed = times(text, value, metadata, recorded_at)
    for part, date, basis in observed:
        matched = terms & set(
            _WORDS.findall(unicodedata.normalize("NFC", text[part.start : part.end]).casefold())
        )
        proximity = -abs((part.start + part.end) / 2 - sum(preferred) / 2) if preferred else 0
        score = (
            len(matched),
            date if recent else datetime.min.replace(tzinfo=timezone.utc),
            proximity,
            -(part.end - part.start),
        )
        if best is None or score > best[0]:
            best = score, part, date, basis, len(matched)
    _, part, date, basis, matched = best
    # With no query support, an embedding's actual span can determine age.
    # Do not manufacture a textual match for semantic-only evidence.
    if not matched:
        intersecting = [
            (stamp, kind)
            for block, stamp, kind in observed
            if preferred and block.start < preferred[1] and block.end > preferred[0]
        ]
        date, basis = max(intersecting) if intersecting else (fallback, fallback_basis)
        part = (
            Passage(*preferred)
            if preferred and 0 <= preferred[0] < preferred[1] <= len(text)
            else Passage(0, len(text))
        )
    return {
        "at": date,
        "basis": basis,
        "start": part.start,
        "end": part.end,
        "matched_terms": matched,
        "requested_terms": len(terms),
        "tracked": bool(_stored(value, len(text))),
        "limited": len(observed) == 1 and observed[0][0].end - observed[0][0].start > 2000,
    }
