"""Owned Markdown views; journal records remain the source of replay and denials."""

import hashlib
import json
import posixpath
import re
from urllib.parse import quote
from uuid import UUID

from .format import JournalError, MAX_LINE_BYTES

NOTES_SUFFIX = "-mnemion-notes"
MARKER = "mnemion_journal_note: 1"
STATES = {"active", "pending", "forgotten", "quarantined"}


def notes_prefix(destination):
    # Outside the append-only journal tree, so 4.15 publishers still accept
    # intact archive moves when a newer librarian refreshes these derived views.
    return destination.prefix + NOTES_SUFFIX


def note_path(destination, memory_id):
    return f"{notes_prefix(destination)}/{memory_id}.md"


def note_candidate(path, text):
    if re.search(r"(?m)^mnemion_journal_note\s*:", text[:8192]):
        return True
    # A damaged/edited header in the reserved folder must not turn a derived
    # copy into independent memory, even with include_generated enabled.
    parts = path.replace("\\", "/").split("/")
    if len(parts) < 2 or not parts[-2].endswith(NOTES_SUFFIX):
        return False
    try:
        return parts[-1] == f"{UUID(parts[-1].removesuffix('.md'))}.md"
    except ValueError:
        return False


def render_note(entry, destination, *, state="active", source=None):
    if state not in STATES:
        raise ValueError("Unknown generated journal note state")
    title = (entry.subject or "Saved memory") if state == "active" else "Memory " + state
    heading = re.sub(r"([\\`*_{}\[\]<>#+.!|])", r"\\\1", " ".join(title.split()))
    if state == "active":
        body = f"# {heading}\n\n{entry.text}\n"
        if source:
            relative = posixpath.relpath(source, notes_prefix(destination))
            body += f"\n[Original journal record]({quote(relative, safe='/')})\n"
    else:
        body = f"# {heading}\n\nThis generated view contains no memory text.\n"
        if state == "pending":
            body += "The journal changed. Run Organize and archive to refresh this view.\n"
    payload = body.encode("utf-8")
    fields = {
        "origin": entry.origin,
        "entry_id": str(entry.id),
        "version": entry.version,
        "state": state,
        "recorded_at": entry.ts.isoformat(),
        "aliases": [title] if state == "active" else [],
        "tags": ["mnemion/journal", "mnemion/" + entry.kind] if state == "active" else [],
        "content_sha256": hashlib.sha256(payload).hexdigest(),
    }
    header = "---\nmnemion_managed: true\n" + MARKER + "\n"
    header += "".join(
        f"{key}: {json.dumps(value, ensure_ascii=False)}\n" for key, value in fields.items()
    )
    result = header.encode("utf-8") + b"---\n" + payload
    if len(result) > MAX_LINE_BYTES + 8192:
        raise JournalError("journal_note_too_large")
    return result


def validate_note(data, destination, memory_id, *, allow_content_changes=False):
    """Refuse to replace unrelated files or silently discard edits to a view."""
    try:
        if not data.startswith(b"---\n") or len(data) > MAX_LINE_BYTES + 8192:
            raise ValueError
        header, payload = data[4:].split(b"---\n", 1)
        if len(header) > 8192:
            raise ValueError
        values = {}
        for line in header.decode("utf-8").splitlines():
            key, value = line.split(": ", 1)
            if key in values:
                raise ValueError
            values[key] = json.loads(value)
        if (
            values.get("mnemion_managed") is not True
            or type(values.get("mnemion_journal_note")) is not int
            or values["mnemion_journal_note"] != 1
            or values.get("origin") != f"{destination.tenant_id}:{destination.space_id}:{memory_id}"
            or values.get("state") not in STATES
            or not allow_content_changes
            and values.get("content_sha256") != hashlib.sha256(payload).hexdigest()
        ):
            raise ValueError
        UUID(values["entry_id"])
        if type(values.get("version")) is not int or values["version"] < 1:
            raise ValueError
        return values
    except (ValueError, KeyError, TypeError, AttributeError, UnicodeError):
        raise JournalError("journal_note_conflict") from None


def invalidated_notes(journal, head, entries):
    """Clear existing views in the same commit as newly published changes."""
    latest = {}
    for entry in entries:
        previous = latest.get(entry.memory_id)
        if previous is None or entry.version > previous.version:
            latest[entry.memory_id] = entry
    updates = []
    for entry in latest.values():
        path = note_path(journal.destination, entry.memory_id)
        data = journal._blob(head, path)
        if data is None:
            continue
        # Source changes invalidate the view even if someone edited its body.
        # Their prior version remains in Git; view edits cannot veto a denial.
        validate_note(data, journal.destination, entry.memory_id, allow_content_changes=True)
        state = {"forget": "forgotten", "quarantine": "quarantined"}.get(entry.action, "pending")
        note = render_note(entry, journal.destination, state=state)
        if note != data:
            updates.append(journal._update(path, note))
    return updates
