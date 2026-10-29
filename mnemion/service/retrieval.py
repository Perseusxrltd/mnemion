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
from .identifiers import (
    IDENTIFIER_CANDIDATES,
    IDENTIFIER_LABEL_WEIGHT,
    IDENTIFIER_WEIGHT,
    query_identifiers,
)
from .keywords import KEYWORD_CANDIDATES, KEYWORD_WEIGHT, permits_keyword_fallback
from .models import ContextInput, RecallInput, json_value
from .model_registry import ModelRegistry
from .model_state import selected_generations
from .model_state import settings as model_settings
from .passages import evidence_passage, passage_span
from .passage_time import select as select_passage_time
from .ranking import adjustment, archive_adjustment
from .repository import hydrate, memory_row
from .telemetry import Telemetry
from .source_health import source_health

logger = logging.getLogger(__name__)
RETRIEVAL_IMPLEMENTATION = (
    "scoped_exact_cosine_lexical_question_coverage_passage_time_archive_rrf_k60_v3"
)

# Materialize the authorized candidates before computing distance or ranks.
# The initial engine uses exact vector distance; no post-hoc tenant filtering
# or approximate-index recall claims are hidden behind this query.
# Keep source visibility as a dependent point lookup. Its LIMIT 1 prevents a
# fresh database's sparse planner statistics from multiplying all source rows
# in a space before matching the revision ID; RLS still applies to both tables.
_ELIGIBLE_PREFIX = """
WITH eligible AS MATERIALIZED (
    SELECT m.id AS memory_id, m.space_id, r.id AS revision_id,
           CASE WHEN %(group_sources)s
                     AND r.metadata->>'extractor'='mnemion-text-v1'
                     AND jsonb_typeof(r.metadata->'source_external_id')='string'
                     AND length(r.metadata->>'source_external_id') BETWEEN 1 AND 512
                     AND jsonb_typeof(r.metadata->'part')='number'
                     AND r.metadata->>'part' ~ '^[0-9]{1,12}$'
                THEN jsonb_build_array('document',m.space_id,m.created_by,r.metadata->>'source_external_id')
                ELSE jsonb_build_array('memory',m.id) END AS source_group,
           CASE WHEN jsonb_typeof(r.metadata->'path')='string'
                THEN r.metadata->>'path' END AS rank_path,
           coalesce(CASE WHEN pg_input_is_valid(r.metadata->>'source_modified_at', 'timestamptz')
             THEN CASE WHEN (r.metadata->>'source_modified_at')::timestamptz
                        BETWEEN timestamptz '0001-01-02 00:00:00+00' AND timestamptz '9999-12-30 00:00:00+00'
                        AND (r.metadata->>'source_modified_at')::timestamptz<=r.recorded_at
                       THEN (r.metadata->>'source_modified_at')::timestamptz END
             END, r.recorded_at) AS rank_time
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
"""
_ELIGIBLE_FILTERS = """
      AND m.deleted_at IS NULL AND m.review_state='ordinary'
      AND (%(subject)s::text IS NULL OR r.subject=%(subject)s)
      AND (%(kinds)s::text[] IS NULL OR r.kind=ANY(%(kinds)s::text[]))
      AND r.metadata @> %(metadata)s::jsonb
      AND (%(recorded_after)s::timestamptz IS NULL OR r.recorded_at>=%(recorded_after)s::timestamptz)
      AND r.claim_status IN ('observed', 'verified', 'contested')
      AND (r.claim_status<>'contested' OR %(contested)s)
      AND (r.valid_from IS NULL OR r.valid_from<=coalesce(%(valid_at)s::timestamptz, now()))
      AND (r.valid_to IS NULL OR r.valid_to>coalesce(%(valid_at)s::timestamptz, now()))
)
"""
ELIGIBLE = _ELIGIBLE_PREFIX + _ELIGIBLE_FILTERS
# Apply the candidate bound inside the materialized CTE. An outer WHERE cannot
# prevent that CTE from rebuilding chronology eligibility for the whole corpus.
# Both variants retain identical source, revision, scope and temporal checks.
SELECTED_ELIGIBLE = (
    _ELIGIBLE_PREFIX + "      AND m.id=ANY(%(selected_memories)s::uuid[])\n" + _ELIGIBLE_FILTERS
)


class RetrievalService:
    def __init__(
        self,
        database: Database,
        embedder: Embedder,
        telemetry: Telemetry | None = None,
        *,
        registry: ModelRegistry | None = None,
    ):
        self.db = database
        self.embedder = embedder
        self.telemetry = telemetry
        self.registry = registry or ModelRegistry(embedder)

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
                        generation=result.get("index", {}).get("generation_id")
                        or "mixed_or_unresolved",
                        failed=failed,
                        duration_ms=(time.monotonic() - started) * 1000,
                        input_bytes=len(command.query.encode("utf-8")),
                        output_bytes=len(text.encode("utf-8")),
                        output_tokens=result.get("token_count", 0)
                        if result.get("token_count_unit", "model_tokens") == "model_tokens"
                        else 0,
                        records=len(result.get("hits", result.get("citations", []))),
                        empty_results=int(
                            not failed and not result.get("hits", result.get("citations", []))
                        ),
                        fallbacks=int(
                            bool(
                                {"semantic_unavailable_lexical_only", "inference_busy_lexical_only"}
                                & set(warnings)
                            )
                        ),
                        incomplete_index=int("semantic_index_incomplete" in warnings),
                    )
                except Exception:
                    logger.warning("Retrieval diagnostic sample was not recorded")

    def _check_routing(self, conn, command, spaces, routing):
        # Source leases and grants can change without changing any model.
        # Refuse the stale selection before inference or returning content,
        # but do not misdirect the caller toward model reconfiguration.
        if set(spaces) != routing.keys():
            raise ServiceError(
                409,
                "scope_changed",
                "Readable spaces changed during the search; retry using current permissions.",
            )
        if (
            selected_generations(
                conn, spaces, self.embedder.generation.id, command.embedding_generation
            )
            != routing
        ):
            raise ServiceError(
                409, "generation_changed", "Space model settings changed; retry the search."
            )

    def _recall(self, identity: Identity, command: RecallInput) -> dict:
        started = time.monotonic()
        ranking_reference = command.known_at or command.valid_at or datetime.now(timezone.utc)
        with self.db.transaction(identity) as conn:
            spaces = resolve_spaces(conn, command)
            routing = selected_generations(
                conn, spaces, self.embedder.generation.id, command.embedding_generation
            )
        groups = defaultdict(list)
        for space, generation in routing.items():
            groups[generation].append(space)
        warnings = []
        vectors = {}
        busy_fallback = False
        if command.mode != "lexical":
            for generation in groups:
                try:
                    with self.db.transaction(identity) as conn:
                        self._check_routing(conn, command, resolve_spaces(conn, command), routing)
                        for space in groups[generation]:
                            policy = model_settings(conn, space, self.embedder.generation.id)
                            active_paused = (
                                policy.get("inference_paused")
                                and policy["active_generation_id"] == generation
                            )
                            candidate_unapproved = (
                                generation == policy["candidate_generation_id"]
                                and self.registry.network_egress(generation)
                                and not policy.get("candidate_network_egress_approved")
                            )
                            if active_paused or candidate_unapproved:
                                raise ServiceError(
                                    503,
                                    "embedding_processing_paused",
                                    "An administrator must reapprove model processing after recovery.",
                                )
                    model = self.registry.get(generation)
                    vectors[generation] = vector_literal(
                        model.query(command.query), model.generation.dimensions
                    )
                except Exception as exc:
                    if (
                        isinstance(exc, ServiceError)
                        and exc.status == 503
                        and exc.code == "inference_busy"
                        and command.on_inference_busy == "lexical"
                    ):
                        # A caller opts into a complete keyword-only result,
                        # including when another generation already returned a
                        # vector. Keep scope/freshness rechecks below and stop
                        # requesting model capacity for this call.
                        vectors.clear()
                        busy_fallback = True
                        warnings.append("inference_busy_lexical_only")
                        break
                    if isinstance(exc, ServiceError) and exc.code not in {
                        "embedding_profile_unavailable",
                        "embedding_processing_paused",
                        "inference_memory_budget",
                    }:
                        raise
                    logger.warning("Query embedding unavailable (%s)", type(exc).__name__)
                    if command.mode == "semantic":
                        raise ServiceError(
                            503,
                            "embedding_unavailable",
                            "Semantic search is temporarily unavailable.",
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
            "metadata": Jsonb(command.metadata_filter),
            "recorded_after": command.recorded_after,
            "recent": command.sort == "recent",
            "group_sources": command.max_per_source > 0,
        }
        identifiers = query_identifiers(command.query)
        identifier_channel = bool(identifiers.terms) and (
            command.mode != "semantic" or busy_fallback
        )
        if identifiers.truncated and (command.mode != "semantic" or busy_fallback):
            warnings.append("identifier_query_truncated")
        with self.db.transaction(identity) as conn:
            # Recheck after model inference, including revoked keys and grants.
            params["spaces"] = resolve_spaces(conn, command)
            warnings.extend(
                source_health(conn, None if command.all_accessible else params["spaces"])[
                    "attention"
                ]
            )
            self._check_routing(conn, command, params["spaces"], routing)
            lexical, semantic, exact, keywords = [], [], [], []
            if command.mode != "semantic" or busy_fallback:
                lexical = conn.execute(
                    ELIGIBLE
                    + """
                    , lexical_matches AS (
                    SELECT e.memory_id, e.space_id, e.revision_id, e.source_group, e.rank_time, e.rank_path,
                           ts_rank_cd(r.search_text, websearch_to_tsquery('simple', %(query)s)) AS lexical_rank
                    FROM eligible e JOIN mnemion.memory_revisions r
                      ON r.tenant_id=mnemion.tenant() AND r.space_id=e.space_id AND r.id=e.revision_id
                    WHERE r.search_text @@ websearch_to_tsquery('simple', %(query)s)
                    ), lexical_sources AS (
                        SELECT *,row_number() OVER (PARTITION BY source_group
                            ORDER BY CASE WHEN %(recent)s THEN rank_time END DESC NULLS LAST,
                                     lexical_rank DESC,memory_id) AS source_position
                        FROM lexical_matches
                    )
                    SELECT * FROM lexical_sources
                    ORDER BY source_position,
                             CASE WHEN %(recent)s THEN rank_time END DESC NULLS LAST,
                             lexical_rank DESC,memory_id LIMIT %(limit)s
                """,
                    params,
                ).fetchall()
            if identifier_channel:
                exact = conn.execute(
                    ELIGIBLE + IDENTIFIER_CANDIDATES,
                    {
                        **params,
                        "identifier_patterns": list(identifiers.patterns),
                        "identifier_question": command.keyword_fallback
                        and command.mode == "hybrid"
                        and bool(vectors)
                        and not busy_fallback
                        and not lexical
                        and permits_keyword_fallback(command.query),
                    },
                ).fetchall()
            if (
                command.keyword_fallback
                and command.mode == "hybrid"
                and bool(vectors)
                and not busy_fallback
                and not lexical
                and permits_keyword_fallback(command.query)
            ):
                keywords = conn.execute(ELIGIBLE + KEYWORD_CANDIDATES, params).fetchall()
                if keywords:
                    warnings.append("partial_keyword_support")
            for generation, group_spaces in groups.items():
                if generation not in vectors:
                    continue
                group_rows = conn.execute(
                    ELIGIBLE
                    + """
                    , distances AS (
                        SELECT e.memory_id, e.space_id, e.revision_id, e.source_group, e.rank_time, e.rank_path, v.start_offset, v.end_offset,
                               v.embedding <=> %(vector)s::vector AS distance,
                               row_number() OVER (PARTITION BY e.revision_id
                                   ORDER BY v.embedding <=> %(vector)s::vector, v.chunk_index) AS part
                        FROM eligible e JOIN mnemion.embeddings v
                          ON v.tenant_id=mnemion.tenant() AND v.space_id=e.space_id AND v.revision_id=e.revision_id
                        WHERE v.generation_id=%(generation)s
                    ), semantic_sources AS (
                        SELECT *,row_number() OVER (PARTITION BY source_group
                            ORDER BY distance,memory_id) AS source_position
                        FROM distances WHERE part=1
                    ) SELECT * FROM semantic_sources
                    ORDER BY source_position,distance,memory_id LIMIT %(limit)s
                """,
                    {
                        **params,
                        "generation": generation,
                        "spaces": group_spaces,
                        "vector": vectors[generation],
                    },
                ).fetchall()
                semantic.extend(
                    {**row, "generation_rank": rank, "embedding_generation": generation}
                    for rank, row in enumerate(group_rows, 1)
                )
            readiness = {"eligible_records": 0, "indexed_records": 0}
            for generation, group_spaces in groups.items():
                counts = conn.execute(
                    ELIGIBLE
                    + """
                SELECT count(*) AS eligible_records,
                       count(*) FILTER (WHERE EXISTS (
                           SELECT FROM mnemion.embeddings v WHERE v.tenant_id=mnemion.tenant()
                           AND v.space_id=e.space_id AND v.revision_id=e.revision_id
                           AND v.generation_id=%(generation)s
                       )) AS indexed_records FROM eligible e
            """,
                    {**params, "generation": generation, "spaces": group_spaces},
                ).fetchone()
                for key in readiness:
                    readiness[key] += counts[key]
            missing = readiness["eligible_records"] - readiness["indexed_records"]
            if missing:
                warnings.append("semantic_index_incomplete")
            scores = defaultdict(float)
            candidates, ranks = {}, defaultdict(dict)
            identifier_ranks, keyword_ranks = {}, {}
            for channel, rows, weight in (
                ("lexical", lexical, 1),
                ("identifier", exact, IDENTIFIER_WEIGHT),
                ("keywords", keywords, KEYWORD_WEIGHT),
                ("semantic", semantic, 1),
            ):
                for rank, row in enumerate(rows, 1):
                    if channel == "semantic":
                        rank = row["generation_rank"]
                    elif channel == "identifier":
                        rank = row["identifier_rank"]
                    key = row["memory_id"]
                    # Do not mix a correction's new revision with ranks or
                    # embedding offsets observed for its preceding revision.
                    if key in candidates and candidates[key]["revision_id"] != row["revision_id"]:
                        scores[key] = 0
                        ranks[key].clear()
                        identifier_ranks.pop(key, None)
                        keyword_ranks.pop(key, None)
                        candidates[key] = {}
                    supported_weight = (
                        weight * row["keyword_matches"] / row["keyword_requested"]
                        if channel == "keywords"
                        else weight
                    )
                    scores[key] += supported_weight / (60 + rank)
                    if channel == "identifier":
                        identifier_ranks[key] = rank
                        if row["identifier_label_rank"] is not None:
                            scores[key] += IDENTIFIER_LABEL_WEIGHT / (
                                60 + row["identifier_label_rank"]
                            )
                    elif channel == "keywords":
                        keyword_ranks[key] = rank
                    else:
                        ranks[key][channel] = rank
                    candidates[key] = {**candidates.get(key, {}), **row}
            channel_count = int(command.mode != "semantic" or busy_fallback) + int(bool(vectors))
            channel_count += (
                IDENTIFIER_WEIGHT + IDENTIFIER_LABEL_WEIGHT if identifier_channel else 0
            )
            if keywords and identifier_channel:
                channel_count += KEYWORD_WEIGHT
            denominator = max(1, channel_count) / 61
            chronology = {}
            # One bounded, currently authorized fetch for passage chronology.
            # No new inference, reindex, or per-result query is needed. Large
            # mixed-generation searches retain their remaining candidates and
            # report the limit instead of pretending they were all reranked.
            selected = sorted(scores, key=lambda key: (-scores[key], str(key)))[:250]
            if len(selected) < len(scores):
                warnings.append("passage_ranking_window_limited")
            if selected:
                rows = conn.execute(
                    SELECTED_ELIGIBLE
                    + """SELECT e.memory_id,e.revision_id,r.content,r.metadata,r.recorded_at,r.passage_times
                    FROM eligible e JOIN mnemion.memory_revisions r
                      ON r.tenant_id=mnemion.tenant() AND r.space_id=e.space_id AND r.id=e.revision_id
                    WHERE e.memory_id=ANY(%(selected_memories)s::uuid[])""",
                    {**params, "selected_memories": selected},
                )
                for row in rows:
                    key = row["memory_id"]
                    candidate = candidates[key]
                    if row["revision_id"] != candidate["revision_id"]:
                        continue
                    preferred = (
                        (candidate["start_offset"], candidate["end_offset"])
                        if "semantic" in ranks[key]
                        else None
                    )
                    chronology[key] = select_passage_time(
                        row["content"],
                        row["passage_times"],
                        row["metadata"],
                        row["recorded_at"],
                        command.query,
                        recent=command.sort == "recent",
                        preferred=preferred,
                    )
                    candidate["rank_time"] = chronology[key]["at"]
                    if chronology[key]["limited"]:
                        warnings.append("passage_chronology_limited")
            adjustments = (
                {
                    key: adjustment(
                        score / denominator,
                        candidates[key]["rank_time"],
                        candidates[key]["rank_path"],
                        ranking_reference,
                        command.ranking_policy,
                    )
                    for key, score in scores.items()
                }
                if command.sort == "relevance"
                else {}
            )
            if adjustments and 0 < command.ranking_policy.archive_weight < 1:
                # An archive preference needs an alternative with literal
                # support. Do not let generic semantic neighbors displace the
                # only exact historical record. An explicit zero weight still
                # requests full suppression in relevance ordering.
                literal = {
                    key for key in scores if "lexical" in ranks[key] or key in identifier_ranks
                }
                if not any(adjustments[key]["archive_segment"] is None for key in literal):
                    for key in literal:
                        value = adjustments[key]
                        if value["archive_segment"] is not None:
                            value["configured_archive_factor"] = value["archive_factor"]
                            value["score"] /= value["archive_factor"]
                            value["archive_factor"] = 1.0
                            value["archive_uncontested"] = True
            keyword_factors = {}
            if keywords:
                strongest = max(row["keyword_matches"] for row in keywords)
                for key in scores:
                    # RRF treats neighboring ranks similarly. A broad ledger
                    # matching one shared ID must not receive almost the same
                    # question support as the actual decision's several terms.
                    # Keep the original relevance/minimum filters unchanged.
                    factor = 0.5 + 0.5 * candidates[key].get("keyword_matches", 0) / strongest
                    keyword_factors[key] = factor
                    if key in adjustments:
                        adjustments[key]["keyword_factor"] = factor
                        adjustments[key]["score"] = round(adjustments[key]["score"] * factor, 8)
            ordered = sorted(
                scores,
                key=lambda key: (
                    -adjustments[key]["score"] if adjustments else -scores[key],
                    str(key),
                ),
            )
            recent_archives = {}
            if command.sort == "recent":
                ratio = command.ranking_policy.recent_relevance_ratio
                best_support = max(
                    (value["matched_terms"] for value in chronology.values()), default=0
                )
                # Prose with just one shared name or project often crosses
                # languages. Preserve its existing key-term support rather
                # than letting near-equal RRF ranks promote fresh noise.
                comparison_support = {
                    key: chronology.get(key, {}).get("matched_terms", 0)
                    if best_support >= 2 and command.mode != "semantic"
                    else scores[key] * keyword_factors.get(key, 1)
                    for key in scores
                }
                best_comparison = max(comparison_support.values(), default=0)
                prioritized = {
                    key
                    for key in scores
                    if ratio == 0
                    or key in chronology
                    and comparison_support[key] >= best_comparison * ratio
                }
                if len(prioritized) < len(scores):
                    warnings.append("recent_weak_matches_demoted")
                # Keep the existing relevance floor: an unrelated fresh note
                # must not jump ahead of strong historical evidence. Among
                # comparable matches only, apply the same explicit archive
                # preference as relevance ordering, without inventing dates.
                recent_archives = {
                    key: archive_adjustment(candidates[key]["rank_path"], command.ranking_policy)
                    for key in scores
                }
                best_weighted = max(
                    (
                        comparison_support[key] * recent_archives[key]["archive_factor"]
                        for key in prioritized
                    ),
                    default=0,
                )
                for key, value in recent_archives.items():
                    value["demoted"] = bool(
                        ratio > 0
                        and key in prioritized
                        and value["archive_segment"] is not None
                        and comparison_support[key] * value["archive_factor"]
                        < best_weighted * ratio
                    )
                if any(value["demoted"] for value in recent_archives.values()):
                    warnings.append("recent_archived_matches_demoted")
                ordered.sort(
                    key=lambda key: (
                        key in prioritized,
                        not recent_archives[key]["demoted"],
                        candidates[key]["rank_time"]
                        if key in prioritized
                        else datetime.min.replace(tzinfo=timezone.utc),
                        scores[key],
                    ),
                    reverse=True,
                )
            hits = []
            filtered = 0
            grouped = 0
            source_counts = defaultdict(int)
            for memory in ordered:
                candidate = candidates[memory]
                score = round(scores[memory] / denominator, 8)
                if score < command.min_score or (
                    command.min_similarity is not None
                    and "lexical" not in ranks[memory]
                    and memory not in identifier_ranks
                    and (
                        "distance" not in candidate
                        or 1 - candidate["distance"] < command.min_similarity
                    )
                ):
                    filtered += 1
                    continue
                source_group = tuple(candidate["source_group"])
                if command.max_per_source and source_counts[source_group] >= command.max_per_source:
                    grouped += 1
                    continue
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
                preferred = (
                    (candidate["start_offset"], candidate["end_offset"])
                    if "semantic" in ranks[memory]
                    else None
                )
                start, end = passage_span(content, command.query, preferred)
                hit["text"] = content[start:end]
                hit["memory_span"] = {
                    "start": start,
                    "end": end,
                    "offset_unit": "unicode_codepoints",
                }
                hit["text_truncated"] = start != 0 or end != len(content)
                evidence_passage(hit["evidence"], command.query, content, (start, end))
                hit["relevance_score"] = score
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
                if adjustments:
                    hit["ranking"]["adjustment"] = adjustments[memory]
                if recent_archives:
                    hit["ranking"]["archive"] = recent_archives[memory]
                if memory in chronology:
                    value = chronology[memory]
                    hit["ranking"]["recency"] = {
                        "at": value["at"],
                        "basis": value["basis"],
                        "tracked": value["tracked"],
                        "limited": value["limited"],
                        "span": {
                            "start": value["start"],
                            "end": value["end"],
                            "offset_unit": "unicode_codepoints",
                        },
                        "matched_terms": value["matched_terms"],
                        "requested_terms": value["requested_terms"],
                        "prioritized": memory in prioritized if command.sort == "recent" else None,
                        **(
                            {
                                "comparison_support": comparison_support[memory],
                                "comparison_basis": "passage_coverage"
                                if best_support >= 2 and command.mode != "semantic"
                                else "rank_fusion_with_keyword_support"
                                if keyword_factors
                                else "rank_fusion",
                            }
                            if command.sort == "recent"
                            else {}
                        ),
                    }
                if memory in identifier_ranks:
                    hit["ranking"]["identifier"] = {
                        "rank": identifier_ranks[memory],
                        "label_rank": candidate["identifier_label_rank"],
                        "matched": candidate["identifier_matches"],
                        "requested": len(identifiers.terms),
                        "label_matches": candidate["identifier_label_matches"],
                        "weight": IDENTIFIER_WEIGHT,
                        "label_weight": IDENTIFIER_LABEL_WEIGHT,
                        **(
                            {"context_matches": candidate["identifier_context_matches"]}
                            if candidate["identifier_context_matches"]
                            else {}
                        ),
                    }
                if memory in keyword_ranks:
                    hit["ranking"]["keywords"] = {
                        "rank": keyword_ranks[memory],
                        "matched": candidate["keyword_matches"],
                        "requested": candidate["keyword_requested"],
                        "terms": candidate["keyword_terms"],
                        "weight": KEYWORD_WEIGHT
                        * candidate["keyword_matches"]
                        / candidate["keyword_requested"],
                    }
                hit["embedding_generation"] = routing[row["space_id"]]
                if hit["claim_status"] == "contested":
                    warnings.append("contested_evidence")
                hits.append(hit)
                source_counts[source_group] += 1
                if len(hits) == command.limit:
                    break
        matched = any(
            hit["ranking"]["ranks"].get("lexical") or hit["ranking"].get("identifier")
            for hit in hits
        )
        match_status = "empty" if not hits else "matched" if matched else "semantic_only"
        if match_status == "semantic_only":
            warnings.append("semantic_matches_require_evidence_review")
        return json_value(
            {
                "request_id": uuid4(),
                "query": command.query,
                "match_status": match_status,
                "filtered_candidates": filtered,
                "source_grouping": {
                    "max_per_source": command.max_per_source,
                    "grouped_candidates": grouped,
                    "scope": "candidate_window",
                },
                "ranking_policy": command.ranking_policy.model_dump(),
                "ranking_reference_time": ranking_reference,
                "hits": hits,
                "warnings": sorted(set(warnings)),
                "index": {
                    "generation_id": next(iter(groups))
                    if len(groups) == 1
                    else (None if groups else self.embedder.generation.id),
                    "generation_ids": sorted(groups),
                    "space_generations": {
                        str(space): generation for space, generation in routing.items()
                    },
                    **readiness,
                    "pending_records": missing,
                    "observed_at": datetime.now(timezone.utc),
                },
                "score_description": "Rank fusion relevance, not a truth probability. "
                + (
                    "Exact identifiers in subjects/paths use weight 3; identifier coverage, lexical and semantic ranks use weight 1. "
                    if identifier_channel
                    else ""
                )
                + "Semantic ranks are computed separately within each embedding generation. "
                + (
                    "Partial key-term support uses up to weight 0.5, proportional to covered terms, alongside exact identifiers or in place of the absent full lexical channel; "
                    "it does not establish a complete query match. "
                    if keywords
                    else ""
                )
                + (
                    "Ordering uses ranking.adjustment.score with bounded source-age, archive-path and available question-coverage factors. A nonzero archive preference preserves literal historical evidence when no non-archived literal alternative exists; "
                    "relevance_score and min_score retain unadjusted rank fusion."
                    if command.sort == "relevance"
                    else "Recent ordering prioritizes comparable passage query coverage when at least two terms match, or rank fusion with available question-coverage support otherwise. Among those matches, archive-path weighting may demote archived evidence before passage chronology orders each group; weaker matches remain afterwards. Semantic mode uses relevance. A ratio of 0 uses strict date ordering. Age decay does not apply."
                ),
                "timing_ms": round((time.monotonic() - started) * 1000, 2),
            }
        )

    def _context(self, identity: Identity, command: ContextInput) -> dict:
        query = RecallInput(**command.model_dump(exclude={"token_budget"}))
        result = self._recall(identity, query)
        try:
            return self._context_pack(identity, command, result)
        except ServiceError as exc:
            if (
                exc.status != 503
                or exc.code != "inference_busy"
                or command.on_inference_busy != "lexical"
            ):
                raise
            # Token counting also uses the local model's admission gate. If
            # contention starts after retrieval, rebuild from fresh lexical
            # evidence and count bytes throughout; never mix counting units in
            # a partly assembled context or bypass the inference/RAM gate.
            result = self._recall(identity, query.model_copy(update={"mode": "lexical"}))
            result["warnings"] = sorted({*result["warnings"], "inference_busy_lexical_only"})
            return self._context_pack(identity, command, result)

    def _context_pack(self, identity: Identity, command: ContextInput, result: dict) -> dict:
        generation = result["index"]["generation_id"]
        busy_fallback = "inference_busy_lexical_only" in result["warnings"]
        model = self.registry.get(generation) if generation and not busy_fallback else None
        count = model.token_count if model else lambda text: len(text.encode("utf-8"))
        unit = (
            model.generation.configuration.get("token_count_unit", "model_tokens")
            if model
            else "utf8_bytes"
        )
        # Load tokenizer assets before opening a scoped database transaction.
        count("")
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
                if count(text) <= command.token_budget:
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
                if count(text) <= command.token_budget:
                    sections.append(section)
                    citations.append(
                        {
                            "number": number,
                            "memory_id": hit["memory_id"],
                            "revision_id": hit["revision_id"],
                            "space_id": hit["space_id"],
                            "source_revision_id": fresh["evidence"]["source_revision_id"],
                            "source_start": hit["evidence"]["start"],
                            "source_end": hit["evidence"]["end"],
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
            "token_count": count(text),
            "token_budget": command.token_budget,
            "tokenizer": model.generation.model
            if model
            else "UTF-8 bytes (busy inference fallback)"
            if busy_fallback
            else "UTF-8 bytes (mixed embedding generations)",
            "tokenizer_generation": model.generation.id if model else "utf8-v1",
            "token_count_unit": unit,
            "omitted_items": omitted,
            "warnings": result["warnings"]
            + (["context_budget_or_freshness_limited"] if omitted else []),
            "index": result["index"],
            "source_grouping": result["source_grouping"],
        }
