from datetime import datetime, timezone
from uuid import UUID

import pytest
import psycopg

from mnemion.service.errors import ServiceError
from mnemion.service.models import (
    BlockInput,
    ContextInput,
    MemoryInput,
    RecallInput,
    RevisionInput,
    ReviewInput,
    SpaceInput,
)
from mnemion.service.retrieval import RetrievalService


def test_keyword_before_indexing_hybrid_after_and_quarantine_is_live(env):
    service = RetrievalService(env.db, env.embedder)
    receipt = env.memory.save(
        env.owner, env.space, MemoryInput(content="Postgres handles billing transactions"), "search"
    )
    query = RecallInput(query="Postgres billing", space_ids=[env.space])
    early = service.recall(env.owner, query)
    assert early["hits"][0]["memory_id"] == receipt["memory_id"]
    assert early["index"]["pending_records"] == 1
    assert early["hits"][0]["ranking"]["ranks"] == {"lexical": 1}
    while env.worker.run_once():
        pass
    indexed = service.recall(env.owner, query)
    assert indexed["index"]["pending_records"] == 0
    assert indexed["hits"][0]["ranking"]["ranks"] == {"lexical": 1, "semantic": 1}
    assert indexed["hits"][0]["relevance_score"] == 1
    env.memory.review(
        env.owner,
        UUID(receipt["memory_id"]),
        ReviewInput(expected_version=1, state="quarantined", reason="Private review"),
    )
    hidden = service.recall(env.owner, query)
    assert hidden["hits"] == [] and hidden["index"]["eligible_records"] == 0


def test_scope_before_candidates_and_temporal_correction(env):
    service = RetrievalService(env.db, env.embedder)
    other_space = env.identities.create_space(env.owner, SpaceInput(name="Other space"))
    env.memory.save(
        env.owner,
        UUID(other_space["id"]),
        MemoryInput(content="billing billing billing"),
        "private",
    )
    original = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="billing uses Postgres", subject="Customer Alpha"),
        "original",
    )
    known_at = datetime.now(timezone.utc)
    revised = env.memory.revise(
        env.owner,
        UUID(original["memory_id"]),
        RevisionInput(
            content="billing uses a new Postgres cluster",
            subject="Customer Beta",
            expected_version=1,
            reason="Move to new cluster",
            claim_status="verified",
        ),
        "corrected",
    )
    now = service.recall(
        env.owner, RecallInput(query="billing", space_ids=[env.space], mode="lexical")
    )
    assert len(now["hits"]) == 1 and now["hits"][0]["revision_id"] == revised["revision_id"]
    then = service.recall(
        env.owner,
        RecallInput(
            query="billing",
            space_ids=[env.space],
            mode="lexical",
            known_at=known_at,
            subject="Customer Alpha",
        ),
    )
    assert then["hits"][0]["revision_id"] == original["revision_id"]
    assert then["hits"][0]["subject"] == "Customer Alpha"
    env.memory.forget(env.owner, UUID(original["memory_id"]), expected_version=2, key="remove")
    assert (
        service.recall(
            env.owner,
            RecallInput(query="billing", space_ids=[env.space], known_at=known_at, mode="lexical"),
        )["hits"]
        == []
    )


def test_context_budget_counts_headers_blocks_and_citations(env):
    service = RetrievalService(env.db, env.embedder)
    env.memory.put_block(
        env.owner,
        env.space,
        "team",
        BlockInput(content="Core context for billing", expected_version=0),
    )
    for index in range(4):
        env.memory.save(
            env.owner,
            env.space,
            MemoryInput(content=f"billing decision {index} " + "evidence " * 40),
            f"ctx-{index}",
        )
    result = service.context(
        env.owner,
        ContextInput(query="billing", space_ids=[env.space], mode="lexical", token_budget=100),
    )
    assert result["token_count"] == env.embedder.token_count(result["text"]) <= 100
    assert result["core_blocks"] and result["citations"] and result["omitted_items"] > 0
    assert "[1]" in result["text"]
    for citation in result["citations"]:
        assert env.memory.source(env.owner, UUID(citation["source_revision_id"]))["content"]
    with pytest.raises(ServiceError) as error:
        env.memory.put_block(
            env.owner, env.space, "team", BlockInput(content="Stale overwrite", expected_version=0)
        )
    assert error.value.status == 409


def test_embedding_failure_is_explicit_and_preserves_keyword_search(env, monkeypatch):
    env.memory.save(env.owner, env.space, MemoryInput(content="billing decision"), "model-failure")

    def unavailable(text):
        raise RuntimeError("Simulated inference failure")

    monkeypatch.setattr(env.embedder, "query", unavailable)
    service = RetrievalService(env.db, env.embedder)
    result = service.recall(env.owner, RecallInput(query="billing", space_ids=[env.space]))
    assert len(result["hits"]) == 1 and "semantic_unavailable_lexical_only" in result["warnings"]
    with pytest.raises(ServiceError) as error:
        service.recall(
            env.owner, RecallInput(query="billing", space_ids=[env.space], mode="semantic")
        )
    assert error.value.status == 503


def test_many_sources_resolve_independently_and_source_tombstones_hide_history(env):
    saved = [
        env.memory.save(
            env.owner,
            env.space,
            MemoryInput(content=f"Corpus evidence from distinct source {index}"),
            f"source-{index}",
        )
        for index in range(48)
    ]
    while env.worker.run_once():
        pass
    service = RetrievalService(env.db, env.embedder)
    command = RecallInput(query="corpus", space_ids=[env.space], limit=50)
    before = service.recall(env.owner, command)
    assert {row["memory_id"] for row in before["hits"]} == {row["memory_id"] for row in saved}
    assert before["index"]["eligible_records"] == before["index"]["indexed_records"] == 48
    known_at = datetime.now(timezone.utc)
    # A source denial must hide its evidence even in a historical query. It
    # must not hide other sources or depend on a memory tombstone being set.
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            """UPDATE mnemion.sources s SET deleted_at=now()
            FROM mnemion.source_revisions sr JOIN mnemion.memory_revisions mr
              ON mr.tenant_id=sr.tenant_id AND mr.space_id=sr.space_id AND mr.source_revision_id=sr.id
            WHERE s.tenant_id=sr.tenant_id AND s.space_id=sr.space_id AND s.id=sr.source_id
              AND mr.id=%s""",
            (UUID(saved[0]["revision_id"]),),
        )
    for historical in (None, known_at):
        result = service.recall(env.owner, command.model_copy(update={"known_at": historical}))
        assert {row["memory_id"] for row in result["hits"]} == {
            row["memory_id"] for row in saved[1:]
        }
        assert result["index"]["eligible_records"] == result["index"]["indexed_records"] == 47
