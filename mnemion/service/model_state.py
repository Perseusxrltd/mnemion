"""Transaction-scoped model routing and candidate jobs; no provider calls here."""

from uuid import uuid4

from .db import require_space
from .errors import ServiceError


def settings(conn, space, default_generation: str) -> dict:
    row = conn.execute(
        """SELECT s.*,r.generation_id AS candidate_generation_id,r.state AS candidate_state,
                  r.created_by AS candidate_created_by,r.network_egress_approved AS candidate_network_egress_approved
           FROM mnemion.space_embedding_settings s LEFT JOIN mnemion.reindex_runs r
             ON r.tenant_id=s.tenant_id AND r.space_id=s.space_id AND r.id=s.candidate_run_id
           WHERE s.space_id=%s""",
        (space,),
    ).fetchone()
    return row or {
        "space_id": space,
        "active_generation_id": default_generation,
        "candidate_run_id": None,
        "candidate_generation_id": None,
        "version": 0,
    }


def active_generations(conn, spaces, default_generation: str) -> dict:
    result = {space: default_generation for space in spaces}
    for row in conn.execute(
        "SELECT space_id,active_generation_id FROM mnemion.space_embedding_settings WHERE space_id=ANY(%s::uuid[])",
        (spaces,),
    ):
        result[row["space_id"]] = row["active_generation_id"]
    return result


def selected_generations(
    conn, spaces, default_generation: str, override: str | None = None
) -> dict:
    if override is None:
        return active_generations(conn, spaces, default_generation)
    result = {}
    for space in spaces:
        require_space(conn, space, 30)
        current = settings(conn, space, default_generation)
        if override not in {current["active_generation_id"], current["candidate_generation_id"]}:
            raise ServiceError(
                409,
                "generation_changed",
                "This generation is no longer an active or approved candidate index for the space.",
            )
        result[space] = override
    return result


def enqueue_candidate(
    conn, *, tenant, space, revision, memory, run, generation, created_by
) -> bool:
    conn.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"reindex:{run}:{revision}",)
    )
    if conn.execute(
        """SELECT 1 FROM mnemion.jobs WHERE space_id=%s AND reindex_run_id=%s AND revision_id=%s
           UNION ALL SELECT 1 FROM mnemion.embeddings
             WHERE space_id=%s AND generation_id=%s AND revision_id=%s LIMIT 1""",
        (space, run, revision, space, generation, revision),
    ).fetchone():
        return False
    operation = uuid4()
    conn.execute(
        """INSERT INTO mnemion.operations(tenant_id,space_id,id,memory_id,revision_id,kind,created_by)
           VALUES(%s,%s,%s,%s,%s,'reindex',%s)""",
        (tenant, space, operation, memory, revision, created_by),
    )
    conn.execute(
        """INSERT INTO mnemion.jobs(tenant_id,space_id,id,operation_id,revision_id,generation_id,kind,reindex_run_id)
           VALUES(%s,%s,%s,%s,%s,%s,'embed',%s)""",
        (tenant, space, uuid4(), operation, revision, generation, run),
    )
    return True


def job_policy(conn, job, default_generation: str) -> str:
    state = settings(conn, job["space_id"], default_generation)
    if job.get("reindex_run_id"):
        if state["candidate_run_id"] != job["reindex_run_id"]:
            return "obsolete"
        return "paused" if state["candidate_state"] == "paused" else "allowed"
    if state["active_generation_id"] != job["generation_id"]:
        return "obsolete"
    return "blocked" if state.get("inference_paused") else "allowed"
