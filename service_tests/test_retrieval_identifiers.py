from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import UUID

import psycopg
import pytest

from mnemion.service.contracts import Recall
from mnemion.service.errors import ServiceError
from mnemion.service.identifiers import query_identifiers
from mnemion.service.models import (
    GrantInput,
    KeyInput,
    MemoryInput,
    PrincipalInput,
    RecallInput,
    RevisionInput,
    ReviewInput,
    SpaceInput,
)
from mnemion.service.retrieval import RetrievalService


def test_identifier_parser_is_literal_bounded_and_does_not_expand_plain_queries():
    for query in ("where is the billing decision", "2026-10-13 7312", "-TASK-7312"):
        assert query_identifiers(query).terms == ()
    parsed = query_identifiers('TASK-7312 task-7312 "report.md"')
    assert parsed.terms == ("TASK-7312", "report.md")
    assert not parsed.truncated
    assert query_identifiers('TASK-7312 -"TASK-8888 TASK-9999"').terms == ()
    many = query_identifiers(" ".join(f"TASK-{index}" for index in range(12)))
    assert len(many.terms) == len(many.patterns) == 8 and many.truncated
    long = query_identifiers("A" * 256 + "1 TASK-7312")
    assert long.terms == ("TASK-7312",) and long.truncated


def test_literal_patterns_on_real_postgres_respect_boundaries_and_unicode(env):
    cases = [
        ("TASK-7312", "reports/TASK-7312_result.md", True),
        ("TASK-7312", "task-7312", True),
        ("TASK-7312", "TASK-73120", False),
        ("TASK-7312", "XTASK-7312", False),
        ("QX-2026-7312", "QX-2026-7312b", False),
        ("report.md", "reports/report.md", True),
        ("report.md", "Read report.md.", True),
        ("report.md", "my-report.md", False),
        ("report.md", "report.md.bak", False),
        ("report.md", "reportXmd", False),
        ("report.md", "report.md_old", False),
        ("ops/report.md", r"ops\report.md", True),
        (r"ops\report.md", "ops/report.md", True),
        ("résumé.md", "re\u0301sume\u0301.md", True),
        ("re\u0301sume\u0301.md", "résumé.md", True),
    ]
    with env.db.transaction(env.owner) as conn:
        for query, content, expected in cases:
            parsed = query_identifiers(query)
            assert len(parsed.patterns) == 1
            actual = conn.execute(
                "SELECT %s::text ~* %s::text AS matched", (content, parsed.patterns[0])
            ).fetchone()["matched"]
            assert actual is expected, (query, content)


def test_exact_filename_enters_candidates_and_beats_broad_ledgers(env):
    target = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(
            content="QX-2026-7312 was accepted. " + "garden " * 20,
            subject="Final report",
            metadata={"path": "ops/reports/TASK-7312_result.md"},
        ),
        "identifier-target",
    )
    for index in range(42):
        env.memory.save(
            env.owner,
            env.space,
            MemoryInput(content=f"billing confirmation for another project, entry {index}"),
            f"semantic-distractor-{index}",
        )
    for index in range(6):
        env.memory.save(
            env.owner,
            env.space,
            MemoryInput(
                content="TASK-7312 billing confirmation QX-2026-7312 " * (index + 1),
                subject=f"Broad ledger {index}",
            ),
            f"ledger-{index}",
        )
    while env.worker.run_once():
        pass
    service = RetrievalService(env.db, env.embedder)
    query = RecallInput(
        query="TASK-7312 billing confirmation QX-2026-7312", space_ids=[env.space], limit=6
    )
    # The exact file is outside the old semantic candidate pool, and its body
    # lacks the full lexical query. Reranking the old pool cannot retrieve it.
    semantic = service.recall(env.owner, query.model_copy(update={"mode": "semantic", "limit": 30}))
    assert target["memory_id"] not in {hit["memory_id"] for hit in semantic["hits"]}
    assert all("identifier" not in hit["ranking"] for hit in semantic["hits"])
    result = service.recall(env.owner, query)
    hit = result["hits"][0]
    assert hit["memory_id"] == target["memory_id"]
    assert hit["ranking"]["ranks"] == {}
    assert hit["ranking"]["identifier"] == {
        "rank": 1,
        "label_rank": 1,
        "matched": 2,
        "requested": 2,
        "label_matches": 1,
        "weight": 1,
        "label_weight": 3,
    }
    assert 0 < hit["relevance_score"] <= 1
    assert hit["score_method"] == "normalized_rrf_k60"
    Recall.model_validate(result)
    # Short filename-only queries work before, and independently of, indexing.
    lexical = service.recall(
        env.owner,
        query.model_copy(update={"query": "TASK-7312_result.md", "mode": "lexical"}),
    )
    assert lexical["hits"][0]["memory_id"] == target["memory_id"]


def test_label_window_keeps_a_file_outside_the_identifier_coverage_window(env):
    for index in range(35):
        env.memory.save(
            env.owner,
            env.space,
            MemoryInput(content="TASK-7312 QX-2026-7312"),
            f"coverage-ledger-{index}",
        )
    target = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="Final report", metadata={"path": "TASK-7312.md"}),
        "label-window",
    )
    result = RetrievalService(env.db, env.embedder).recall(
        env.owner,
        RecallInput(
            query="TASK-7312 QX-2026-7312 missing words",
            space_ids=[env.space],
            mode="lexical",
            limit=6,
        ),
    )
    hit = result["hits"][0]
    assert hit["memory_id"] == target["memory_id"]
    assert hit["ranking"]["identifier"]["rank"] == 36
    assert hit["ranking"]["identifier"]["label_rank"] == 1
    assert hit["ranking"]["identifier"]["matched"] == 1


def test_near_identifiers_do_not_supply_literal_candidates_or_unbounded_terms(env):
    env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="Another task", metadata={"path": "TASK-73120.md"}),
        "near-identifier",
    )
    service = RetrievalService(env.db, env.embedder)
    command = RecallInput(query="TASK-7312 absent text", space_ids=[env.space], mode="lexical")
    assert service.recall(env.owner, command)["hits"] == []
    many = service.recall(
        env.owner,
        command.model_copy(update={"query": " ".join(f"TASK-{index}" for index in range(12))}),
    )
    assert "identifier_query_truncated" in many["warnings"]


def test_identifier_candidates_do_not_resurrect_explicit_lexical_exclusions(env):
    excluded = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="TASK-7312 billing", subject="TASK-7312"),
        "excluded-identifier",
    )
    included = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="TASK-7312 garden"),
        "included-identifier",
    )
    result = RetrievalService(env.db, env.embedder).recall(
        env.owner,
        RecallInput(query="TASK-7312 -billing", space_ids=[env.space], mode="lexical"),
    )
    assert [hit["memory_id"] for hit in result["hits"]] == [included["memory_id"]]
    assert excluded["memory_id"] not in {hit["memory_id"] for hit in result["hits"]}
    assert all("identifier" not in hit["ranking"] for hit in result["hits"])


def reader(env):
    principal = env.identities.create_principal(
        env.owner, PrincipalInput(name="Identifier reader", kind="application")
    )
    principal_id = UUID(principal["id"])
    key = env.identities.create_key(env.owner, principal_id, KeyInput(name="Reader key"))
    env.identities.grant(env.owner, env.space, principal_id, GrantInput(role="reader"))
    return principal_id, env.db.authenticate(key["api_key"])


def test_exact_candidates_are_scoped_before_ranks_and_respect_live_review(env):
    _, identity = reader(env)
    hidden = UUID(env.identities.create_space(env.owner, SpaceInput(name="Hidden"))["id"])
    env.memory.save(
        env.owner, hidden, MemoryInput(content="TASK-7312", subject="TASK-7312"), "hidden-id"
    )
    visible = env.memory.save(
        env.owner, env.space, MemoryInput(content="Accepted", subject="TASK-7312"), "visible-id"
    )
    service = RetrievalService(env.db, env.embedder)
    command = RecallInput(query="TASK-7312 missing prose", all_accessible=True, mode="lexical")
    result = service.recall(identity, command)
    assert [hit["memory_id"] for hit in result["hits"]] == [visible["memory_id"]]
    assert result["hits"][0]["ranking"]["identifier"]["rank"] == 1
    assert result["index"]["eligible_records"] == 1
    env.memory.review(
        env.owner,
        UUID(visible["memory_id"]),
        ReviewInput(expected_version=1, state="quarantined", reason="Private review"),
    )
    assert service.recall(identity, command)["hits"] == []


def test_exact_labels_follow_revision_metadata_filters_and_source_tombstones(env):
    saved = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="Accepted", metadata={"path": "TASK-7312.md", "team": "one"}),
        "old-label",
    )
    known_at = datetime.now(timezone.utc)
    env.memory.revise(
        env.owner,
        UUID(saved["memory_id"]),
        RevisionInput(
            content="Corrected",
            metadata={"path": "TASK-8888.md", "team": "two"},
            expected_version=1,
            reason="Correct task association",
        ),
        "new-label",
    )
    service = RetrievalService(env.db, env.embedder)
    command = RecallInput(query="TASK-7312", space_ids=[env.space], mode="lexical")
    assert service.recall(env.owner, command)["hits"] == []
    historical = command.model_copy(update={"known_at": known_at})
    hit = service.recall(env.owner, historical)["hits"][0]
    assert hit["revision_id"] == saved["revision_id"]
    assert (
        service.recall(
            env.owner, historical.model_copy(update={"metadata_filter": {"team": "two"}})
        )["hits"]
        == []
    )
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            """UPDATE mnemion.sources s SET deleted_at=now()
            FROM mnemion.source_revisions sr JOIN mnemion.memory_revisions mr
              ON mr.tenant_id=sr.tenant_id AND mr.space_id=sr.space_id AND mr.source_revision_id=sr.id
            WHERE s.tenant_id=sr.tenant_id AND s.space_id=sr.space_id AND s.id=sr.source_id
              AND mr.id=%s""",
            (UUID(saved["revision_id"]),),
        )
    assert service.recall(env.owner, historical)["hits"] == []


def test_exact_recall_rechecks_a_grant_revoked_during_inference(env, monkeypatch):
    principal, identity = reader(env)
    env.memory.save(
        env.owner, env.space, MemoryInput(content="Accepted", subject="TASK-7312"), "revoked-id"
    )
    query = env.embedder.query

    def revoke(text):
        env.identities.revoke_grant(env.owner, env.space, principal)
        return query(text)

    monkeypatch.setattr(env.embedder, "query", revoke)
    with pytest.raises(ServiceError) as error:
        RetrievalService(env.db, env.embedder).recall(
            identity, RecallInput(query="TASK-7312", space_ids=[env.space])
        )
    assert error.value.status in (403, 404)


def test_revision_change_between_candidate_channels_discards_old_ranks(env, monkeypatch):
    saved = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="TASK-7312 billing", subject="TASK-7312"),
        "before-correction",
    )
    while env.worker.run_once():
        pass
    transaction = env.db.transaction
    changed = False

    class Connection:
        def __init__(self, conn):
            self.conn = conn

        def execute(self, statement, *args, **kwargs):
            nonlocal changed
            if (
                not changed
                and isinstance(statement, str)
                and "identifier_matches AS MATERIALIZED" in statement
            ):
                changed = True
                env.memory.revise(
                    env.owner,
                    UUID(saved["memory_id"]),
                    RevisionInput(
                        content="billing corrected",
                        subject="Different report",
                        expected_version=1,
                        reason="Remove incorrect task association",
                    ),
                    "during-recall",
                )
                while env.worker.run_once():
                    pass
            return self.conn.execute(statement, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self.conn, name)

    @contextmanager
    def changing_transaction(identity):
        with transaction(identity) as conn:
            yield Connection(conn)

    monkeypatch.setattr(env.db, "transaction", changing_transaction)
    result = RetrievalService(env.db, env.embedder).recall(
        env.owner, RecallInput(query="TASK-7312 billing", space_ids=[env.space])
    )
    assert changed
    hit = result["hits"][0]
    assert hit["memory_id"] == saved["memory_id"]
    assert hit["revision_id"] != saved["revision_id"]
    assert hit["text"] == "billing corrected"
    assert hit["ranking"]["ranks"] == {"semantic": 1}
    assert hit["ranking"]["lexical_rank"] is None
    assert "identifier" not in hit["ranking"]
