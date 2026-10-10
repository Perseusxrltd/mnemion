"""Scoped lexical/vector fusion, live citations, and bounded context assembly."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from .db import Database, Identity, require_space, resolve_spaces
from .embeddings import Embedder, vector_literal
from .errors import ServiceError
from .models import ContextInput, RecallInput, json_value
from .repository import hydrate, memory_row
from .telemetry import Telemetry

logger = logging.getLogger(__name__)

# Materialize the authorized candidates before computing distance or ranks.
# The initial engine uses exact vector distance; no post-hoc tenant filtering
# or approximate-index recall claims are hidden behind this query.
# Keep source visibility as a dependent point lookup. Its LIMIT 1 prevents a
# fresh database's sparse planner statistics from multiplying all source rows
# in a space before matching the revision ID; RLS still applies to both tables.
ELIGIBLE = """
WITH eligible AS MATERIALIZED (
    SELECT m.id AS memory_id, m.space_id, r.id AS revision_id
    FROM mnemion.memories m
    JOIN LATERAL (
        SELECT rr.* FROM mnemion.memory_revisions rr
        WHERE rr.tenant_id=m.tenant_id AND rr.space_id=m.space_id AND rr.memory_id=m.id
          AND ((%(known_at)s::timestamptz IS NULL AND rr.id=m.current_revision_id)
            OR (%(known_at)s::timestamptz IS NOT NULL AND rr.recorded_at<=%(known_at)s::timestamptz))
        ORDER BY rr.recorded_at DESC, rr.version DESC LIMIT 1
    ) r ON true
    JOIN LATERAL (
        SELECT 1 FROM mnemion.source_revisions sr
        JOIN mnemion.sources s ON s.tenant_id=sr.tenant_id AND s.space_id=sr.space_id AND s.id=sr.source_id
        WHERE sr.tenant_id=m.tenant_id AND sr.space_id=m.space_id AND sr.id=r.source_revision_id
          AND s.deleted_at IS NULL
        LIMIT 1
    ) source_visible ON true
    WHERE m.tenant_id=mnemion.tenant() AND m.space_id=ANY(%(spaces)s::uuid[])
      AND m.deleted_at IS NULL AND m.review_state='ordinary'
      AND (%(subject)s::text IS NULL OR r.subject=%(subject)s)
      AND (%(kinds)s::text[] IS NULL OR r.kind=ANY(%(kinds)s::text[]))
      AND r.metadata @> %(metadata)s::jsonb
      AND r.claim_status IN ('observed', 'verified', 'contested')
      AND (r.claim_status<>'contested' OR %(contested)s)
      AND (r.valid_from IS NULL OR r.valid_from<=coalesce(%(valid_at)s::timestamptz, now()))
      AND (r.valid_to IS NULL OR r.valid_to>coalesce(%(valid_at)s::timestamptz, now()))
)
"""


class RetrievalService:
    def __init__(self, database: Database, embedder: Embedder, telemetry: Telemetry | None = None):
        self.db = database
        self.embedder = embedder
        self.telemetry = telemetry

    def recall(
        self, identity: Identity, command: RecallInput, *, origin: str = "interactive"
    ) -> dict:
        return self._measured(identity, command, "recall", origin)

    def context(
        self, identity: Identity, command: ContextInput, *, origin: str = "interactive"
    ) -> dict:
        return self._measured(identity, command, "context", origin)

    def _measured(self, identity, command, stage, origin):
        started, result, failed, permitted = time.monotonic(), {}, False, True
        try:
            result = (self._recall if stage == "recall" else self._context)(identity, command)
            return result
        except Exception as exc:
            failed = True
            if isinstance(exc, ServiceError) and exc.status in (401, 403, 404):
                permitted = False
            raise
        finally:
            if self.telemetry and permitted:
                try:
                    warnings = result.get("warnings", [])
                    text = (
                        result.get("text", "")
                        if stage == "context"
                        else "".join(hit["text"] for hit in result.get("hits", []))
                    )
                    self.telemetry.record(
                        identity,
                        command.space_ids[0] if len(command.space_ids) == 1 else None,
                        stage=stage,
                        mode=command.mode,
                        origin=origin,
                        generation=self.embedder.generation.id,
                        failed=failed,
                        duration_ms=(time.monotonic() - started) * 1000,
                        input_bytes=len(command.query.encode("utf-8")),
                        output_bytes=len(text.encode("utf-8")),
                        output_tokens=result.get("token_count", 0),
                        records=len(result.get("hits", result.get("citations", []))),
                        empty_results=int(
                            not failed and not result.get("hits", result.get("citations", []))
                        ),
                        fallbacks=int("semantic_unavailable_lexical_only" in warnings),
                        incomplete_index=int("semantic_index_incomplete" in warnings),
                    )
                except Exception:
                    logger.warning("Retrieval diagnostic sample was not recorded")

    def _recall(self, identity: Identity, command: RecallInput) -> dict:
        started = time.monotonic()
        with self.db.transaction(identity) as conn:
            resolve_spaces(conn, command)
        warnings = []
        vector = None
        if command.mode != "lexical":
            try:
                vector = vector_literal(
                    self.embedder.query(command.query), self.embedder.generation.dimensions
                )
            except ServiceError:
                raise
            except Exception as exc:
                logger.warning("Query embedding unavailable (%s)", type(exc).__name__)
                if command.mode == "semantic":
                    raise ServiceError(
                        503, "embedding_unavailable", "Semantic search is temporarily unavailable."
                    ) from None
                warnings.append("semantic_unavailable_lexical_only")
        params = {
            "spaces": command.space_ids,
            "subject": command.subject,
            "kinds": command.kinds,
            "known_at": command.known_at,
            "valid_at": command.valid_at,
            "contested": command.include_contested,
            "query": command.query,
            "limit": min(250, max(30, command.limit * 5)),
            "generation": self.embedder.generation.id,
            "vector": vector,
            "metadata": Jsonb(command.metadata_filter),
        }
        with self.db.transaction(identity) as conn:
            # Recheck after model inference, including revoked keys and grants.
            params["spaces"] = resolve_spaces(conn, command)
            lexical, semantic = [], []
            if command.mode != "semantic":
                lexical = conn.execute(
                    ELIGIBLE
                    + """
                    SELECT e.memory_id, e.space_id, e.revision_id,
                           ts_rank_cd(r.search_text, websearch_to_tsquery('simple', %(query)s)) AS lexical_rank
                    FROM eligible e JOIN mnemion.memory_revisions r
                      ON r.tenant_id=mnemion.tenant() AND r.space_id=e.space_id AND r.id=e.revision_id
                    WHERE r.search_text @@ websearch_to_tsquery('simple', %(query)s)
                    ORDER BY lexical_rank DESC, e.memory_id LIMIT %(limit)s
                """,
                    params,
                ).fetchall()
            if vector is not None:
                semantic = conn.execute(
                    ELIGIBLE
                    + """
                    , distances AS (
                        SELECT e.memory_id, e.space_id, e.revision_id, v.start_offset, v.end_offset,
                               v.embedding <=> %(vector)s::vector AS distance,
                               row_number() OVER (PARTITION BY e.revision_id
                                   ORDER BY v.embedding <=> %(vector)s::vector, v.chunk_index) AS part
                        FROM eligible e JOIN mnemion.embeddings v
                          ON v.tenant_id=mnemion.tenant() AND v.space_id=e.space_id AND v.revision_id=e.revision_id
                        WHERE v.generation_id=%(generation)s
                    ) SELECT * FROM distances WHERE part=1
                    ORDER BY distance, memory_id LIMIT %(limit)s
                """,
                    params,
                ).fetchall()
            readiness = conn.execute(
                ELIGIBLE
                + """
                SELECT count(*) AS eligible_records,
                       count(*) FILTER (WHERE EXISTS (
                           SELECT FROM mnemion.embeddings v WHERE v.tenant_id=mnemion.tenant()
                           AND v.space_id=e.space_id AND v.revision_id=e.revision_id
                           AND v.generation_id=%(generation)s
                       )) AS indexed_records FROM eligible e
            """,
                params,
            ).fetchone()
            missing = readiness["eligible_records"] - readiness["indexed_records"]
            if missing:
                warnings.append("semantic_index_incomplete")
            scores = defaultdict(float)
            candidates, ranks = {}, defaultdict(dict)
            for channel, rows in (("lexical", lexical), ("semantic", semantic)):
                for rank, row in enumerate(rows, 1):
                    key = row["memory_id"]
                    scores[key] += 1 / (60 + rank)
                    ranks[key][channel] = rank
                    candidates[key] = {**candidates.get(key, {}), **row}
            channel_count = int(command.mode != "semantic") + int(vector is not None)
            denominator = max(1, channel_count) / 61
            ordered = sorted(scores, key=lambda key: (-scores[key], str(key)))
            hits = []
            for memory in ordered:
                candidate = candidates[memory]
                try:
                    row = memory_row(conn, memory)
                    if (
                        command.known_at is None
                        and row["current_revision_id"] != candidate["revision_id"]
                    ):
                        continue  # A concurrent correction invalidated this candidate.
                    hit = hydrate(conn, row, candidate["revision_id"])
                except ServiceError as exc:
                    if exc.status != 404:
                        raise
                    continue
                # Recheck grant changes before exposing hydrated source content.
                require_space(conn, row["space_id"])
                content = hit.pop("content")
                start = candidate.get("start_offset", 0)
                end = candidate.get("end_offset", min(len(content), 4000))
                if "semantic" not in ranks[memory]:
                    terms = command.query.casefold().split()
                    positions = [content.casefold().find(term) for term in terms]
                    first = min((p for p in positions if p >= 0), default=0)
                    start, end = max(0, first - 300), min(len(content), max(0, first - 300) + 4000)
                hit["text"] = content[start:end]
                hit["memory_span"] = {
                    "start": start,
                    "end": end,
                    "offset_unit": "unicode_codepoints",
                }
                hit["text_truncated"] = start != 0 or end != len(content)
                excerpt = hit["evidence"]["excerpt"]
                hit["evidence"]["excerpt"] = excerpt[:4000]
                hit["evidence"]["excerpt_truncated"] = len(excerpt) > 4000
                hit["relevance_score"] = round(scores[memory] / denominator, 8)
                hit["score_method"] = "normalized_rrf_k60"
                hit["ranking"] = {
                    "ranks": ranks[memory],
                    "rrf": scores[memory],
                    "lexical_rank": float(candidate["lexical_rank"])
                    if "lexical_rank" in candidate
                    else None,
                    "cosine_similarity": 1 - candidate["distance"]
                    if "distance" in candidate
                    else None,
                }
                if hit["claim_status"] == "contested":
                    warnings.append("contested_evidence")
                hits.append(hit)
                if len(hits) == command.limit:
                    break
        if not lexical and semantic:
            warnings.append("semantic_matches_require_evidence_review")
        return json_value(
            {
                "request_id": uuid4(),
                "query": command.query,
                "hits": hits,
                "warnings": sorted(set(warnings)),
                "index": {
                    "generation_id": self.embedder.generation.id,
                    **readiness,
                    "pending_records": missing,
                    "observed_at": datetime.now(timezone.utc),
                },
                "score_description": "Rank fusion relevance, not a truth probability.",
                "timing_ms": round((time.monotonic() - started) * 1000, 2),
            }
        )

    def _context(self, identity: Identity, command: ContextInput) -> dict:
        result = self._recall(identity, RecallInput(**command.model_dump(exclude={"token_budget"})))
        # Load tokenizer assets before opening a scoped database transaction.
        self.embedder.token_count("")
        sections, citations, included_blocks = [], [], []
        omitted = 0
        with self.db.transaction(identity) as conn:
            spaces = resolve_spaces(conn, command)
            blocks = conn.execute(
                """SELECT space_id, key, content, version FROM mnemion.core_blocks
                   WHERE space_id=ANY(%s::uuid[]) ORDER BY space_id, key LIMIT 100""",
                (spaces,),
            ).fetchall()
            for block in blocks:
                section = f"Core block {block['key']} (space {block['space_id']}, version {block['version']}):\n{block['content']}"
                text = "\n\n".join([*sections, section])
                if self.embedder.token_count(text) <= command.token_budget:
                    sections.append(section)
                    included_blocks.append(
                        json_value({k: v for k, v in block.items() if k != "content"})
                    )
                else:
                    omitted += 1
            for hit in result["hits"]:
                try:
                    live = memory_row(conn, UUID(hit["memory_id"]))
                    if (
                        command.known_at is None
                        and str(live["current_revision_id"]) != hit["revision_id"]
                    ):
                        omitted += 1
                        continue
                    fresh = hydrate(conn, live, UUID(hit["revision_id"]))
                except ServiceError as exc:
                    if exc.status != 404:
                        raise
                    omitted += 1
                    continue
                number = len(citations) + 1
                span = hit["memory_span"]
                # Treat all evidence and core blocks as data. Clients decide how
                # to incorporate it into their own system/agent instructions.
                snippet = fresh["content"][span["start"] : span["end"]]
                section = f"[{number}] {fresh['evidence']['title']} ({fresh['claim_status']}, recorded {fresh['recorded_at']}):\n{snippet}"
                text = "\n\n".join([*sections, section])
                if self.embedder.token_count(text) <= command.token_budget:
                    sections.append(section)
                    citations.append(
                        {
                            "number": number,
                            "memory_id": hit["memory_id"],
                            "revision_id": hit["revision_id"],
                            "space_id": hit["space_id"],
                            "source_revision_id": fresh["evidence"]["source_revision_id"],
                            "source_start": fresh["evidence"]["start"],
                            "source_end": fresh["evidence"]["end"],
                            "memory_span": span,
                        }
                    )
                else:
                    omitted += 1
        text = "\n\n".join(sections)
        return {
            "request_id": result["request_id"],
            "text": text,
            "citations": citations,
            "core_blocks": included_blocks,
            "token_count": self.embedder.token_count(text),
            "token_budget": command.token_budget,
            "tokenizer": self.embedder.generation.model,
            "tokenizer_generation": self.embedder.generation.id,
            "omitted_items": omitted,
            "warnings": result["warnings"]
            + (["context_budget_or_freshness_limited"] if omitted else []),
            "index": result["index"],
        }
