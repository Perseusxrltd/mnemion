"""Recoverable candidate indexing, explicit egress approval and atomic cutover."""

from __future__ import annotations

from uuid import UUID, uuid4

from .db import Database, Identity, require_space
from .errors import ServiceError, not_found
from .fences import exclusive_boundary, shared_boundary
from .model_registry import ModelRegistry
from .model_state import enqueue_candidate, settings
from .models import json_value
from .repository import audit, idempotency, remember_receipt


REVISIONS = """
FROM mnemion.memory_revisions r JOIN mnemion.memories m
  ON m.tenant_id=r.tenant_id AND m.space_id=r.space_id AND m.id=r.memory_id
WHERE r.space_id=%(space)s AND m.deleted_at IS NULL AND EXISTS (
  SELECT FROM mnemion.source_revisions sr JOIN mnemion.sources s
    ON s.tenant_id=sr.tenant_id AND s.space_id=sr.space_id AND s.id=sr.source_id
  WHERE sr.tenant_id=r.tenant_id AND sr.space_id=r.space_id AND sr.id=r.source_revision_id
    AND s.deleted_at IS NULL)
"""


def coverage(conn, space, generation) -> dict:
    return conn.execute(
        """SELECT count(*) AS revisions,
           count(*) FILTER(WHERE EXISTS(SELECT FROM mnemion.embeddings e
             WHERE e.tenant_id=r.tenant_id AND e.space_id=r.space_id
               AND e.revision_id=r.id AND e.generation_id=%(generation)s)) AS indexed_revisions """
        + REVISIONS,
        {"space": space, "generation": generation},
    ).fetchone()


class ReindexService:
    def __init__(self, database: Database, registry: ModelRegistry):
        self.db, self.registry = database, registry

    def _state(self, conn, space) -> dict:
        current = settings(conn, space, self.registry.default.generation.id)
        candidate = None
        if current["candidate_run_id"]:
            run = conn.execute(
                "SELECT * FROM mnemion.reindex_runs WHERE space_id=%s AND id=%s",
                (space, current["candidate_run_id"]),
            ).fetchone()
            counts = coverage(conn, space, run["generation_id"])
            jobs = conn.execute(
                "SELECT state,count(*) AS count FROM mnemion.jobs WHERE space_id=%s AND reindex_run_id=%s GROUP BY state ORDER BY state",
                (space, run["id"]),
            ).fetchall()
            candidate = {
                "id": run["id"],
                "generation_id": run["generation_id"],
                "state": run["state"],
                "scan_complete": run["scan_complete"],
                **counts,
                "jobs": jobs,
                "ready_to_activate": run["scan_complete"]
                and counts["revisions"] == counts["indexed_revisions"],
                "network_egress_approved": run["network_egress_approved"],
                "created_at": run["created_at"],
                "updated_at": run["updated_at"],
            }
        registered = {
            row["id"] for row in conn.execute("SELECT id FROM mnemion.embedding_generations")
        }
        return json_value(
            {
                "space_id": space,
                "version": current["version"],
                "active_generation_id": current["active_generation_id"],
                "inference_paused": current.get("inference_paused", False),
                "previous_generation_id": current.get("previous_generation_id"),
                "candidate": candidate,
                "profiles": [
                    {**p, "registered": p["generation_id"] in registered}
                    for p in self.registry.describe()
                ],
            }
        )

    def read(self, identity: Identity, space: UUID) -> dict:
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 40)
            return self._state(conn, space)

    def choices(self, identity: Identity, space: UUID) -> dict:
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            current = settings(conn, space, self.registry.default.generation.id)
            profiles = {p["generation_id"]: p for p in self.registry.describe()}
            result = []
            for state, generation in (
                ("active", current["active_generation_id"]),
                ("candidate", current["candidate_generation_id"]),
            ):
                if generation:
                    profile = profiles.get(generation)
                    result.append(
                        {
                            "generation_id": generation,
                            "state": state,
                            "label": profile["label"] if profile else "Unavailable model",
                            "available": profile is not None
                            and not (
                                (state == "active" and current.get("inference_paused"))
                                or (
                                    state == "candidate"
                                    and profile["network_egress"]
                                    and not current.get("candidate_network_egress_approved")
                                )
                            ),
                            "token_count_unit": profile["token_count_unit"] if profile else None,
                        }
                    )
            return {"items": result}

    def start(self, identity: Identity, space: UUID, command, key: str) -> dict:
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 40)
            exclusive_boundary(conn, identity.tenant_id, space)
            require_space(conn, space, 40, writing=True)
            digest, previous = idempotency(
                conn,
                identity,
                space,
                key,
                {"kind": "embedding_reindex", **command.model_dump(mode="json")},
            )
            if previous:
                return previous
            model = self.registry.profile(command.profile_id)
            generation = model.generation.id
            descriptor = next(p for p in self.registry.describe() if p["id"] == command.profile_id)
            if descriptor["network_egress"] and not command.approve_network_egress:
                raise ServiceError(
                    422,
                    "embedding_egress_approval_required",
                    "A space administrator must approve sending this space's text to the configured endpoint.",
                )
            if not conn.execute(
                "SELECT id FROM mnemion.embedding_generations WHERE id=%s", (generation,)
            ).fetchone():
                raise ServiceError(
                    503,
                    "embedding_model_not_registered",
                    "The operator must register this model configuration before reindexing.",
                )
            current = settings(conn, space, self.registry.default.generation.id)
            if current["version"] != command.expected_version:
                raise ServiceError(
                    409, "version_conflict", "Model settings changed; refresh before retrying."
                )
            if current["candidate_run_id"]:
                raise ServiceError(
                    409, "reindex_in_progress", "Finish or cancel the existing candidate first."
                )
            if current["active_generation_id"] == generation:
                raise ServiceError(
                    409, "model_already_active", "This embedding generation is already active."
                )
            run = uuid4()
            conn.execute(
                """INSERT INTO mnemion.reindex_runs(tenant_id,space_id,id,generation_id,
                   previous_generation_id,network_egress_approved,created_by)
                   VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                (
                    identity.tenant_id,
                    space,
                    run,
                    generation,
                    current["active_generation_id"],
                    command.approve_network_egress,
                    identity.principal_id,
                ),
            )
            conn.execute(
                """INSERT INTO mnemion.space_embedding_settings(tenant_id,space_id,active_generation_id,candidate_run_id)
                   VALUES(%s,%s,%s,%s) ON CONFLICT(tenant_id,space_id) DO UPDATE
                   SET candidate_run_id=excluded.candidate_run_id,version=mnemion.space_embedding_settings.version+1,updated_at=now()""",
                (identity.tenant_id, space, current["active_generation_id"], run),
            )
            audit(
                conn,
                identity,
                "embedding.reindex_started",
                run,
                space_id=space,
                details={
                    "generation_id": generation,
                    "network_egress_approved": command.approve_network_egress,
                },
            )
            return remember_receipt(conn, identity, space, key, digest, self._state(conn, space))

    def control(
        self,
        identity: Identity,
        space: UUID,
        run_id: UUID,
        action: str,
        version: int,
        *,
        approve_network_egress: bool = False,
    ) -> dict:
        if action not in {"pause", "resume", "retry", "cancel", "activate"}:
            raise not_found()
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 40)
            exclusive_boundary(conn, identity.tenant_id, space)
            require_space(conn, space, 40, writing=True)
            current = settings(conn, space, self.registry.default.generation.id)
            if current["version"] != version:
                raise ServiceError(
                    409, "version_conflict", "Model settings changed; refresh before retrying."
                )
            if current["candidate_run_id"] != run_id:
                raise not_found()
            run = conn.execute(
                "SELECT * FROM mnemion.reindex_runs WHERE space_id=%s AND id=%s FOR UPDATE",
                (space, run_id),
            ).fetchone()
            if (
                action in {"resume", "activate"}
                and self.registry.network_egress(run["generation_id"])
                and not run["network_egress_approved"]
            ):
                if not approve_network_egress:
                    raise ServiceError(
                        422,
                        "embedding_egress_approval_required",
                        "Reapprove this candidate endpoint after recovery before resuming or activating it.",
                    )
                conn.execute(
                    "UPDATE mnemion.reindex_runs SET network_egress_approved=true WHERE space_id=%s AND id=%s",
                    (space, run_id),
                )
            if action == "activate":
                self.registry.get(run["generation_id"])
                counts = coverage(conn, space, run["generation_id"])
                if not run["scan_complete"] or counts["revisions"] != counts["indexed_revisions"]:
                    raise ServiceError(
                        409,
                        "candidate_index_incomplete",
                        "All retained revisions must be indexed before activation.",
                    )
                conn.execute(
                    """UPDATE mnemion.space_embedding_settings SET previous_generation_id=active_generation_id,
                       active_generation_id=%s,candidate_run_id=NULL,inference_paused=false WHERE space_id=%s""",
                    (run["generation_id"], space),
                )
                conn.execute(
                    "UPDATE mnemion.reindex_runs SET state='activated',updated_at=now() WHERE space_id=%s AND id=%s",
                    (space, run_id),
                )
                # Old vectors remain for a subsequent controlled rollback. Old
                # unfinished jobs no longer spend inference on an inactive model.
                self._cancel_jobs(conn, space, generation=current["active_generation_id"])
            elif action == "cancel":
                self._cancel_jobs(conn, space, run=run_id)
                conn.execute(
                    "UPDATE mnemion.reindex_runs SET state='cancelled',lease_id=NULL,lease_until=NULL,updated_at=now() WHERE space_id=%s AND id=%s",
                    (space, run_id),
                )
                conn.execute(
                    "UPDATE mnemion.space_embedding_settings SET candidate_run_id=NULL WHERE space_id=%s",
                    (space,),
                )
            elif action == "retry":
                rows = conn.execute(
                    """UPDATE mnemion.jobs SET state='pending',attempts=0,available_at=now(),error_code=NULL
                       WHERE space_id=%s AND reindex_run_id=%s AND state='failed' RETURNING operation_id""",
                    (space, run_id),
                ).fetchall()
                for row in rows:
                    conn.execute(
                        "UPDATE mnemion.operations SET state='accepted',error_code=NULL,updated_at=now() WHERE id=%s",
                        (row["operation_id"],),
                    )
            else:
                if action == "resume":
                    self.registry.get(run["generation_id"])
                conn.execute(
                    "UPDATE mnemion.reindex_runs SET state=%s,updated_at=now() WHERE space_id=%s AND id=%s",
                    ("paused" if action == "pause" else "running", space, run_id),
                )
            conn.execute(
                "UPDATE mnemion.space_embedding_settings SET version=version+1,updated_at=now() WHERE space_id=%s",
                (space,),
            )
            audit(
                conn,
                identity,
                "embedding." + action,
                run_id,
                space_id=space,
                details={"generation_id": run["generation_id"]},
            )
            return self._state(conn, space)

    def resume_processing(self, identity: Identity, space: UUID, command) -> dict:
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 40)
            exclusive_boundary(conn, identity.tenant_id, space)
            require_space(conn, space, 40, writing=True)
            current = settings(conn, space, self.registry.default.generation.id)
            if current["version"] != command.expected_version:
                raise ServiceError(
                    409, "version_conflict", "Model settings changed; refresh before retrying."
                )
            if (
                self.registry.network_egress(current["active_generation_id"])
                and not command.approve_network_egress
            ):
                raise ServiceError(
                    422,
                    "embedding_egress_approval_required",
                    "Reapprove sending this space's text to its active endpoint after recovery.",
                )
            if current.get("inference_paused"):
                conn.execute(
                    "UPDATE mnemion.space_embedding_settings SET inference_paused=false,version=version+1,updated_at=now() WHERE space_id=%s",
                    (space,),
                )
                audit(
                    conn,
                    identity,
                    "embedding.processing_resumed",
                    space,
                    space_id=space,
                    details={
                        "generation_id": current["active_generation_id"],
                        "network_egress_approved": command.approve_network_egress,
                    },
                )
            return self._state(conn, space)

    @staticmethod
    def _cancel_jobs(conn, space, *, generation=None, run=None):
        rows = conn.execute(
            """UPDATE mnemion.jobs SET state='cancelled',lease_id=NULL,lease_until=NULL
               WHERE space_id=%s AND kind='embed' AND state IN ('pending','leased','failed')
                 AND ((%s::text IS NOT NULL AND generation_id=%s) OR (%s::uuid IS NOT NULL AND reindex_run_id=%s))
               RETURNING operation_id""",
            (space, generation, generation, run, run),
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE mnemion.operations SET state='cancelled',updated_at=now() WHERE id=%s",
                (row["operation_id"],),
            )


class ReindexBackfill:
    def __init__(self, database: Database, registry: ModelRegistry):
        if not database.worker:
            raise ValueError("Backfill requires the separate worker login")
        self.db, self.registry = database, registry

    def run_once(self, *, batch_size=100) -> bool:
        if type(batch_size) is not int or not 1 <= batch_size <= 500:
            raise ValueError("Backfill batches must contain 1–500 revisions")
        with self.db.pool.connection() as conn:
            job = conn.execute(
                "SELECT * FROM mnemion.claim_reindex(%s,%s::text[])",
                (uuid4(), self.registry.generation_ids),
            ).fetchone()
        if not job:
            return False
        with self.db.worker_transaction(job["tenant_id"]) as conn:
            shared_boundary(conn, job["tenant_id"], job["space_id"])
            if not conn.execute(
                "SELECT mnemion.embedding_source_current(%s) AS current", (job["space_id"],)
            ).fetchone()["current"]:
                return False
            run = conn.execute(
                """SELECT * FROM mnemion.reindex_runs WHERE space_id=%s AND id=%s
                   AND state='running' AND lease_id=%s AND lease_until>now() FOR UPDATE""",
                (job["space_id"], job["id"], job["lease_id"]),
            ).fetchone()
            if not run:
                return False
            pending = conn.execute(
                """SELECT id FROM mnemion.jobs WHERE space_id=%s AND reindex_run_id=%s
                   AND state IN ('pending','leased','failed') LIMIT 1000""",
                (run["space_id"], run["id"]),
            ).fetchall()
            if len(pending) >= 1000:
                conn.execute(
                    "UPDATE mnemion.reindex_runs SET lease_id=NULL,lease_until=NULL,updated_at=now() WHERE space_id=%s AND id=%s",
                    (run["space_id"], run["id"]),
                )
                return False
            rows = conn.execute(
                "SELECT r.id,r.memory_id "
                + REVISIONS
                + " AND r.id>%(cursor)s ORDER BY r.id LIMIT %(limit)s",
                {"space": run["space_id"], "cursor": run["cursor_id"], "limit": batch_size},
            ).fetchall()
            for row in rows:
                enqueue_candidate(
                    conn,
                    tenant=run["tenant_id"],
                    space=run["space_id"],
                    revision=row["id"],
                    memory=row["memory_id"],
                    run=run["id"],
                    generation=run["generation_id"],
                    created_by=run["created_by"],
                )
            conn.execute(
                """UPDATE mnemion.reindex_runs SET cursor_id=%s,scan_complete=%s,
                   lease_id=NULL,lease_until=NULL,updated_at=now() WHERE space_id=%s AND id=%s""",
                (
                    rows[-1]["id"] if rows else run["cursor_id"],
                    len(rows) < batch_size,
                    run["space_id"],
                    run["id"],
                ),
            )
        return True
