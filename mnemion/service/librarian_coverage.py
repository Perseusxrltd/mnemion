"""One consistent, scoped coverage snapshot without reading memory text."""

from .models import json_value


def snapshot(conn, space, settings):
    fingerprint = settings["profile_fingerprint"] if settings else None
    row = conn.execute(
        """WITH active AS MATERIALIZED (
              SELECT tenant_id,space_id,id,version,review_state,updated_at
              FROM mnemion.memories WHERE space_id=%(space)s AND deleted_at IS NULL
            ), coverage AS (
              SELECT kind.mode,count(m.id) AS eligible,
                count(m.id) FILTER(WHERE o.memory_version=m.version AND o.outcome='completed') AS checked,
                count(m.id) FILTER(WHERE o.memory_version=m.version AND o.outcome='skipped') AS skipped,
                count(m.id) FILTER(WHERE o.memory_version=m.version AND o.outcome='attempted') AS attempted,
                count(m.id) FILTER(WHERE o.memory_version IS DISTINCT FROM m.version) AS pending,
                count(m.id) FILTER(WHERE o.memory_id IS NULL) AS unseen,
                count(m.id) FILTER(WHERE o.memory_id IS NOT NULL AND o.memory_version<>m.version) AS changed,
                min(m.updated_at) FILTER(WHERE o.memory_version IS DISTINCT FROM m.version) AS oldest_pending_at,
                max(o.checked_at) AS last_observed_at
              FROM (VALUES ('organize'),('review')) AS kind(mode)
              LEFT JOIN active m ON m.review_state='ordinary'
              LEFT JOIN mnemion.librarian_observations o
                ON o.tenant_id=m.tenant_id AND o.space_id=m.space_id AND o.memory_id=m.id
                  AND o.profile_fingerprint=%(fingerprint)s AND o.mode=kind.mode
              GROUP BY kind.mode
            ), recent AS (
              SELECT 30 AS window_days,count(*) AS runs,
                count(*) FILTER(WHERE state IN ('queued','running')) AS active_runs,
                count(*) FILTER(WHERE state='failed') AS failed_runs,
                count(*) FILTER(WHERE state='cancelled') AS cancelled_runs,
                coalesce(sum(calls_reserved),0) AS calls_reserved,
                coalesce(sum(calls_completed),0) AS calls_completed,
                coalesce(sum(request_bytes),0) AS request_bytes,
                coalesce(sum(response_bytes),0) AS response_bytes,
                coalesce(sum(latency_ms),0) AS provider_latency_ms
              FROM mnemion.librarian_runs
              WHERE space_id=%(space)s AND profile_fingerprint=%(fingerprint)s
                AND created_at>=now()-interval '30 days'
            )
            SELECT count(*) AS active_memories,
              count(*) FILTER(WHERE review_state<>'ordinary') AS excluded_memories,
              (SELECT jsonb_agg(to_jsonb(c) ORDER BY mode) FROM coverage c) AS modes,
              (SELECT to_jsonb(r) FROM recent r) AS recent,now() AS observed_at
            FROM active""",
        {"space": space, "fingerprint": fingerprint},
    ).fetchone()
    return json_value(
        {
            "space_id": space,
            "profile_id": settings["profile_id"] if settings else None,
            "profile_fingerprint": fingerprint,
            **row,
        }
    )
