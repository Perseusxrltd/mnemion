"""Durable leased indexing. Model inference never holds a database transaction."""

from __future__ import annotations

import logging
import threading
import time
from uuid import uuid4

from .db import Database
from .embeddings import Embedder, vector_literal
from .lifecycle import purge_memory
from .fences import shared_boundary
from .model_state import job_policy
from .telemetry import Telemetry

logger = logging.getLogger(__name__)


class Worker:
    def __init__(
        self,
        database: Database,
        embedder: Embedder,
        *,
        lease_seconds: int = 120,
        max_attempts: int = 5,
        telemetry: Telemetry | None = None,
        default_generation: str | None = None,
    ):
        if not database.worker:
            raise ValueError("A separate worker database login is required")
        self.db = database
        self.embedder = embedder
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self.telemetry = telemetry
        self.default_generation = default_generation or embedder.generation.id

    def claim(self) -> dict | None:
        with self.db.pool.connection() as conn:
            return conn.execute(
                "SELECT * FROM mnemion.claim_job(%s, %s, %s)",
                (uuid4(), self.lease_seconds, self.embedder.generation.id),
            ).fetchone()

    def _keep_lease(self, job: dict, stopped: threading.Event) -> None:
        while not stopped.wait(max(1, self.lease_seconds / 3)):
            try:
                with self.db.worker_transaction(job["tenant_id"]) as conn:
                    row = conn.execute(
                        """UPDATE mnemion.jobs SET lease_until=now()+make_interval(secs=>%s)
                           WHERE id=%s AND state='leased' AND lease_id=%s AND lease_until>now()
                           RETURNING id""",
                        (self.lease_seconds, job["id"], job["lease_id"]),
                    ).fetchone()
                    if not row:
                        return
            except Exception as exc:
                # Finalization checks the lease again. Losing a heartbeat can
                # cause a retry, but cannot authorize a stale worker to publish.
                logger.warning("Lease heartbeat failed (%s)", type(exc).__name__)
                return

    @staticmethod
    def _owned(conn, job: dict) -> dict | None:
        return conn.execute(
            """SELECT * FROM mnemion.jobs WHERE tenant_id=%s AND space_id=%s AND id=%s
               AND state='leased' AND lease_id=%s AND lease_until>now() FOR UPDATE""",
            (job["tenant_id"], job["space_id"], job["id"], job["lease_id"]),
        ).fetchone()

    @staticmethod
    def _finish(conn, job: dict, state: str = "ready") -> None:
        conn.execute(
            """UPDATE mnemion.jobs SET state=%s, lease_id=NULL, lease_until=NULL, error_code=NULL
               WHERE id=%s""",
            (state, job["id"]),
        )
        conn.execute(
            "UPDATE mnemion.operations SET state=%s, error_code=NULL, updated_at=now() WHERE id=%s",
            (state, job["operation_id"]),
        )

    def process(self, job: dict) -> bool:
        """Return False if another worker or a deletion invalidated this lease."""
        if job["kind"] == "purge":
            return self._purge(job)
        with self.db.worker_transaction(job["tenant_id"]) as conn:
            shared_boundary(conn, job["tenant_id"], job["space_id"])
            if not self._owned(conn, job):
                return False
            if not self._policy(conn, job):
                return False
            row = conn.execute(
                """SELECT r.content FROM mnemion.memory_revisions r JOIN mnemion.memories m
                     ON m.tenant_id=r.tenant_id AND m.space_id=r.space_id AND m.id=r.memory_id
                   WHERE r.id=%s AND m.deleted_at IS NULL AND EXISTS (
                     SELECT FROM mnemion.source_revisions sr JOIN mnemion.sources s
                       ON s.tenant_id=sr.tenant_id AND s.space_id=sr.space_id AND s.id=sr.source_id
                     WHERE sr.tenant_id=r.tenant_id AND sr.space_id=r.space_id
                       AND sr.id=r.source_revision_id AND s.deleted_at IS NULL)""",
                (job["revision_id"],),
            ).fetchone()
            if not row:
                self._finish(conn, job, "cancelled")
                return False
            conn.execute(
                "UPDATE mnemion.operations SET state='indexing', updated_at=now() WHERE id=%s",
                (job["operation_id"],),
            )
        if job["generation_id"] != self.embedder.generation.id:
            raise ValueError("Worker generation does not match queued generation")
        stopped = threading.Event()
        heartbeat = threading.Thread(target=self._keep_lease, args=(job, stopped), daemon=True)
        heartbeat.start()
        try:
            chunks = self.embedder.document(row["content"])
        finally:
            stopped.set()
            heartbeat.join(timeout=1)
        if not chunks:
            raise ValueError("Model returned no embedding chunks")
        # Inference may have taken seconds, or a worker may have been killed.
        # Lock and check the lease again before publishing any vector rows.
        with self.db.worker_transaction(job["tenant_id"]) as conn:
            shared_boundary(conn, job["tenant_id"], job["space_id"])
            live = conn.execute(
                """SELECT m.id FROM mnemion.memories m JOIN mnemion.memory_revisions r
                     ON r.tenant_id=m.tenant_id AND r.space_id=m.space_id AND r.memory_id=m.id
                   WHERE r.id=%s AND m.deleted_at IS NULL AND EXISTS (
                     SELECT FROM mnemion.source_revisions sr JOIN mnemion.sources s
                       ON s.tenant_id=sr.tenant_id AND s.space_id=sr.space_id AND s.id=sr.source_id
                     WHERE sr.tenant_id=r.tenant_id AND sr.space_id=r.space_id
                       AND sr.id=r.source_revision_id AND s.deleted_at IS NULL) FOR UPDATE OF m""",
                (job["revision_id"],),
            ).fetchone()
            # Deletion also locks memory before jobs. Keep that order to avoid
            # a worker-finalization/delete deadlock.
            if not self._owned(conn, job):
                return False
            if not self._policy(conn, job, finishing=True):
                return False
            if not live:
                self._finish(conn, job, "cancelled")
                return False
            conn.execute(
                "DELETE FROM mnemion.embeddings WHERE revision_id=%s AND generation_id=%s",
                (job["revision_id"], job["generation_id"]),
            )
            for index, chunk in enumerate(chunks):
                if not 0 <= chunk.start < chunk.end <= len(row["content"]):
                    raise ValueError("Embedding chunk offsets are invalid")
                conn.execute(
                    """INSERT INTO mnemion.embeddings
                         (tenant_id, space_id, revision_id, generation_id, chunk_index,
                          start_offset, end_offset, embedding)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)""",
                    (
                        job["tenant_id"],
                        job["space_id"],
                        job["revision_id"],
                        job["generation_id"],
                        index,
                        chunk.start,
                        chunk.end,
                        vector_literal(chunk.vector, self.embedder.generation.dimensions),
                    ),
                )
            self._finish(conn, job)
            job["metric_input_bytes"] = len(row["content"].encode("utf-8"))
            job["metric_chunks"] = len(chunks)
            return True

    def _policy(self, conn, job, *, finishing=False):
        policy = job_policy(conn, job, self.default_generation)
        if policy == "obsolete":
            self._finish(conn, job, "cancelled")
            return False
        if policy == "blocked" or (policy == "paused" and not finishing):
            conn.execute(
                "UPDATE mnemion.jobs SET state='pending',lease_id=NULL,lease_until=NULL,attempts=greatest(0,attempts-1) WHERE id=%s",
                (job["id"],),
            )
            return False
        if not conn.execute(
            "SELECT mnemion.embedding_source_current(%s) AS current", (job["space_id"],)
        ).fetchone()["current"]:
            conn.execute(
                """UPDATE mnemion.jobs SET state='pending',lease_id=NULL,lease_until=NULL,
                   attempts=greatest(0,attempts-1),available_at=now()+interval '60 seconds',error_code='source_access_unavailable'
                   WHERE id=%s""",
                (job["id"],),
            )
            conn.execute(
                "UPDATE mnemion.operations SET state='accepted',error_code='source_access_unavailable',updated_at=now() WHERE id=%s",
                (job["operation_id"],),
            )
            return False
        return True

    def _purge(self, job: dict) -> bool:
        with self.db.worker_transaction(job["tenant_id"]) as conn:
            if not self._owned(conn, job):
                return False
            memory = conn.execute(
                "SELECT memory_id FROM mnemion.operations WHERE id=%s", (job["operation_id"],)
            ).fetchone()["memory_id"]
            row = conn.execute(
                "SELECT * FROM mnemion.memories WHERE id=%s FOR UPDATE", (memory,)
            ).fetchone()
            if not row or not row["deleted_at"]:
                self._finish(conn, job, "cancelled")
                return False
            purge_memory(conn, job["tenant_id"], job["space_id"], memory)
            self._finish(conn, job)
            return True

    def fail(self, job: dict, error: Exception) -> None:
        with self.db.worker_transaction(job["tenant_id"]) as conn:
            if not self._owned(conn, job):
                return
            terminal = job["attempts"] >= self.max_attempts
            code = type(error).__name__[:100]
            conn.execute(
                """UPDATE mnemion.jobs SET state=%s, lease_id=NULL, lease_until=NULL,
                          available_at=now()+make_interval(secs=>%s), error_code=%s WHERE id=%s""",
                (
                    "failed" if terminal else "pending",
                    min(300, 2 ** job["attempts"]),
                    code,
                    job["id"],
                ),
            )
            conn.execute(
                "UPDATE mnemion.operations SET state=%s, error_code=%s, updated_at=now() WHERE id=%s",
                ("failed" if terminal else "accepted", code, job["operation_id"]),
            )
        logger.warning(
            "Index operation %s failed (%s); terminal=%s",
            job["operation_id"],
            type(error).__name__,
            terminal,
        )

    def run_once(self) -> bool:
        job = self.claim()
        if not job:
            return False
        started, failed, processed = time.monotonic(), False, False
        try:
            processed = self.process(job)
        except Exception as exc:
            failed = True
            self.fail(job, exc)
        finally:
            if self.telemetry:
                try:
                    chunks = job.get("metric_chunks", 0)
                    self.telemetry.record(
                        job["tenant_id"],
                        job["space_id"],
                        stage="purge" if job["kind"] == "purge" else "index",
                        origin="background",
                        generation=self.embedder.generation.id,
                        failed=failed,
                        duration_ms=(time.monotonic() - started) * 1000,
                        input_bytes=job.get("metric_input_bytes", 0),
                        chunks=chunks,
                        records=int(processed),
                        output_bytes=chunks * self.embedder.generation.dimensions * 4,
                    )
                except Exception:
                    logger.warning("Indexing diagnostic sample was not recorded")
        return True
