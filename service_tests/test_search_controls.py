"""Recency and rejection controls exercise real scoped PostgreSQL retrieval."""

from datetime import datetime, timezone

from mnemion.service.models import ContextInput, MemoryInput, RecallInput
from mnemion.service.retrieval import RetrievalService


def test_recent_source_date_and_recorded_filter_apply_before_candidate_limit(env):
    for index in range(32):
        env.memory.save(
            env.owner,
            env.space,
            MemoryInput(
                content="billing " * 20, metadata={"source_modified_at": "2020-01-01T00:00:00Z"}
            ),
            f"old-ledger-{index}",
        )
    cutoff = datetime.now(timezone.utc)
    target = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(
            content="billing decision", metadata={"source_modified_at": "2025-06-01T00:00:00+00:00"}
        ),
        "recent-decision",
    )
    service = RetrievalService(env.db, env.embedder)
    query = RecallInput(
        query="billing", space_ids=[env.space], mode="lexical", limit=1, sort="recent"
    )
    recent = service.recall(env.owner, query)
    assert recent["hits"][0]["memory_id"] == target["memory_id"]
    assert recent["index"]["eligible_records"] == 33
    filtered = service.recall(
        env.owner, query.model_copy(update={"recorded_after": cutoff, "sort": "relevance"})
    )
    assert filtered["hits"][0]["memory_id"] == target["memory_id"]
    assert filtered["index"]["eligible_records"] == 1


def test_invalid_or_missing_source_date_falls_back_to_recorded_time(env):
    receipts = [
        env.memory.save(
            env.owner, env.space, MemoryInput(content="billing", metadata=metadata), f"date-{index}"
        )
        for index, metadata in enumerate(
            [
                {"source_modified_at": "2020-01-01T00:00:00Z"},
                {"source_modified_at": "not a timestamp"},
                {"source_modified_at": "infinity"},
                {"source_modified_at": "12000-01-01T00:00:00Z"},
                {},
            ]
        )
    ]
    result = RetrievalService(env.db, env.embedder).recall(
        env.owner,
        RecallInput(query="billing", space_ids=[env.space], mode="lexical", sort="recent"),
    )
    assert [hit["memory_id"] for hit in result["hits"]] == [
        r["memory_id"] for r in reversed(receipts)
    ]
    assert result["match_status"] == "matched"


def test_semantic_only_matches_can_be_rejected_without_discarding_literal_evidence(env):
    target = env.memory.save(env.owner, env.space, MemoryInput(content="billing " * 10), "billing")
    env.memory.save(env.owner, env.space, MemoryInput(content="garden " * 10), "garden")
    while env.worker.run_once():
        pass
    service = RetrievalService(env.db, env.embedder)
    query = RecallInput(query="zebra", space_ids=[env.space])
    baseline = service.recall(env.owner, query)
    assert baseline["match_status"] == "semantic_only" and len(baseline["hits"]) == 2
    assert "semantic_matches_require_evidence_review" in baseline["warnings"]
    for controls in ({"min_similarity": 0.99}, {"min_score": 1.0}):
        filtered = service.recall(env.owner, query.model_copy(update=controls))
        assert filtered["hits"] == [] and filtered["match_status"] == "empty"
        assert filtered["filtered_candidates"] == 2
    literal = service.recall(
        env.owner, query.model_copy(update={"query": "billing", "min_similarity": 1.0})
    )
    assert [hit["memory_id"] for hit in literal["hits"]] == [target["memory_id"]]
    assert literal["match_status"] == "matched"
    context = service.context(
        env.owner, ContextInput(query="zebra", space_ids=[env.space], min_similarity=0.99)
    )
    assert context["citations"] == []
