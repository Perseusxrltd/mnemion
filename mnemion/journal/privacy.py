"""Conservative pre-publication rules and an optional fail-closed local scanner."""

import json
import re

from .format import JournalEntry, JournalError
from .process import run

_SECRET = re.compile(
    r"\b(?:mnv_|mnm_bk_|mnm_)[A-Za-z0-9_-]{32,}\b"
    r"|-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"
    r"|\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"
    r"|\b(?:gh[pousr]_|github_pat_|sk-(?:proj-|ant-)?)[A-Za-z0-9_-]{20,}\b"
    r"|\bBearer\s+[A-Za-z0-9_.~-]{24,}"
    r"|\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}"
    r"|\b(?:https?|postgres(?:ql)?|mysql)://[^\s/:\"']+:[^\s/@\"']+@"
    r"|[\"']?(?:password|passwd|api[_ -]?key|access[_ -]?token|secret[_ -]?key)[\"']?"
    r"\s*[:=]\s*[\"']?[A-Za-z0-9/+_.=-]{16,}",
    re.IGNORECASE,
)
_EMAIL = re.compile(
    r"\b[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]*[A-Z0-9])?(?:\.[A-Z0-9-]+)+\b",
    re.IGNORECASE,
)
_SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
_PHONE = re.compile(r"(?<!\w)\+[1-9](?:[ ()-]*\d){8,14}(?!\d)")


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, str):
                yield key + "=" + item
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def scan(entry: JournalEntry, *, personal_data=True, scanner: tuple[str, ...] = ()):
    line = entry.line()
    # Inspect original strings as well as their JSON representation. Escaped
    # quotes/newlines in a pasted config must not evade assignment detection.
    text = "\n".join(_strings(entry.model_dump(mode="json")))
    if _SECRET.search(text):
        raise JournalError("journal_secret_detected")
    if personal_data and (_EMAIL.search(text) or _SSN.search(text) or _PHONE.search(text)):
        raise JournalError("journal_personal_data_detected")
    if scanner:
        code, result = run(list(scanner), input=line, timeout=5, maximum=8192)
        try:
            verdict = json.loads(result)
            allowed = code == 0 and isinstance(verdict, dict) and verdict.get("allow") is True
        except (ValueError, TypeError):
            allowed = False
        if not allowed:
            raise JournalError("journal_scanner_rejected")
