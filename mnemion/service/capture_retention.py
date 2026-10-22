"""Bounded cleanup of administrator-approved, server-timed capture lifetimes.

The worker claims stored policy decisions. It never uses a model, a device key,
producer timestamps, or a caller-supplied memory list to authorize deletion.
"""

from dataclasses import dataclass
import logging
import time
from uuid import UUID, uuid4

from .capture_custody import source_lock
from .fences import write_boundary
from .errors import ServiceError
from .memory import MemoryService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeletionActor:
    """Historical attribution for an automatic action, never a login identity."""

    tenant_id: UUID
    principal_id: UUID


class CaptureRetentionWorker:
    def __init__(self, database):
        if not database.worker:
            raise ValueError("Capture retention requires the separate worker database login")
        self.db = database
        # Delete operations do not require an embedding generation or model.
        self.memory = MemoryService(database, None)
        self.next_check = 0.0

    def claim(self):
        with self.db.pool.connection() as conn:
            return conn.execute(
                "SELECT * FROM mnemion.claim_capture_expiry(%s,120)", (uuid4(),)
            ).fetchone()

    @staticmethod
    def owned(conn, job):
        return conn.execute(
            """SELECT x.*,s.space_id,p.approved_by,p.capture_policy
               FROM mnemion.capture_expiries x
               JOIN mnemion.capture_sources s USING(tenant_id,source_id)
               JOIN mnemion.capture_policy_versions p ON p.tenant_id=x.tenant_id
                 AND p.source_id=x.source_id AND p.policy_version=x.policy_version
               WHERE x.tenant_id=%s AND x.source_id=%s AND x.lineage_id=%s
                 AND x.state='leased' AND x.lease_id=%s AND x.lease_until>clock_timestamp()
                 AND x.expires_at<=clock_timestamp() FOR UPDATE OF x""",
            (job["tenant_id"], job["source_id"], job["lineage_id"], job["lease_id"]),
        ).fetchone()

    def process(self, job):
        with self.db.worker_transaction(job["tenant_id"]) as conn:
            # Match capture acceptance and canonical withdrawal lock order.
            source_lock(conn, job["source_id"])
            current = self.owned(conn, job)
            if current is None:
                return False
            policy = current["capture_policy"]
            if (
                not current["approved_by"]
                or not policy
                or policy.get("retention") != "expire_after"
                or policy.get("expiry_scope") != "captured_fragment_family"
            ):
                raise ValueError("Capture retention lacks its approved policy")
            write_boundary(conn, current["tenant_id"], current["space_id"])
            # The fence is permanent, including while a large family is being
            # cleaned in bounded batches. New revisions cannot reset its clock.
            conn.execute(
                """INSERT INTO mnemion.capture_denials(tenant_id,source_id,lineage_id,forgotten_at)
                   VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (
                    current["tenant_id"],
                    current["source_id"],
                    current["lineage_id"],
                    current["expires_at"],
                ),
            )
            rows = conn.execute(
                """SELECT m.* FROM mnemion.capture_events e JOIN mnemion.memories m
                     ON m.tenant_id=e.tenant_id AND m.space_id=e.space_id AND m.id=e.memory_id
                   WHERE e.source_id=%s AND e.lineage_id=%s AND m.deleted_at IS NULL
                   ORDER BY m.id LIMIT 32 FOR UPDATE OF m""",
                (current["source_id"], current["lineage_id"]),
            ).fetchall()
            for row in rows:
                self.memory._forget_record(
                    conn,
                    DeletionActor(row["tenant_id"], row["created_by"]),
                    row,
                    details={
                        "cause": "capture_retention",
                        "source_id": current["source_id"],
                        "policy_version": current["policy_version"],
                        "approved_by": current["approved_by"],
                        "expires_at": current["expires_at"],
                    },
                )
            remaining = conn.execute(
                """SELECT 1 FROM mnemion.capture_events e JOIN mnemion.memories m
                     ON m.tenant_id=e.tenant_id AND m.space_id=e.space_id AND m.id=e.memory_id
                   WHERE e.source_id=%s AND e.lineage_id=%s AND m.deleted_at IS NULL LIMIT 1""",
                (current["source_id"], current["lineage_id"]),
            ).fetchone()
            conn.execute(
                """UPDATE mnemion.capture_expiries SET state=%s,lease_id=NULL,lease_until=NULL,
                   attempts=0,error_code=NULL,available_at=clock_timestamp(),
                   completed_at=CASE WHEN %s THEN NULL ELSE clock_timestamp() END
                   WHERE source_id=%s AND lineage_id=%s AND lease_id=%s""",
                (
                    "pending" if remaining else "expired",
                    bool(remaining),
                    current["source_id"],
                    current["lineage_id"],
                    current["lease_id"],
                ),
            )
            return True

    def fail(self, job, error):
        code = (
            "space_paused"
            if isinstance(error, ServiceError) and error.code == "space_paused"
            else type(error).__name__[:100]
        )
        with self.db.worker_transaction(job["tenant_id"]) as conn:
            conn.execute(
                """UPDATE mnemion.capture_expiries SET state='pending',lease_id=NULL,lease_until=NULL,
                   error_code=%s,available_at=clock_timestamp()+make_interval(secs=>%s)
                   WHERE source_id=%s AND lineage_id=%s AND state='leased' AND lease_id=%s""",
                (
                    code,
                    min(300, 2 ** min(job["attempts"], 8)),
                    job["source_id"],
                    job["lineage_id"],
                    job["lease_id"],
                ),
            )
        logger.warning("Capture retention remains pending (%s)", type(error).__name__)

    def run_once(self):
        if time.monotonic() < self.next_check:
            return False
        job = self.claim()
        if not job:
            self.next_check = time.monotonic() + 30
            return False
        try:
            return self.process(job)
        except Exception as error:
            self.fail(job, error)
            return False
