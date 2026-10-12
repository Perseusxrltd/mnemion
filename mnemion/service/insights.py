"""Permission-scoped diagnostics, bounded history and explicit metric semantics."""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from .insights_models import Insights as Insights, RuntimeInsights as RuntimeInsights
from .db import Database, Identity, require_administrator, require_space
from .embeddings import Embedder
from .errors import ServiceError
from .models import json_value
from .model_state import active_generations
from .telemetry import COUNTERS, LATENCY_BOUNDS_MS, Telemetry, percentile_bound


AGGREGATES = ",".join(
    [
        "sum(calls)::bigint AS calls",
        "sum(failures)::bigint AS failures",
        "sum(duration_ms) AS duration_ms",
        "max(duration_max_ms) AS max_ms",
        "mnemion.sum_histogram(latency_histogram) AS latency_histogram",
        *(f"sum({field})::bigint AS {field}" for field in COUNTERS),
    ]
)


def metric_values(row: dict) -> dict:
    row = dict(row)
    calls = row["calls"]
    row["mean_ms"] = round(row["duration_ms"] / calls, 3) if calls else None
    for name, quantile in (("p50_upper_ms", 0.5), ("p95_upper_ms", 0.95), ("p99_upper_ms", 0.99)):
        row[name] = percentile_bound(row["latency_histogram"], quantile)
    return row


class InsightsService:
    def __init__(self, database: Database, embedder: Embedder, *, cache_seconds: int = 30):
        self.db, self.embedder = database, embedder
        self.cache_seconds = cache_seconds
        self._cache: OrderedDict[tuple, tuple[float, dict]] = OrderedDict()
        self._lock = threading.Lock()
        self._capacity = threading.BoundedSemaphore(2)

    def read(
        self,
        identity: Identity,
        space: UUID,
        *,
        hours: int = 24,
        origin: Literal["all", "interactive", "background", "evaluation"] = "all",
    ) -> dict:
        if not 1 <= hours <= 744 or origin not in {
            "all",
            "interactive",
            "background",
            "evaluation",
        }:
            raise ServiceError(422, "invalid_window", "Choose a time window of 1 to 744 hours.")
        if not self._capacity.acquire(blocking=False):
            raise ServiceError(
                503, "diagnostics_busy", "Diagnostics capacity is busy; retry shortly."
            )
        try:
            with self.db.transaction(identity) as conn:
                require_space(conn, space, 30)
                conn.execute("SET LOCAL statement_timeout='5000'")
                conn.execute("SET LOCAL lock_timeout='250'")
                now = datetime.now(timezone.utc)
                since = (now - timedelta(hours=hours)).replace(second=0, microsecond=0)
                # At most 372 points per stage, regardless of traffic volume.
                bucket = max(60, math.ceil(hours * 3600 / 372 / 60) * 60)
                snapshot = self._snapshot(conn, identity, space)
                params = {
                    "space": space,
                    "since": since,
                    "until": now,
                    "origin": origin,
                    "bucket": bucket,
                }
                predicate = "space_id=%(space)s AND bucket>=%(since)s AND bucket<=%(until)s AND (%(origin)s='all' OR origin=%(origin)s)"
                groups = conn.execute(
                    f"""SELECT stage,mode,origin,generation_id,{AGGREGATES}
                        FROM mnemion.metric_buckets WHERE {predicate}
                        GROUP BY stage,mode,origin,generation_id
                        ORDER BY stage,mode,origin,generation_id LIMIT 257""",
                    params,
                ).fetchall()
                series = conn.execute(
                    f"""SELECT date_bin(make_interval(secs=>%(bucket)s),bucket,'2000-01-01'::timestamptz) AS at,
                        stage,{AGGREGATES} FROM mnemion.metric_buckets WHERE {predicate}
                        GROUP BY at,stage ORDER BY at,stage LIMIT 2245""",
                    params,
                ).fetchall()
                coverage = conn.execute(
                    f"""SELECT coalesce(sum(calls),0)::bigint AS recorded_calls,
                        min(bucket) AS first_sample_at,max(bucket) AS last_sample_at
                        FROM mnemion.metric_buckets WHERE {predicate}""",
                    params,
                ).fetchone()
                changes = conn.execute(
                    """SELECT date_bin(make_interval(secs=>%(bucket)s),created_at,'2000-01-01'::timestamptz) AS at,
                       action,count(*) AS count FROM mnemion.audit_events
                       WHERE space_id=%(space)s AND created_at>=%(since)s AND created_at<=%(until)s
                       AND action IN ('memory.created','memory.revised','memory.reviewed','memory.deleted')
                       GROUP BY at,action ORDER BY at,action LIMIT 1497""",
                    params,
                ).fetchall()
                latency = conn.execute(
                    """SELECT count(*) AS completed_operations,
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM updated_at-created_at)) AS p50_seconds,
                       percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM updated_at-created_at)) AS p95_seconds,
                       max(extract(epoch FROM updated_at-created_at))::double precision AS max_seconds
                       FROM mnemion.operations WHERE space_id=%(space)s AND state='ready'
                       AND kind IN ('ingest','revise','reindex')
                       AND updated_at>=%(since)s AND updated_at<=%(until)s""",
                    params,
                ).fetchone()
                # Authorization is current even when the expensive content counts
                # came from this caller's short-lived numeric snapshot cache.
                require_space(conn, space, 30)
            return json_value(
                {
                    "space_id": space,
                    "observed_at": now,
                    "snapshot_cache_seconds": self.cache_seconds,
                    "generation_id": snapshot["generation_id"],
                    **snapshot,
                    "changes": changes,
                    "queue_latency": latency,
                    "metrics": {
                        "since": since,
                        "until": now,
                        "bucket_seconds": bucket,
                        "retention_days": 31,
                        "origin": origin,
                        "histogram_upper_bounds_ms": [*LATENCY_BOUNDS_MS, None],
                        "groups": [metric_values(row) for row in groups[:256]],
                        "series": [metric_values(row) for row in series[:2244]],
                        "truncated": len(groups) > 256 or len(series) > 2244,
                        **coverage,
                    },
                    "notices": [
                        "Metrics are best-effort minute aggregates; gaps are not measured zero traffic.",
                        "Latency percentiles are histogram upper bounds. Queue-to-ready percentiles are exact for completed operations in this window.",
                        "Cross-space requests are excluded from an individual space's traffic.",
                        "Byte counters describe UTF-8 query/context text or float32 vector payloads, not measured network or DRAM bandwidth.",
                        "Storage counts are logical content/vector values, excluding database indexes, backups and filesystem overhead.",
                    ],
                }
            )
        finally:
            self._capacity.release()

    def _snapshot(self, conn, identity: Identity, space: UUID) -> dict:
        generation = active_generations(conn, [space], self.embedder.generation.id)[space]
        key = (identity, space, generation)
        with self._lock:
            previous = self._cache.get(key)
            if previous and time.monotonic() - previous[0] < self.cache_seconds:
                self._cache.move_to_end(key)
                return previous[1]
        current = """FROM mnemion.memories m JOIN mnemion.memory_revisions r
            ON r.tenant_id=m.tenant_id AND r.space_id=m.space_id AND r.id=m.current_revision_id
            WHERE m.space_id=%(space)s AND m.deleted_at IS NULL"""
        params = {"space": space, "generation": generation}
        eligible = """m.review_state='ordinary' AND r.claim_status IN ('observed','verified','contested')
            AND (r.valid_from IS NULL OR r.valid_from<=now())
            AND (r.valid_to IS NULL OR r.valid_to>now())
            AND EXISTS(SELECT FROM mnemion.source_revisions sr JOIN mnemion.sources s
               ON s.tenant_id=sr.tenant_id AND s.space_id=sr.space_id AND s.id=sr.source_id
               WHERE sr.tenant_id=r.tenant_id AND sr.space_id=r.space_id
                 AND sr.id=r.source_revision_id AND s.deleted_at IS NULL)"""
        counts = conn.execute(
            f"""SELECT count(*) AS active,
                count(*) FILTER(WHERE m.review_state='ordinary') AS ordinary,
                count(*) FILTER(WHERE m.review_state='quarantined') AS quarantined,
                count(*) FILTER(WHERE {eligible}) AS eligible,
                count(*) FILTER(WHERE {eligible} AND EXISTS(
                  SELECT FROM mnemion.embeddings e WHERE e.tenant_id=r.tenant_id AND e.space_id=r.space_id
                    AND e.revision_id=r.id AND e.generation_id=%(generation)s)) AS indexed,
                count(*) FILTER(WHERE r.valid_to<=now()) AS expired,
                count(*) FILTER(WHERE r.valid_from>now()) AS future,
                coalesce(sum(octet_length(r.content)),0)::bigint AS content_bytes
                {current}""",
            params,
        ).fetchone()
        distributions = {}
        groupings = {
            "kind": "r.kind",
            "claim": "r.claim_status",
            "age": """CASE WHEN m.updated_at>now()-interval '1 day' THEN 'under_1_day'
                WHEN m.updated_at>now()-interval '7 days' THEN '1_to_7_days'
                WHEN m.updated_at>now()-interval '30 days' THEN '7_to_30_days'
                WHEN m.updated_at>now()-interval '90 days' THEN '30_to_90_days' ELSE 'over_90_days' END""",
            "size": """CASE WHEN octet_length(r.content)<1024 THEN 'under_1_KiB'
                WHEN octet_length(r.content)<4096 THEN '1_to_4_KiB'
                WHEN octet_length(r.content)<16384 THEN '4_to_16_KiB' ELSE 'over_16_KiB' END""",
        }
        for name, expression in groupings.items():
            distributions[name] = conn.execute(
                f"SELECT {expression} AS label,count(*) AS count {current} GROUP BY label ORDER BY label",
                params,
            ).fetchall()
        duplicates = conn.execute(
            f"""SELECT coalesce(sum(n-1),0)::bigint AS count FROM (
                SELECT count(*) n {current} GROUP BY r.content_hash HAVING count(*)>1) d""",
            params,
        ).fetchone()["count"]
        storage = conn.execute(
            """SELECT
              (SELECT count(*) FROM mnemion.memories WHERE space_id=%(space)s AND deleted_at IS NOT NULL) AS deleted,
              (SELECT count(*) FROM mnemion.memory_revisions WHERE space_id=%(space)s) AS revisions,
              (SELECT coalesce(sum(octet_length(content)),0)::bigint FROM mnemion.memory_revisions WHERE space_id=%(space)s) AS revision_bytes,
              (SELECT count(*) FROM mnemion.sources WHERE space_id=%(space)s AND deleted_at IS NULL) AS sources,
              (SELECT count(*) FROM mnemion.source_revisions WHERE space_id=%(space)s) AS source_revisions,
              (SELECT coalesce(sum(octet_length(content)),0)::bigint FROM mnemion.source_revisions WHERE space_id=%(space)s) AS source_bytes,
              (SELECT coalesce(sum(octet_length(content)),0)::bigint FROM mnemion.source_attachments WHERE space_id=%(space)s) AS attachment_bytes""",
            params,
        ).fetchone()
        queue = conn.execute(
            """SELECT state,count(*) AS count,count(*) FILTER(WHERE attempts>1) AS retried,
                min(created_at) AS oldest_at,
                extract(epoch FROM now()-min(created_at))::double precision AS oldest_age_seconds
                FROM mnemion.jobs WHERE space_id=%s GROUP BY state ORDER BY state""",
            (space,),
        ).fetchall()
        generations = conn.execute(
            """SELECT g.id,g.model,g.dimensions,count(e.*) AS chunks,
                count(DISTINCT e.revision_id) AS revisions,
                coalesce(sum(pg_column_size(e.embedding)),0)::bigint AS vector_bytes
                FROM mnemion.embedding_generations g LEFT JOIN mnemion.embeddings e
                  ON e.generation_id=g.id AND e.space_id=%s
                WHERE g.id=%s OR e.generation_id IS NOT NULL
                GROUP BY g.id,g.model,g.dimensions ORDER BY g.id LIMIT 64""",
            (space, generation),
        ).fetchall()
        for row in generations:
            row["active"] = row["id"] == generation
        managed = conn.execute("SELECT mnemion.managed_scope(%s) AS value", (space,)).fetchone()[
            "value"
        ]
        source = conn.execute(
            """SELECT c.provider,c.id AS connector_id,s.observed_at,s.access_valid_until,
                s.completed_at,s.operator_paused FROM mnemion.connector_scopes s
                JOIN mnemion.connectors c ON c.tenant_id=s.tenant_id AND c.id=s.connector_id
                WHERE s.space_id=%s""",
            (space,),
        ).fetchone()
        source_health = {
            "managed": managed,
            "operator_details_available": bool(source),
            **(source or {}),
            "items": [],
            "runs": [],
        }
        if managed:
            source_health["items"] = conn.execute(
                "SELECT state AS label,count(*) AS count FROM mnemion.connector_items WHERE space_id=%s GROUP BY state ORDER BY state",
                (space,),
            ).fetchall()
            if source:
                source_health["runs"] = conn.execute(
                    "SELECT state AS label,count(*) AS count FROM mnemion.connector_runs WHERE space_id=%s GROUP BY state ORDER BY state",
                    (space,),
                ).fetchall()
        result = {
            "generation_id": generation,
            "snapshot_at": datetime.now(timezone.utc),
            "memory": {
                **counts,
                **storage,
                "duplicate_copies": duplicates,
                "distributions": distributions,
            },
            "queue": queue,
            "generations": generations,
            "source": source_health,
        }
        with self._lock:
            self._cache[key] = (time.monotonic(), result)
            self._cache.move_to_end(key)
            while len(self._cache) > 64:
                self._cache.popitem(last=False)
        return result


def runtime_insights(
    database: Database,
    identity: Identity,
    embedder: Embedder,
    telemetry: Telemetry,
    *,
    registry=None,
) -> dict:
    with database.transaction(identity) as conn:
        require_administrator(conn)
    from .resources import process_resources

    gate = getattr(embedder, "_inference_gate", None)
    return {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "scope": "this_api_process",
        "telemetry": telemetry.snapshot(),
        "inference": gate.snapshot() if gate else None,
        "model_loaded": getattr(embedder, "_model", None) is not None
        if hasattr(embedder, "_model")
        else None,
        "model": embedder.generation.model,
        "generation_id": embedder.generation.id,
        "dimensions": embedder.generation.dimensions,
        "configuration": embedder.generation.configuration,
        "models": [
            {
                "generation_id": model.generation.id,
                "model": model.generation.model,
                "model_loaded": getattr(model, "_model", None) is not None
                if hasattr(model, "_model")
                else None,
                "configuration": model.generation.configuration,
                "provider": model.snapshot() if hasattr(model, "snapshot") else None,
            }
            for model in (registry.get(generation) for generation in registry.generation_ids)
        ]
        if registry
        else [],
        "pool": database.pool.get_stats(),
        "resources": process_resources(),
        "memory_budget": registry.memory_budget.snapshot()
        if registry and registry.memory_budget
        else None,
        "model_cache": registry.cache_status() if registry else None,
        "notices": [
            "Process counters restart with this API instance and may include several tenants. No query or source text is collected.",
            "API resource gauges do not measure a separate worker, provider, database or the user's client.",
            "Provider charges and physical memory bandwidth are unavailable unless separately instrumented.",
        ],
    }
