"""Resumable, scanned capture of current native revisions into an approved journal."""

from __future__ import annotations

import time
from uuid import uuid4

from pydantic import ValidationError
from psycopg.types.json import Jsonb

from ..journal.format import JournalEntry, JournalError
from ..journal.privacy import scan
from .backfill_models import BackfillControlInput, BackfillRun, BackfillStartInput
from .db import require_administrator, require_space
from .errors import ServiceError
from .models import json_value
from .repository import audit, idempotency, remember_receipt

BATCH_RECORDS = 100
BATCH_BYTES = 2 * 1024**2
BATCH_SECONDS = 5
_REJECTED = {
    "journal_secret_detected",
    "journal_personal_data_detected",
    "journal_scanner_rejected",
    "journal_record_too_large",
    "journal_record_invalid",
}

_CURRENT = """FROM mnemion.memories m
    LEFT JOIN mnemion.memory_revisions r ON r.tenant_id=m.tenant_id
      AND r.space_id=m.space_id AND r.id=m.current_revision_id
    LEFT JOIN mnemion.source_revisions sr ON sr.tenant_id=r.tenant_id
      AND sr.space_id=r.space_id AND sr.id=r.source_revision_id
    LEFT JOIN mnemion.sources s ON s.tenant_id=sr.tenant_id
      AND s.space_id=sr.space_id AND s.id=sr.source_id """
_ELIGIBLE = """m.deleted_at IS NULL AND m.review_state='ordinary'
    AND r.id IS NOT NULL AND s.id IS NOT NULL AND s.deleted_at IS NULL
    AND NOT EXISTS (SELECT FROM mnemion.recovery_denials d
      WHERE d.tenant_id=m.tenant_id AND d.memory_id=m.id)"""
_CAPTURED = """EXISTS (SELECT FROM mnemion.writeback_events e
    WHERE e.tenant_id=m.tenant_id AND e.space_id=m.space_id AND e.memory_id=m.id
      AND e.version=m.version AND e.action='upsert')"""


def _job(conn, space, *, locked=False):
    return conn.execute(
        "SELECT * FROM mnemion.writeback_backfills WHERE space_id=%s"
        + (" FOR UPDATE" if locked else ""),
        (space,),
    ).fetchone()


def _settings(service, conn, identity, space, *, locked=False):
    settings = service._settings(conn, space, locked=locked)
    if settings is None:
        raise ServiceError(409, "journal_not_configured", "Enable a journal destination first.")
    if conn.execute(
        "SELECT 1 FROM mnemion.connector_scopes WHERE space_id=%s", (space,)
    ).fetchone():
        raise ServiceError(409, "journal_native_space_required", "Choose a native memory space.")
    return settings


def _approver_live(conn, job):
    return conn.execute(
        "SELECT mnemion.writeback_backfill_approval_live(%s) AS live",
        (job["space_id"],),
    ).fetchone()["live"]


def _waiting(service, conn, identity, space, settings, job):
    try:
        service.destination(identity, space, settings)
    except ServiceError:
        return "journal_destination_unavailable"
    if settings["paused"]:
        return "journal_paused"
    if not conn.execute("SELECT mnemion.writeback_publisher_live(%s) AS live", (space,)).fetchone()[
        "live"
    ]:
        return "journal_publisher_unavailable"
    if job and job["state"] in {"running", "paused", "blocked"}:
        if settings["version"] != job["policy_version"]:
            return "journal_policy_changed"
        if not _approver_live(conn, job):
            return "journal_backfill_approval_expired"
    return None


def _status(service, conn, identity, space, settings):
    row = _job(conn, space)
    counts = conn.execute(
        "SELECT count(*) AS count,coalesce(sum(octet_length(r.content)),0) AS bytes "
        + _CURRENT
        + " WHERE m.space_id=%s AND "
        + _ELIGIBLE
        + " AND NOT "
        + _CAPTURED,
        (space,),
    ).fetchone()
    return json_value(
        {
            "policy_version": settings["version"],
            "eligible_memories": counts["count"],
            "eligible_content_bytes": counts["bytes"],
            "waiting_reason": _waiting(service, conn, identity, space, settings, row),
            "run": {field: row[field] for field in BackfillRun.model_fields} if row else None,
        }
    )


def status(service, identity, space):
    with service.db.transaction(identity) as conn:
        require_space(conn, space, 40)
        require_administrator(conn)
        settings = _settings(service, conn, identity, space)
        return _status(service, conn, identity, space, settings)


def start(service, identity, space, command: BackfillStartInput, key: str):
    with service.db.administration_transaction(identity) as conn:
        require_space(conn, space, 40, writing=True)
        require_administrator(conn)
        digest, previous = idempotency(
            conn,
            identity,
            space,
            key,
            {"kind": "journal.backfill", **command.model_dump(mode="json")},
        )
        if previous:
            return previous
        settings = _settings(service, conn, identity, space, locked=True)
        if settings["version"] != command.expected_version:
            raise ServiceError(
                409, "version_conflict", "Journal settings changed; review them first."
            )
        waiting = _waiting(service, conn, identity, space, settings, None)
        if waiting:
            raise ServiceError(
                409, waiting, "Repair or resume this journal before starting a backfill."
            )
        current = _job(conn, space, locked=True)
        if command.resume_run:
            if (
                not current
                or current["id"] != command.resume_run
                or current["state"] not in {"running", "paused", "blocked"}
            ):
                raise ServiceError(
                    409, "journal_backfill_changed", "Refresh the current backfill run."
                )
            run_id = current["id"]
            conn.execute(
                """UPDATE mnemion.writeback_backfills SET state='running',policy_version=%s,
                requested_by=%s,last_error=NULL,next_batch_at=clock_timestamp(),updated_at=clock_timestamp()
                WHERE space_id=%s""",
                (settings["version"], identity.principal_id, space),
            )
        else:
            if current and current["state"] in {"running", "paused", "blocked"}:
                raise ServiceError(
                    409, "journal_backfill_active", "Resume or cancel the existing backfill first."
                )
            run_id = uuid4()
            cutoff = conn.execute("SELECT clock_timestamp() AS value").fetchone()["value"]
            total = conn.execute(
                "SELECT count(*) AS count FROM mnemion.memories WHERE space_id=%s AND created_at<=%s",
                (space, cutoff),
            ).fetchone()["count"]
            conn.execute(
                """INSERT INTO mnemion.writeback_backfills
                (tenant_id,space_id,id,policy_version,requested_by,state,cutoff_at,total_at_start)
                VALUES (%s,%s,%s,%s,%s,'running',%s,%s)
                ON CONFLICT(tenant_id,space_id) DO UPDATE SET id=excluded.id,
                  policy_version=excluded.policy_version,requested_by=excluded.requested_by,state='running',
                  cutoff_at=excluded.cutoff_at,cursor_id='00000000-0000-0000-0000-000000000000',
                  total_at_start=excluded.total_at_start,examined=0,queued=0,already_journaled=0,
                  excluded=0,rejected=0,content_bytes=0,errors='[]',last_error=NULL,
                  next_batch_at=clock_timestamp(),started_at=clock_timestamp(),updated_at=clock_timestamp(),
                  finished_at=NULL""",
                (
                    identity.tenant_id,
                    space,
                    run_id,
                    settings["version"],
                    identity.principal_id,
                    cutoff,
                    total,
                ),
            )
        audit(
            conn,
            identity,
            "journal.backfill_resumed" if command.resume_run else "journal.backfill_started",
            run_id,
            space_id=space,
            details={
                "policy_version": settings["version"],
                "existing_memory_publication_approved": True,
                "retained_git_history_acknowledged": True,
            },
        )
        result = _status(service, conn, identity, space, settings)
        return remember_receipt(conn, identity, space, key, digest, result)


def control(service, identity, space, command: BackfillControlInput):
    with service.db.administration_transaction(identity) as conn:
        require_space(conn, space, 40, writing=True)
        require_administrator(conn)
        settings = _settings(service, conn, identity, space, locked=True)
        current = _job(conn, space, locked=True)
        if (
            settings["version"] != command.expected_version
            or not current
            or current["id"] != command.run_id
        ):
            raise ServiceError(
                409, "version_conflict", "The journal or backfill changed; refresh first."
            )
        target = "paused" if command.action == "pause" else "cancelled"
        if current["state"] in {"running", "paused", "blocked"}:
            conn.execute(
                """UPDATE mnemion.writeback_backfills SET state=%s,updated_at=clock_timestamp(),
                finished_at=CASE WHEN %s='cancelled' THEN clock_timestamp() END WHERE space_id=%s""",
                (target, target, space),
            )
            audit(
                conn,
                identity,
                "journal.backfill_" + target,
                current["id"],
                space_id=space,
                details={"queued": current["queued"], "examined": current["examined"]},
            )
        return _status(service, conn, identity, space, settings)


def _record(row, identity, space):
    return JournalEntry(
        id=uuid4(),
        ts=row["recorded_at"],
        tenant_id=identity.tenant_id,
        space_id=space,
        memory_id=row["id"],
        version=row["version"],
        writer=row["author"],
        text=row["content"],
        subject=row["revision_subject"],
        kind=row["revision_kind"],
        metadata=row["metadata"],
        important=row["metadata"].get("important") is True,
    )


def _step(service, identity, space):
    """One memory and its cursor advance share a short authenticated transaction."""
    with service.db.transaction(identity) as conn:
        require_space(conn, space, 30, writing=True)
        settings = _settings(service, conn, identity, space, locked=True)
        current = _job(conn, space, locked=True)
        if not current or current["state"] != "running":
            return None
        if _waiting(service, conn, identity, space, settings, current):
            return None
        destination = service.destination(identity, space, settings)
        row = conn.execute(
            """SELECT m.id,m.version,r.id AS revision_id,
              CASE WHEN octet_length(r.content)<=262144 THEN r.content END AS content,
              CASE WHEN octet_length(r.subject)<=2000 THEN r.subject END AS revision_subject,
              CASE WHEN octet_length(r.metadata::text)<=65536 THEN r.metadata END AS metadata,
              (octet_length(r.content)>262144 OR coalesce(octet_length(r.subject)>2000,false)
                OR octet_length(r.metadata::text)>65536) AS oversized,
              r.kind AS revision_kind,r.recorded_at,r.created_by AS author,"""
            + _ELIGIBLE
            + " AS eligible,"
            + _CAPTURED
            + " AS captured "
            + _CURRENT
            + " WHERE m.space_id=%s AND m.id>%s AND m.created_at<=%s ORDER BY m.id LIMIT 1 FOR UPDATE OF m",
            (space, current["cursor_id"], current["cutoff_at"]),
        ).fetchone()
        if row is None:
            conn.execute(
                """UPDATE mnemion.writeback_backfills SET state='completed',
                finished_at=clock_timestamp(),updated_at=clock_timestamp() WHERE space_id=%s""",
                (space,),
            )
            audit(
                conn,
                identity,
                "journal.backfill_completed",
                current["id"],
                space_id=space,
                details={
                    field: current[field]
                    for field in ("examined", "queued", "rejected", "excluded")
                },
            )
            return None
        count, size, errors = "excluded", 0, list(current["errors"])
        if row["eligible"] and row["captured"]:
            count = "already_journaled"
        elif row["eligible"]:
            try:
                if row["oversized"]:
                    raise JournalError("journal_record_too_large")
                try:
                    entry = _record(row, identity, space)
                except ValidationError:
                    raise JournalError("journal_record_invalid") from None
                scan(
                    entry, personal_data=destination.personal_data_scan, scanner=destination.scanner
                )
                # A slow host scanner must not retain authority through a
                # publisher revocation or the approving administrator's removal.
                service.db._check_identity(conn, identity)
                if _waiting(service, conn, identity, space, settings, current):
                    return None
                conn.execute(
                    """INSERT INTO mnemion.writeback_events
                    (tenant_id,space_id,id,memory_id,revision_id,version,writer,action,important,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,'upsert',%s,%s)""",
                    (
                        identity.tenant_id,
                        space,
                        entry.id,
                        row["id"],
                        row["revision_id"],
                        row["version"],
                        entry.writer,
                        entry.important,
                        entry.ts,
                    ),
                )
                count, size = "queued", len(row["content"].encode("utf-8"))
                # A bounded backfill batch is an explicit publication request.
                # Existing per-event delivery and retry guards still apply.
                conn.execute(
                    "UPDATE mnemion.writeback_settings SET next_push_at=clock_timestamp() WHERE space_id=%s",
                    (space,),
                )
            except JournalError as error:
                if error.code not in _REJECTED:
                    conn.execute(
                        """UPDATE mnemion.writeback_backfills SET state='blocked',
                        last_error='journal_scanner_unavailable',updated_at=clock_timestamp() WHERE space_id=%s""",
                        (space,),
                    )
                    return None
                count = "rejected"
                if len(errors) < 50:
                    errors.append(
                        {"memory_id": str(row["id"]), "version": row["version"], "code": error.code}
                    )
        # The field name is chosen only from the fixed cases above, never input.
        conn.execute(
            f"""UPDATE mnemion.writeback_backfills SET cursor_id=%s,examined=examined+1,
            {count}={count}+1,content_bytes=content_bytes+%s,errors=%s,updated_at=clock_timestamp()
            WHERE space_id=%s""",
            (row["id"], size, Jsonb(errors), space),
        )
        return size


def run_batch(service, identity, space):
    destination = service.destination(identity, space)
    records = min(BATCH_RECORDS, destination.max_batch_entries)
    byte_limit = min(BATCH_BYTES, destination.max_batch_bytes)
    size, processed = 0, 0
    deadline = time.monotonic() + BATCH_SECONDS
    while processed < records and size < byte_limit and not service._stop.is_set():
        result = _step(service, identity, space)
        if result is None:
            break
        size += result
        processed += 1
        if time.monotonic() >= deadline:
            break
    return {"examined": processed, "content_bytes": size}
