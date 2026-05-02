"""Memory-injection and privacy-risk guardrails for stored drawers."""

from __future__ import annotations

import re
import sqlite3
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from collections import Counter
from pathlib import Path
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


def _redact_text(text: str) -> str:
    text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED_SSN]", text)
    text = re.sub(
        r"(?i)\b(password|api[_ -]?key|secret|token)\b\s*[:=]\s*['\"]?[^\s,'\"]+",
        r"\1=[REDACTED]",
        text,
    )
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{12,}", r"\1[REDACTED]", text)
    return text


def _snippet_for_reason(text: str, reason: str, max_chars: int = 260) -> str:
    pattern = reason.removeprefix("matched pattern: ")
    match = None
    try:
        match = re.search(pattern, text.lower())
    except re.error:
        match = None
    if match:
        center = match.start()
        start = max(0, center - max_chars // 2)
    else:
        start = 0
    snippet = text[start : start + max_chars].replace("\r", " ").replace("\n", " ")
    return _redact_text(snippet).strip()


def _finding_rows(db_path: str) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_guard_findings'"
        ).fetchone()
        if not exists:
            return []
        return conn.execute(
            """SELECT drawer_id, risk_type, score, reason, MAX(created_at) AS created_at
               FROM memory_guard_findings
               GROUP BY drawer_id, risk_type, score, reason
               ORDER BY created_at DESC, drawer_id"""
        ).fetchall()
    finally:
        conn.close()


def generate_review_report(db_path: str, collection, output_dir: str) -> dict[str, Any]:
    """Write a report from existing memory-guard findings without rescanning or quarantining."""
    rows = _finding_rows(db_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "memory_guard_review.csv"
    md_path = output / "memory_guard_review.md"

    ids = [row["drawer_id"] for row in rows]
    metadata_by_id: dict[str, dict[str, Any]] = {}
    doc_by_id: dict[str, str] = {}
    for i in range(0, len(ids), 200):
        batch_ids = ids[i : i + 200]
        if not batch_ids:
            continue
        batch = collection.get(ids=batch_ids, include=["documents", "metadatas"])
        for drawer_id, doc, meta in zip(
            batch.get("ids") or [],
            batch.get("documents") or [],
            batch.get("metadatas") or [],
        ):
            metadata_by_id[drawer_id] = meta or {}
            doc_by_id[drawer_id] = doc or ""

    report_rows = []
    by_reason: Counter[str] = Counter()
    by_wing_room: Counter[tuple[str, str]] = Counter()
    for row in rows:
        drawer_id = row["drawer_id"]
        meta = metadata_by_id.get(drawer_id, {})
        wing = str(meta.get("wing") or "")
        room = str(meta.get("room") or "")
        source = str(meta.get("source_file") or meta.get("source") or "")
        reason = str(row["reason"])
        by_reason[reason] += 1
        by_wing_room[(wing, room)] += 1
        report_rows.append(
            {
                "drawer_id": drawer_id,
                "risk_type": row["risk_type"],
                "score": row["score"],
                "reason": reason,
                "wing": wing,
                "room": room,
                "source": source,
                "created_at": row["created_at"],
                "redacted_snippet": _snippet_for_reason(doc_by_id.get(drawer_id, ""), reason),
            }
        )

    fieldnames = [
        "drawer_id",
        "risk_type",
        "score",
        "reason",
        "wing",
        "room",
        "source",
        "created_at",
        "redacted_snippet",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report_rows)

    lines = [
        "# Mnemion Memory Guard Review",
        "",
        f"- Findings: {len(report_rows)}",
        f"- Distinct drawers: {len({row['drawer_id'] for row in report_rows})}",
        "- Action taken: report only; no quarantine.",
        "",
        "## Reasons",
        "",
    ]
    for reason, count in by_reason.most_common():
        lines.append(f"- `{reason}`: {count}")
    lines.extend(["", "## Top Wings And Rooms", ""])
    for (wing, room), count in by_wing_room.most_common(20):
        lines.append(f"- `{wing or '(blank)'}/{room or '(blank)'}`: {count}")
    lines.extend(["", "## Sample Findings", ""])
    for row in report_rows[:50]:
        lines.append(
            f"- `{row['drawer_id']}` `{row['wing']}/{row['room']}` "
            f"`{row['reason']}`: {row['redacted_snippet']}"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "findings": len(report_rows),
        "distinct_drawers": len({row["drawer_id"] for row in report_rows}),
        "markdown_path": str(md_path),
        "csv_path": str(csv_path),
        "by_reason": dict(by_reason),
        "top_wing_room": [
            {"wing": wing, "room": room, "count": count}
            for (wing, room), count in by_wing_room.most_common(20)
        ],
    }


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
