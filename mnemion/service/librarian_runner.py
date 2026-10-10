"""Leased, low-concurrency librarian work using the initiating live identity."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from uuid import uuid4

from psycopg.types.json import Jsonb

from .db import Identity, require_space
from .errors import ServiceError
from .librarian import LibrarianService
from .librarian_models import LibrarianRunInput
from .librarian_provider import LibrarianProviderError

logger = logging.getLogger(__name__)


class LibrarianRunner:
    def __init__(self, service: LibrarianService):
        if service.db.worker:
            raise ValueError(
                "Librarian jobs require the restricted API login and initiating identity"
            )
        self.service, self.db, self.registry = service, service.db, service.registry
        self._job = None
        self._thread = None
        self._stop = threading.Event()
        self._step_lock = threading.Lock()

    def start(self):
        if self._thread is None and self.registry.providers:
            self._thread = threading.Thread(
                target=self._loop, name="mnemion-librarian", daemon=True
            )
            self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as exc:
                logger.warning("Librarian deferred (%s)", type(exc).__name__)
            self._stop.wait(2)

    @staticmethod
    def _identity(job):
        return Identity(job["tenant_id"], job["created_by"], job["key_id"])

    def _live(self, conn, job, *, writing=False):
        require_space(conn, job["space_id"], 30, writing=writing)
        settings = self.service._active_settings(conn, job["space_id"])
        if (
            settings["version"] != job["settings_version"]
            or settings["profile_fingerprint"] != job["profile_fingerprint"]
        ):
            raise ServiceError(409, "configuration_changed", "Librarian configuration changed.")
        row = conn.execute(
            """SELECT * FROM mnemion.librarian_runs WHERE space_id=%s AND id=%s
                AND state='running' AND lease_id=%s AND lease_until>now() FOR UPDATE""",
            (job["space_id"], job["id"], job["lease_id"]),
        ).fetchone()
        if (
            row
            and (datetime.now(timezone.utc) - row["started_at"]).total_seconds()
            > row["configuration"]["max_seconds"]
        ):
            raise ServiceError(
                409, "time_budget_exhausted", "The librarian run exhausted its time budget."
            )
        return row

    def _schedule(self):
        with self.db.pool.connection() as conn:
            settings = conn.execute(
                "SELECT * FROM mnemion.claim_librarian_schedule(%s)",
                (self.registry.fingerprints,),
            ).fetchone()
        if settings:
            try:
                self.service.create_run(
                    self._identity(settings),
                    settings["space_id"],
                    LibrarianRunInput(mode=settings["mode"]),
                    f"librarian-schedule-{settings['version']}-{settings['next_run_at'].isoformat()}",
                )
            except ServiceError as exc:
                # The schedule has advanced. A revoked key cannot hold the queue,
                # or acquire a replacement identity on its own.
                logger.info("Scheduled librarian deferred (%s)", exc.code)

    def run_once(self):
        if not self.registry.providers or not self._step_lock.acquire(blocking=False):
            return False
        try:
            if self._job is None:
                self._schedule()
                with self.db.pool.connection() as conn:
                    self._job = conn.execute(
                        "SELECT * FROM mnemion.claim_librarian(%s,%s)",
                        (uuid4(), self.registry.fingerprints),
                    ).fetchone()
            if not self._job:
                return False
            job = self._job
            try:
                self._step(job)
            except Exception as exc:
                reason = "librarian_error"
                sent = received = 0
                elapsed = 0.0
                if isinstance(exc, ServiceError):
                    reason = "access_revoked" if exc.status in (401, 403, 404) else exc.code
                    if reason == "librarian_disabled":
                        reason = "configuration_changed"
                if isinstance(exc, LibrarianProviderError):
                    reason = exc.code
                    sent, received, elapsed = exc.request_bytes, exc.response_bytes, exc.latency_ms
                allowed = {
                    "access_revoked",
                    "reference_unavailable",
                    "provider_error",
                    "time_budget_exhausted",
                    "librarian_profile_unavailable",
                    "configuration_changed",
                    "daily_budget_exhausted",
                    "input_budget_exceeded",
                    "inference_busy",
                    "tokenizer_unavailable",
                    "credentials_unavailable",
                    "run_cancelled",
                }
                if reason not in allowed:
                    reason = "librarian_error"
                with self.db.pool.connection() as conn:
                    conn.execute(
                        "SELECT mnemion.fail_librarian(%s,%s,%s,%s,%s,%s)",
                        (
                            job["id"],
                            job["lease_id"],
                            reason,
                            sent,
                            min(received, 2097152),
                            min(elapsed, 600000.0),
                        ),
                    )
                self._job = None
                logger.warning("Librarian ended (%s)", reason)
            return True
        finally:
            self._step_lock.release()

    def _heartbeat(self, job, stopped, accepted):
        while not stopped.wait(15):
            try:
                with self.db.transaction(self._identity(job)) as conn:
                    if self._stop.is_set() or not self._live(conn, job):
                        accepted.clear()
                        return
                    conn.execute(
                        "UPDATE mnemion.librarian_runs SET lease_until=now()+interval '120 seconds' WHERE space_id=%s AND id=%s",
                        (job["space_id"], job["id"]),
                    )
            except Exception:
                accepted.clear()
                return

    @staticmethod
    def _records(conn, job, items, *, lock=False):
        result = []
        for item in sorted(items, key=lambda row: row["memory_id"]):
            # Lock order agrees with human decisions and deletion. Do not load
            # full source attachments or arbitrary metadata into a model prompt.
            memory = conn.execute(
                "SELECT * FROM mnemion.memories WHERE space_id=%s AND id=%s"
                + (" FOR UPDATE" if lock else ""),
                (job["space_id"], item["memory_id"]),
            ).fetchone()
            if (
                not memory
                or memory["deleted_at"]
                or memory["review_state"] != "ordinary"
                or memory["version"] != item["memory_version"]
                or memory["current_revision_id"] != item["revision_id"]
            ):
                raise ServiceError(
                    409, "reference_unavailable", "A selected memory changed or is unavailable."
                )
            revision = conn.execute(
                """SELECT r.content,r.subject,r.kind,r.claim_status,r.metadata->'tags' AS tags,
                    r.metadata->'summary' AS summary FROM mnemion.memory_revisions r
                    JOIN mnemion.source_revisions sr ON sr.tenant_id=r.tenant_id AND sr.space_id=r.space_id AND sr.id=r.source_revision_id
                    JOIN mnemion.sources s ON s.tenant_id=sr.tenant_id AND s.space_id=sr.space_id AND s.id=sr.source_id
                    WHERE r.space_id=%s AND r.id=%s AND s.deleted_at IS NULL""",
                (job["space_id"], item["revision_id"]),
            ).fetchone()
            if not revision:
                raise ServiceError(
                    409, "reference_unavailable", "Selected source evidence is unavailable."
                )
            result.append({"memory_id": str(item["memory_id"]), **revision})
        return result

    def _reserve(self, job, items, units):
        with self.db.transaction(self._identity(job)) as conn:
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                ("librarian-settings:" + str(job["space_id"]),),
            )
            if self._stop.is_set() or not self._live(conn, job, writing=True):
                raise ServiceError(
                    409, "configuration_changed", "The librarian run is no longer active."
                )
            self._records(conn, job, items)
            settings = self.service._active_settings(conn, job["space_id"])
            reservation = conn.execute(
                """INSERT INTO mnemion.librarian_budgets(tenant_id,space_id,day,calls_reserved)
                    VALUES(%s,%s,(now() AT TIME ZONE 'UTC')::date,1)
                    ON CONFLICT(tenant_id,space_id,day) DO UPDATE SET calls_reserved=mnemion.librarian_budgets.calls_reserved+1
                    WHERE mnemion.librarian_budgets.calls_reserved<%s RETURNING calls_reserved""",
                (job["tenant_id"], job["space_id"], settings["max_calls_per_day"]),
            ).fetchone()
            if not reservation:
                raise ServiceError(
                    429,
                    "daily_budget_exhausted",
                    "This space has used today's librarian call budget.",
                )
            conn.execute(
                "UPDATE mnemion.librarian_runs SET calls_reserved=calls_reserved+1,input_units=input_units+%s WHERE space_id=%s AND id=%s",
                (units, job["space_id"], job["id"]),
            )
            # A lost response can still be a billable call. Ordinary and scheduled
            # sweeps must not select this unchanged revision again after a crash.
            for item in items:
                self._observe(conn, job, item, "attempted")

    def _step(self, job):
        identity = self._identity(job)
        with self.db.transaction(identity) as conn:
            current = self._live(conn, job, writing=True)
            if not current:
                raise ServiceError(409, "run_cancelled", "The librarian run is no longer active.")
            job.update(current)
            items = conn.execute(
                "SELECT * FROM mnemion.librarian_items WHERE space_id=%s AND run_id=%s AND state='pending' ORDER BY position",
                (job["space_id"], job["id"]),
            ).fetchall()
            if not items:
                self._complete(conn, job)
                return
            if job["mode"] == "organize":
                items = items[:1]
            records = self._records(conn, job, items)
        provider = self.registry.get(job["profile_id"])
        try:
            provider.prepare_request(records, job["mode"])
        except ServiceError as exc:
            if exc.code != "input_budget_exceeded":
                raise
            with self.db.transaction(identity) as conn:
                if not self._live(conn, job, writing=True):
                    raise ServiceError(
                        409, "run_cancelled", "The librarian run is no longer active."
                    )
                self._mark_items(conn, job, items, "skipped", "input_budget_exceeded")
                conn.execute(
                    "UPDATE mnemion.librarian_runs SET skipped=skipped+%s WHERE space_id=%s AND id=%s",
                    (len(items), job["space_id"], job["id"]),
                )
            return
        stopped, accepted = threading.Event(), threading.Event()
        accepted.set()
        heartbeat = threading.Thread(
            target=self._heartbeat, args=(job, stopped, accepted), daemon=True
        )
        heartbeat.start()
        try:
            result = provider.generate(
                records,
                job["mode"],
                reserve=lambda units: self._reserve(job, items, units),
                live=lambda: accepted.is_set() and not self._stop.is_set(),
            )
        finally:
            stopped.set()
            heartbeat.join(timeout=1)
        with self.db.transaction(identity) as conn:
            if not self._live(conn, job, writing=True):
                raise ServiceError(409, "run_cancelled", "The librarian run is no longer active.")
            self._records(conn, job, items, lock=True)
            for suggestion in result.output.proposals:
                proposal = uuid4()
                conn.execute(
                    """INSERT INTO mnemion.librarian_proposals(tenant_id,space_id,id,run_id,memory_id,suggestion)
                        VALUES(%s,%s,%s,%s,%s,%s)""",
                    (
                        job["tenant_id"],
                        job["space_id"],
                        proposal,
                        job["id"],
                        suggestion.memory_id,
                        Jsonb(suggestion.model_dump(mode="json")),
                    ),
                )
                # Every supplied record can influence a model result, even if the
                # model cites only a subset. Retain all input dependencies.
                for item in items:
                    conn.execute(
                        """INSERT INTO mnemion.librarian_dependencies
                            (tenant_id,space_id,proposal_id,memory_id,revision_id,memory_version)
                            VALUES(%s,%s,%s,%s,%s,%s)""",
                        (
                            job["tenant_id"],
                            job["space_id"],
                            proposal,
                            item["memory_id"],
                            item["revision_id"],
                            item["memory_version"],
                        ),
                    )
            self._mark_items(conn, job, items, "completed")
            conn.execute(
                """UPDATE mnemion.librarian_runs SET processed=processed+%s,proposal_count=proposal_count+%s,
                    output_tokens=CASE WHEN calls_completed=0 THEN %s::bigint
                        WHEN output_tokens IS NULL OR %s::bigint IS NULL THEN NULL ELSE output_tokens+%s END,
                    calls_completed=calls_completed+1,request_bytes=request_bytes+%s,
                    response_bytes=response_bytes+%s,latency_ms=latency_ms+%s
                    WHERE space_id=%s AND id=%s""",
                (
                    len(items),
                    len(result.output.proposals),
                    result.output_tokens,
                    result.output_tokens,
                    result.output_tokens,
                    result.request_bytes,
                    result.response_bytes,
                    result.latency_ms,
                    job["space_id"],
                    job["id"],
                ),
            )
            if (
                conn.execute(
                    "SELECT 1 AS present FROM mnemion.librarian_items WHERE space_id=%s AND run_id=%s AND state='pending'",
                    (job["space_id"], job["id"]),
                ).fetchone()
                is None
            ):
                self._complete(conn, job)

    @staticmethod
    def _observe(conn, job, item, outcome):
        conn.execute(
            """INSERT INTO mnemion.librarian_observations
                (tenant_id,space_id,memory_id,profile_fingerprint,mode,memory_version,outcome)
                VALUES(%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(tenant_id,space_id,memory_id,profile_fingerprint,mode)
                DO UPDATE SET memory_version=excluded.memory_version,outcome=excluded.outcome,checked_at=now()""",
            (
                job["tenant_id"],
                job["space_id"],
                item["memory_id"],
                job["profile_fingerprint"],
                job["mode"],
                item["memory_version"],
                outcome,
            ),
        )

    @classmethod
    def _mark_items(cls, conn, job, items, state, reason=None):
        for item in items:
            conn.execute(
                "UPDATE mnemion.librarian_items SET state=%s,reason=%s WHERE space_id=%s AND run_id=%s AND position=%s",
                (state, reason, job["space_id"], job["id"], item["position"]),
            )
            cls._observe(conn, job, item, state)

    def _complete(self, conn, job):
        completed = conn.execute(
            """UPDATE mnemion.librarian_runs SET state='completed',lease_id=NULL,lease_until=NULL,finished_at=now()
                WHERE space_id=%s AND id=%s AND processed+skipped=selected
                  AND NOT EXISTS(SELECT FROM mnemion.librarian_items i
                    WHERE i.tenant_id=mnemion.librarian_runs.tenant_id AND i.space_id=mnemion.librarian_runs.space_id
                      AND i.run_id=mnemion.librarian_runs.id AND i.state='pending')
                RETURNING id""",
            (job["space_id"], job["id"]),
        ).fetchone()
        if completed is None:
            raise RuntimeError("Librarian run still has unfinished items")
        self._job = None
