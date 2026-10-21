"""Bounded private scan observations, separate from settings and raw capture.

Only a scan's owner/token can finish it. Lost replies are never replayed here.
An unfinished record observed by a new Studio session is interrupted, not good
evidence of either a completed scan or complete coverage of a provider's history.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, ValidationError, field_validator, model_validator

from . import local_state
from .connectors.capture_scheduling import BACKFILL_POLL_SECONDS, BACKFILL_REASONS, backfill_pending
from .desktop_capture import CAPTURE_REASONS, CaptureReport
from .service.models import Command

Reason = Literal[
    "history_reset",
    "partial",
    "interrupted",
    "source_cancelled",
    "source_timeout",
    "source_unavailable",
    "source_helper_unavailable",
    "source_invalid_response",
    "source_identity_mismatch",
    "source_connection_unavailable",
    "source_scope_ambiguous",
    "source_scope_mismatch",
    "source_conversation_identity_required",
    "source_conversation_copy_unverified",
    "source_conversation_incomplete_copy",
    "source_settings_changed",
    "source_memory_limit",
    "source_provider_credentials",
    "provider_access_lost",
    "slack_access_lost",
    "slack_workspace_mismatch",
    "provider_rate_limited",
    "provider_unavailable",
    "invalid_drive_identity",
    "private_location",
    "unsafe_location",
    "damaged_state",
    "storage_locked",
    "source_credentials_unavailable",
    *sorted(CAPTURE_REASONS),
]


def observation_time(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value
    ):
        raise ValueError("Use a UTC observation timestamp")
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Report(Command):
    completed: bool = Field(strict=True)
    timestamp: str = Field(max_length=32)
    duration_seconds: float = Field(ge=0, le=86400, allow_inf_nan=False, strict=True)
    changed: int = Field(ge=0, le=10**12, strict=True)
    removed: int = Field(ge=0, le=10**12, strict=True)
    unchanged: int = Field(ge=0, le=10**12, strict=True)
    conflicts: int = Field(ge=0, le=10**12, strict=True)
    remote_sync_available: bool = Field(strict=True)
    capture: CaptureReport | None = None

    _timestamp = field_validator("timestamp")(observation_time)


def backfilling(report: Report | None) -> bool:
    return backfill_pending(report.model_dump() if report is not None else None)


class Failure(Command):
    observed_at: str = Field(max_length=32)
    reason_code: Reason

    _timestamp = field_validator("observed_at")(observation_time)

    @field_validator("reason_code")
    @classmethod
    def failure_reason(cls, value):
        if value in BACKFILL_REASONS:
            raise ValueError("Backfill progress is not a failed scan")
        return value


class Record(Command):
    id: UUID
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    owner: UUID
    run: UUID
    phase: Literal["waiting", "scanning", "backfill", "complete", "attention"]
    started_at: str | None = Field(default=None, max_length=32)
    finished_at: str | None = Field(default=None, max_length=32)
    next_scan_at: str | None = Field(default=None, max_length=32)
    reason_code: Reason | None = None
    report: Report | None = None
    last_success_report: Report | None = None
    last_failure: Failure | None = None

    @field_validator("started_at", "finished_at", "next_scan_at")
    @classmethod
    def times(cls, value):
        return observation_time(value) if value is not None else None

    @model_validator(mode="after")
    def consistent(self):
        if self.phase == "waiting":
            if (
                self.started_at is not None
                or self.finished_at is not None
                or self.next_scan_at is None
                or self.reason_code != "history_reset"
                or self.report is not None
                or self.last_success_report is not None
                or self.last_failure is not None
            ):
                raise ValueError("A history reset cannot invent scan observations")
            return self
        if self.started_at is None or self.reason_code == "history_reset":
            raise ValueError("A scan observation needs its actual start")
        if self.phase == "scanning":
            if self.finished_at is not None or self.next_scan_at is not None or self.reason_code:
                raise ValueError("An unfinished scan has no completion observation")
        elif self.finished_at is None or self.next_scan_at is None:
            raise ValueError("A finished observation needs its timestamps")
        if self.phase == "complete" and (
            self.report is None
            or not self.report.completed
            or self.reason_code is not None
            or self.last_success_report != self.report
        ):
            raise ValueError("A completed observation needs a successful report")
        if self.phase == "attention" and self.reason_code is None:
            raise ValueError("Attention needs a known reason")
        if self.phase == "backfill" or self.reason_code in BACKFILL_REASONS:
            if (
                self.phase != "backfill"
                or not backfilling(self.report)
                or self.reason_code != self.report.capture.reason_code
            ):
                raise ValueError("Backfill progress needs its observed capture report")
        if self.reason_code == "partial" and (self.report is None or self.report.completed):
            raise ValueError("A partial observation needs its incomplete report")
        if self.last_success_report is not None and not self.last_success_report.completed:
            raise ValueError("A partial scan is not a successful scan")
        return self


class State(Command):
    format: Literal[1] = 1
    records: list[Record] = Field(max_length=16)

    @model_validator(mode="after")
    def distinct(self):
        if len({record.id for record in self.records}) != len(self.records):
            raise ValueError("Duplicate source observation")
        return self


class Request(Command):
    operation: Literal["status", "status_begin", "status_finish", "status_repair"]
    owner: UUID
    expected_revision: str | None = None
    id: UUID | None = None
    run: UUID | None = None
    report: Report | None = None
    reason_code: Reason | None = None
    repair_token: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    confirm: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def fields(self):
        expected = {
            "status": {"operation", "owner", "expected_revision"},
            "status_begin": {"operation", "owner", "expected_revision", "id", "run"},
            "status_finish": {"operation", "owner", "id", "run"},
            "status_repair": {
                "operation",
                "owner",
                "expected_revision",
                "id",
                "repair_token",
                "confirm",
            },
        }[self.operation]
        optional = {"report", "reason_code"} if self.operation == "status_finish" else set()
        if not expected <= self.model_fields_set <= expected | optional or any(
            getattr(self, field) is None for field in expected
        ):
            raise ValueError("Choose a supported private source-status operation")
        if self.operation == "status_finish":
            if self.report is None and self.reason_code is None:
                raise ValueError("Finish with an observed report or a known failure")
            if self.report is not None and self.reason_code is not None:
                raise ValueError("Do not combine a report with a separate failure")
            if self.reason_code == "history_reset":
                raise ValueError("A scan cannot reset observation history")
            if self.reason_code in BACKFILL_REASONS:
                raise ValueError("Backfill progress needs its observed capture report")
        if self.operation == "status_repair" and self.confirm is not True:
            raise ValueError("Confirm repair of this computer's scan observations")
        return self


def settings(source) -> dict:
    """A pause changes scheduling, not the meaning of retained observations."""
    return source.model_dump(mode="json", exclude={"enabled", "status_epoch"}, exclude_none=True)


def fingerprint(source) -> str:
    value = {
        **settings(source),
        "status_epoch": str(source.status_epoch) if source.status_epoch else None,
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _load(root: Path) -> State:
    def distinct_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate observation field")
            value[key] = item
        return value

    try:
        value = json.loads(
            local_state.read_bytes(root / "source-status.json"), object_pairs_hook=distinct_object
        )
        return State.model_validate(value)
    except FileNotFoundError:
        return State(records=[])
    except (ValidationError, ValueError, RecursionError, local_state.LocalSetupError):
        raise local_state.LocalSetupError(
            "source_status_invalid",
            "Saved scan observations could not be read. The existing file has been retained.",
        ) from None


def _view(record: Record, owner: UUID) -> dict:
    value = record.model_dump(
        mode="json", exclude={"id", "fingerprint", "owner", "run"}, exclude_none=True
    )
    # Capture coverage uses explicit nulls for unknown times and unfinished index
    # observations. Recursive exclude_none strips that wire contract, so the
    # desktop rejects saved reports and cannot start the next scan.
    for field in ("report", "last_success_report"):
        report = getattr(record, field)
        if report is not None and report.capture is not None:
            value[field]["capture"] = report.capture.model_dump(mode="json")
    value["durability"] = "saved"
    if record.phase == "scanning" and record.owner != owner:
        value.update(phase="attention", reason_code="interrupted")
    return value


def _repair_token(content: bytes, revision: str) -> str:
    return hashlib.sha256(
        b"mnemion-source-status-repair-v1\n" + revision.encode() + b"\n" + content
    ).hexdigest()


def _damaged_view(root: Path, current) -> dict:
    # Only an ordinary, bounded private file can be preserved by explicit repair.
    # Unsafe links, permissions, unreadable/oversized files never receive a token.
    try:
        token = _repair_token(local_state.read_bytes(root / "source-status.json"), current.revision)
    except (OSError, local_state.LocalSetupError):
        token = None
    return {
        "format": 1,
        "sources": [
            {
                "id": str(source.id),
                "activity": {
                    "phase": "attention",
                    "durability": "unavailable",
                    "reason_code": "source_status_invalid",
                    **({"repair_token": token} if token else {}),
                },
            }
            for source in current.sources
        ],
    }


def _repair(root: Path, current, request: Request) -> dict:
    if not any(source.id == request.id for source in current.sources):
        raise local_state.LocalSetupError(
            "source_settings_changed", "Refresh this source before repairing observations."
        )
    try:
        _load(root)
    except local_state.LocalSetupError:
        pass
    else:
        raise local_state.LocalSetupError(
            "source_status_changed", "Scan status changed. Read it before attempting repair again."
        )
    content = local_state.read_bytes(root / "source-status.json")
    if request.repair_token != _repair_token(content, current.revision):
        raise local_state.LocalSetupError(
            "source_status_changed", "Scan status changed. Read it before attempting repair again."
        )
    observed = datetime.now(timezone.utc)
    records = [
        Record(
            id=source.id,
            fingerprint=fingerprint(source),
            owner=request.owner,
            run=uuid4(),
            phase="waiting",
            reason_code="history_reset",
            next_scan_at=(observed + timedelta(seconds=source.poll_seconds)).isoformat(),
        )
        for source in current.sources
    ]
    local_state.replace_damaged(
        root / "source-status.json",
        State(records=records).model_dump(mode="json", exclude_none=True),
        expected=content,
        kind="source-status",
    )
    return {"format": 1, "repaired": True, "history_restored": False, "original_preserved": True}


def perform(root: Path, value: dict) -> dict:
    from .desktop_sources import load

    request = Request.model_validate(value)
    local_state.directory(root)
    with local_state.lock(root):
        current = load(root)
        if request.expected_revision is not None and current.revision != request.expected_revision:
            raise local_state.LocalSetupError(
                "source_settings_changed", "Source settings changed. Refresh before retrying."
            )
        saved = {source.id: source for source in current.sources}
        if request.operation == "status_repair":
            return _repair(root, current, request)
        try:
            state = _load(root)
        except local_state.LocalSetupError:
            if request.operation == "status":
                return _damaged_view(root, current)
            raise
        records = {
            record.id: record
            for record in state.records
            if record.id in saved and record.fingerprint == fingerprint(saved[record.id])
        }
        if request.operation == "status":
            return {
                "format": 1,
                "sources": [
                    {"id": str(source.id), "activity": _view(records[source.id], request.owner)}
                    for source in current.sources
                    if source.id in records
                ],
            }
        source = saved.get(request.id)
        previous = records.get(request.id)
        if request.operation == "status_begin":
            if source is None or not source.enabled:
                raise local_state.LocalSetupError(
                    "source_settings_changed", "Refresh this source before scanning."
                )
            if previous is not None and previous.run == request.run:
                # An ambiguous begin reply is not a license to replay that run.
                raise local_state.LocalSetupError(
                    "source_status_unconfirmed",
                    "Review the saved scan observation before starting again.",
                )
            last_failure = previous.last_failure if previous else None
            if previous is not None and previous.phase == "scanning":
                last_failure = Failure(observed_at=now(), reason_code="interrupted")
            record = Record(
                id=request.id,
                fingerprint=fingerprint(source),
                owner=request.owner,
                run=request.run,
                phase="scanning",
                started_at=now(),
                report=previous.report if previous else None,
                last_success_report=previous.last_success_report if previous else None,
                last_failure=last_failure,
            )
        else:
            if source is None or previous is None:
                # Removed/reconfigured settings must not resurrect old observations.
                return {"format": 1, "ignored": True}
            if (
                previous.owner != request.owner
                or previous.run != request.run
                or previous.phase != "scanning"
            ):
                raise local_state.LocalSetupError(
                    "source_status_unconfirmed",
                    "The scan observation changed. Read status before retrying.",
                )
            finished = now()
            backfill = backfilling(request.report)
            interval = (
                min(source.poll_seconds, BACKFILL_POLL_SECONDS) if backfill else source.poll_seconds
            )
            reason = request.reason_code or (
                request.report.capture.reason_code
                if backfill
                else "partial"
                if request.report and not request.report.completed
                else None
            )
            report = request.report or previous.report
            record = Record(
                **{
                    **previous.model_dump(),
                    "phase": "backfill" if backfill else "attention" if reason else "complete",
                    "finished_at": finished,
                    "next_scan_at": (
                        datetime.fromisoformat(finished) + timedelta(seconds=interval)
                    ).isoformat(),
                    "reason_code": reason,
                    "report": report,
                    "last_success_report": request.report
                    if request.report and request.report.completed
                    else previous.last_success_report,
                    "last_failure": Failure(observed_at=finished, reason_code=reason)
                    if reason and not backfill
                    else previous.last_failure,
                }
            )
        records[record.id] = record
        local_state.write(
            root / "source-status.json",
            State(records=list(records.values())).model_dump(mode="json", exclude_none=True),
        )
        return {"format": 1, "id": str(record.id), "activity": _view(record, request.owner)}
