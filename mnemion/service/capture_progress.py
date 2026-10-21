"""Bounded index observations for an active, currently authorized capture device.

Pages inspect current revisions and the named active embedding generation. A
multi-page sweep is a sequence of observations, never an atomic history census.
No memory content, model invocation or indexing work is returned or performed.
"""

from uuid import UUID

from psycopg.errors import LockNotAvailable, QueryCanceled

from ..capture_coverage import IndexCounts, utc_now
from .db import require_space
from .errors import ServiceError
from .model_state import settings


class CaptureProgress:
    def index_progress(self, identity, grant_id, *, after=None, limit=1000):
        try:
            return self._index_progress(identity, grant_id, after=after, limit=limit)
        except (LockNotAvailable, QueryCanceled):
            raise ServiceError(
                503,
                "capture_index_busy",
                "Index observations are busy; retain the last saved observation.",
            ) from None

    def _index_progress(self, identity, grant_id, *, after=None, limit=1000):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("Choose an index observation page between 1 and 1,000 events")
        with self.db.transaction(identity, timeout=1) as conn:
            conn.execute("SET LOCAL statement_timeout='2000ms'")
            conn.execute("SET LOCAL lock_timeout='500ms'")
            grant = self._grant(conn, identity, grant_id)
            conn.execute(
                "SELECT pg_advisory_xact_lock_shared(hashtextextended(%s,0))",
                (f"capture:{grant['source_id']}",),
            )
            conn.execute(
                "SELECT mnemion.lock_capture_authority(%s,%s)", (grant_id, identity.key_id)
            )
            self.db._check_identity(conn, identity)
            grant = self._grant(conn, identity, grant_id)
            space = UUID(grant["space_id"])
            require_space(conn, space, 20)
            model = settings(conn, space, self.memory.generation.id)
            generation = model["active_generation_id"]
            rows = conn.execute(
                """WITH selected AS MATERIALIZED (
                     SELECT e.tenant_id,e.event_id,e.space_id,e.memory_id FROM mnemion.capture_events e
                     WHERE e.tenant_id=mnemion.tenant() AND e.source_id=%(source)s
                       AND (%(after)s::text IS NULL OR e.event_id>%(after)s)
                     ORDER BY e.event_id LIMIT %(limit)s
                   )
                   SELECT e.event_id,
                     CASE
                       WHEN e.memory_id IS NULL OR m.deleted_at IS NOT NULL THEN 'forgotten'
                       WHEN m.id IS NULL OR r.id IS NULL THEN 'unknown'
                       WHEN m.review_state<>'ordinary' THEN 'withheld'
                       WHEN visible.present IS NULL THEN 'withheld'
                       WHEN EXISTS(SELECT FROM mnemion.embeddings v
                         WHERE v.tenant_id=e.tenant_id AND v.space_id=e.space_id
                           AND v.revision_id=r.id AND v.generation_id=%(generation)s) THEN 'vector_indexed'
                       WHEN EXISTS(SELECT FROM mnemion.jobs j
                         WHERE j.tenant_id=e.tenant_id AND j.space_id=e.space_id
                           AND j.revision_id=r.id AND j.generation_id=%(generation)s AND j.state='failed')
                         AND NOT EXISTS(SELECT FROM mnemion.jobs j
                         WHERE j.tenant_id=e.tenant_id AND j.space_id=e.space_id
                           AND j.revision_id=r.id AND j.generation_id=%(generation)s AND j.state IN ('pending','leased')) THEN 'failed'
                       ELSE 'waiting'
                     END AS state
                   FROM selected e
                     LEFT JOIN mnemion.memories m ON m.tenant_id=e.tenant_id
                       AND m.space_id=e.space_id AND m.id=e.memory_id
                     LEFT JOIN mnemion.memory_revisions r ON r.tenant_id=e.tenant_id
                       AND r.space_id=e.space_id AND r.id=m.current_revision_id
                     LEFT JOIN LATERAL (
                       SELECT 1 AS present FROM mnemion.source_revisions sr
                         JOIN mnemion.sources s ON s.tenant_id=sr.tenant_id
                           AND s.space_id=sr.space_id AND s.id=sr.source_id
                       WHERE sr.tenant_id=e.tenant_id AND sr.space_id=e.space_id
                         AND sr.id=r.source_revision_id AND s.deleted_at IS NULL LIMIT 1
                     ) visible ON true
                   ORDER BY e.event_id""",
                {
                    "source": UUID(grant["source_id"]),
                    "after": after,
                    "limit": limit + 1,
                    "generation": generation,
                },
            ).fetchall()
            more, selected = len(rows) > limit, rows[:limit]
            counts = IndexCounts().model_dump()
            for row in selected:
                counts["events"] += 1
                counts[row["state"]] += 1
                counts["lexical_indexed"] += row["state"] in {"vector_indexed", "waiting", "failed"}
            return {
                "source_id": grant["source_id"],
                "grant_id": grant["grant_id"],
                "generation_id": generation,
                "inference_paused": bool(model.get("inference_paused", False)),
                "observed_at": utc_now(),
                "after": after,
                "counts": IndexCounts.model_validate(counts).model_dump(),
                "next_cursor": selected[-1]["event_id"] if more else None,
            }
