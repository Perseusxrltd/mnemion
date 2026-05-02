"""Memory-injection and privacy-risk guardrails for stored drawers."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .trust_lifecycle import STATUS_QUARANTINED


@dataclass(frozen=True)
class RiskFinding:
    risk_type: str
    score: float
    reason: str


_INJECTION_PATTERNS = [
    r"ignore (all )?(previous|prior) instructions",
    r"disregard (the )?(system|developer|previous) instructions",
    r"always answer .* with",
    r"when the user asks .* reveal",
    r"leak (passwords?|secrets?|tokens?)",
]
_PRIVACY_PATTERNS = [
    r"\b\d{3}-\d{2}-\d{4}\b",
    r"\b(password|api[_ -]?key|secret|token)\b",
    r"\breveal\b.*\b(ssn|password|secret|private)\b",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_guard_findings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    drawer_id   TEXT NOT NULL,
    risk_type   TEXT NOT NULL,
    score       REAL NOT NULL,
    reason      TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_guard_drawer ON memory_guard_findings(drawer_id);
"""


def score_memory_risks(text: str) -> list[RiskFinding]:
    lower = text.lower()
    findings: list[RiskFinding] = []
    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, lower):
            findings.append(
                RiskFinding(
                    risk_type="instruction_injection",
                    score=0.9,
                    reason=f"matched pattern: {pattern}",
                )
            )
            break
    for pattern in _PRIVACY_PATTERNS:
        if re.search(pattern, lower):
            findings.append(
                RiskFinding(
                    risk_type="privacy_exfiltration",
                    score=0.85,
                    reason=f"matched pattern: {pattern}",
                )
            )
            break
    return findings


class MemoryGuard:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self):
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _record(self, drawer_id: str, findings: list[RiskFinding]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.executemany(
                """INSERT INTO memory_guard_findings
                   (drawer_id, risk_type, score, reason, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                [
                    (drawer_id, finding.risk_type, finding.score, finding.reason, now)
                    for finding in findings
                ],
            )
            conn.commit()

    def quarantine_drawer(self, drawer_id: str, trust, reason: str = "") -> dict[str, Any]:
        return trust.update_status(
            drawer_id,
            STATUS_QUARANTINED,
            confidence=0.0,
            reason=reason or "memory guard quarantine",
            changed_by="memory_guard",
        )

    def scan_collection(self, collection, trust=None, quarantine: bool = False) -> dict[str, int]:
        batch = collection.get(include=["documents", "metadatas"])
        flagged = 0
        scanned = 0
        for drawer_id, doc in zip(batch.get("ids") or [], batch.get("documents") or []):
            scanned += 1
            findings = score_memory_risks(doc)
            if not findings:
                continue
            flagged += 1
            self._record(drawer_id, findings)
            if quarantine and trust is not None:
                self.quarantine_drawer(drawer_id, trust=trust, reason=findings[0].reason)
        return {"scanned": scanned, "flagged": flagged, "quarantined": flagged if quarantine else 0}
