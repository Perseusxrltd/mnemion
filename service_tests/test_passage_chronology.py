"""Real query, revision and source-ingestion regressions from issues 17 and 31."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import psycopg
import pytest
import httpx
import json

from mnemion.service.contracts import Recall
from mnemion.service.models import ContextInput, MemoryInput, RecallInput, RevisionInput
from mnemion.service.passage_time import capture, select
from mnemion.service.retrieval import RetrievalService
from service_tests.test_connectors import connected as connected
from service_tests.test_connectors import ingest, item


NOW = datetime(2026, 10, 19, 8, tzinfo=timezone.utc)


def test_numbered_decisions_have_individual_chronology_and_exact_unicode_offsets():
    text = "## 2026-10-17T09:00:00Z\n(1) Café: livré. (2) T-0260: message pending.\n"
    old = capture(text, {}, NOW)
    changed = text.replace("Café: livré.", "Café: livré, facture classée.")
    chronology = capture(
        changed,
        {},
        NOW + timedelta(hours=1),
        {
            "content": text,
            "metadata": {},
            "passage_times": old,
            "recorded_at": NOW,
        },
    )
    selected = select(
        changed, chronology, {}, NOW + timedelta(hours=1), "T-0260 message", recent=True
    )
    assert selected["at"] == datetime(2026, 10, 17, 9, tzinfo=timezone.utc)
    assert selected["basis"] == "source_timestamp"
    assert changed[selected["start"] : selected["end"]] == "(2) T-0260: message pending."
    edited = select(changed, chronology, {}, NOW + timedelta(hours=1), "Café facture", recent=True)
    assert edited["at"] == NOW + timedelta(hours=1)
    assert edited["basis"] == "recorded_at"


@pytest.mark.parametrize(
    "text,expected,basis",
    [
        ("# 2026-10-17\nAtlas status", datetime(2026, 10, 17, tzinfo=timezone.utc), "source_date"),
        (
            "| 2026-10-17 12:30 | Atlas status |",
            datetime(2026, 10, 17, tzinfo=timezone.utc),
            "source_date",
        ),
        (
            "| 2026-10-17T12:30:00+02:00 | Atlas status |",
            datetime(2026, 10, 17, 10, 30, tzinfo=timezone.utc),
            "source_timestamp",
        ),
        ("Atlas deadline 2026-10-17", NOW, "recorded_at"),
        ("# Deadline 2026-10-17\nAtlas status", NOW, "recorded_at"),
        ("# 2036-10-17\nAtlas status", NOW, "recorded_at"),
        ("# 2026-99-40\nAtlas status", NOW, "recorded_at"),
        ("```\n2026-10-17 Atlas status\n```", NOW, "recorded_at"),
    ],
)
def test_source_dates_are_bounded_labels_not_inline_deadlines_or_assumed_timezones(
    text, expected, basis
):
    result = select(text, {}, {}, NOW, "Atlas status", recent=True)
    assert result["at"] == expected
    assert result["basis"] == basis


def test_dated_correction_wins_even_when_both_files_have_the_same_modified_time(env):
    source_date = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    memories = []
    for name, content in (
        ("DISPATCH.md", "| 2026-10-17T09:00:00Z | T-0260 routine is NOT created |"),
        ("LEDGER.md", "| 2026-10-17T14:30:00Z | T-0260 routine created, confirmed |"),
    ):
        memories.append(
            env.memory.save(
                env.owner,
                env.space,
                MemoryInput(
                    content=content,
                    metadata={"path": name, "source_modified_at": source_date},
                ),
                name,
            )["memory_id"]
        )
    service = RetrievalService(env.db, env.embedder)
    command = RecallInput(
        query="T-0260 routine created", mode="lexical", sort="recent", space_ids=[env.space]
    )
    result = service.recall(env.owner, command)
    assert [hit["memory_id"] for hit in result["hits"]] == memories[::-1]
    assert result["hits"][0]["ranking"]["recency"]["at"] == "2026-10-17T14:30:00+00:00"
    assert result["hits"][0]["ranking"]["recency"]["basis"] == "source_timestamp"
    assert result["hits"][0]["ranking"]["recency"]["tracked"]
    Recall.model_validate(result)
    context = service.context(env.owner, ContextInput(**command.model_dump(), token_budget=256))
    assert context["citations"][0]["memory_id"] == memories[-1]
    # Existing revisions need no reindex to use explicit dated sections.
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            "UPDATE mnemion.memory_revisions SET passage_times='{}' WHERE space_id=%s", (env.space,)
        )
    legacy = service.recall(env.owner, command)
    assert legacy["hits"][0]["memory_id"] == memories[-1]
    assert not legacy["hits"][0]["ranking"]["recency"]["tracked"]


def test_cosmetic_edits_do_not_refresh_an_unchanged_status_passage(env):
    now = datetime.now(timezone.utc)
    old_date = (now - timedelta(days=5)).isoformat()
    text = "T-0045 watch by Gmail only.\n\nUnrelated billing draft."
    old = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(
            content=text,
            metadata={"source_modified_at": old_date},
        ),
        "old-status",
    )
    current = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(
            content="T-0045 watch by Gmail; the confirmed status is unchanged.",
            metadata={"source_modified_at": (now - timedelta(days=2)).isoformat()},
        ),
        "current-status",
    )
    env.memory.revise(
        env.owner,
        UUID(old["memory_id"]),
        RevisionInput(
            content=text.replace("Gmail only", "Gmail   only").replace(
                "billing draft", "billing final"
            ),
            metadata={"source_modified_at": (now - timedelta(minutes=1)).isoformat()},
            expected_version=1,
            reason="Cosmetic whitespace and unrelated billing update",
        ),
        "cosmetic-revision",
    )
    result = RetrievalService(env.db, env.embedder).recall(
        env.owner,
        RecallInput(
            query="T-0045 watch Gmail",
            mode="lexical",
            sort="recent",
            space_ids=[env.space],
        ),
    )
    assert [hit["memory_id"] for hit in result["hits"]] == [current["memory_id"], old["memory_id"]]
    assert result["hits"][1]["ranking"]["recency"]["at"] == old_date


def test_source_updates_retain_passage_age_with_the_original_source_identity(env, connected):
    service, connection, space, operator, identities = connected
    old_date = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    first = item(text="T-0045 watch by Gmail only.\nUnrelated status pending.")
    first.memory.metadata["source_modified_at"] = old_date
    saved = ingest(service, operator, space, first)["items"][0]["memory_id"]
    updated = first.model_copy(deep=True)
    updated.revision = "second-source-revision"
    updated.memory.content = "T-0045 watch by Gmail only.\nUnrelated status accepted."
    updated.memory.metadata["source_modified_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=1)
    ).isoformat()
    applied = ingest(service, operator, space, updated)
    assert applied["items"][0]["memory_id"] == saved
    result = RetrievalService(env.db, env.embedder).recall(
        identities["reader"][0],
        RecallInput(
            query="T-0045 Gmail",
            sort="recent",
            mode="lexical",
            all_accessible=True,
        ),
    )
    assert result["hits"][0]["ranking"]["recency"]["at"] == old_date


def test_recent_demotes_an_unrelated_newer_file_without_hiding_it(env):
    now = datetime.now(timezone.utc)
    answer = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(
            content="The Atlas scheduled routine for likes is created.",
            metadata={"source_modified_at": (now - timedelta(days=2)).isoformat()},
        ),
        "routine-answer",
    )
    weak = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(
            content="A routine README about pension options.",
            metadata={"source_modified_at": (now - timedelta(minutes=1)).isoformat()},
        ),
        "routine-readme",
    )
    while env.worker.run_once():
        pass
    service = RetrievalService(env.db, env.embedder)
    query = RecallInput(query="Atlas routine likes created", sort="recent", space_ids=[env.space])
    result = service.recall(env.owner, query)
    assert [hit["memory_id"] for hit in result["hits"]] == [answer["memory_id"], weak["memory_id"]]
    assert result["hits"][0]["ranking"]["recency"]["prioritized"]
    assert not result["hits"][1]["ranking"]["recency"]["prioritized"]
    assert "recent_weak_matches_demoted" in result["warnings"]
    strict = service.recall(
        env.owner,
        RecallInput(
            **{
                **query.model_dump(),
                "ranking_policy": {"recent_relevance_ratio": 0},
            }
        ),
    )
    assert strict["hits"][0]["memory_id"] == weak["memory_id"]
    assert {h["memory_id"]: h["relevance_score"] for h in result["hits"]} == {
        h["memory_id"]: h["relevance_score"] for h in strict["hits"]
    }


@pytest.mark.parametrize("sort", ["recent", "relevance"])
def test_identifier_question_finds_the_specific_decision_in_a_multitopic_row(env, sort):
    now = datetime.now(timezone.utc) - timedelta(hours=1)
    content = "| 2026-10-17T14:30:00Z | " + " ".join(
        [
            "(1) Billing settled.",
            "(2) Garden maintenance approved.",
            "(3) Coffee delivery booked.",
            "(4) Marisol: NO, settled; MESSAGE_MARISOL_v2 archived; T-0260 closed.",
            "(5) Atlas backup verified.",
            "(6) Kereis: CLOSED, no action.",
            "(7) T-0045 watch by Gmail only.",
            "(8) PostgreSQL restored. |",
        ]
    )
    target = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(
            content=content,
            metadata={"path": "LEDGER.md", "source_modified_at": now.isoformat()},
        ),
        "decision-row",
    )
    for index in range(8):
        env.memory.save(
            env.owner,
            env.space,
            MemoryInput(
                content=f"T-0260 waiting for a reply. Unrelated note {index}.",
                metadata={"source_modified_at": (now + timedelta(minutes=index)).isoformat()},
            ),
            f"unrelated-{index}",
        )
    while env.worker.run_once():
        pass
    result = RetrievalService(env.db, env.embedder).recall(
        env.owner,
        RecallInput(
            query="Marisol reply T-0260 closed settled",
            space_ids=[env.space],
            sort=sort,
            limit=4,
        ),
    )
    best = result["hits"][0]
    assert best["memory_id"] == target["memory_id"]
    assert best["ranking"]["identifier"]["matched"] == 1
    assert best["ranking"]["keywords"]["matched"] >= 3
    span = best["ranking"]["recency"]["span"]
    assert content[span["start"] : span["end"]].startswith("(4) Marisol:")
    assert best["relevance_score"] <= 1
    Recall.model_validate(result)


@pytest.mark.parametrize("method", ["search", "context", "start_evaluation"])
def test_new_ranking_defaults_do_not_break_sdk_calls_to_older_servers(method):
    from mnemion.sdk import Client, MnemionError
    from mnemion.service.models import RankingPolicy

    bodies = []

    def observe(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(503, json={"error": {"code": "fixture", "message": "Unavailable"}})

    with Client(
        "https://example.invalid", "fixture-key", transport=httpx.MockTransport(observe)
    ) as client:
        for policy in (
            {"recency_weight": 0},
            RankingPolicy(recency_weight=0),
            {"recent_relevance_ratio": 0},
        ):
            with pytest.raises(MnemionError):
                if method == "start_evaluation":
                    client.start_evaluation(
                        "00000000-0000-0000-0000-000000000001",
                        "00000000-0000-0000-0000-000000000002",
                        ranking_policy=policy,
                    )
                else:
                    getattr(client, method)(
                        "Atlas status", all_accessible=True, ranking_policy=policy
                    )
    assert all("recent_relevance_ratio" not in body["ranking_policy"] for body in bodies[:2])
    assert bodies[-1]["ranking_policy"]["recent_relevance_ratio"] == 0
    if method == "start_evaluation":
        assert all("sort" not in body for body in bodies)


def test_evaluation_records_recent_ordering_and_measures_its_effect(env):
    from mnemion.service.evaluation_models import DatasetInput, EvaluationInput
    from mnemion.service.evaluation_runner import EvaluationRunner
    from mnemion.service.evaluations import EvaluationService

    now = datetime.now(timezone.utc)
    answer = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(
            content="Atlas routine likes created",
            metadata={"source_modified_at": (now - timedelta(days=2)).isoformat()},
        ),
        "eval-current-answer",
    )
    env.memory.save(
        env.owner,
        env.space,
        MemoryInput(
            content="A routine README for pension documents.",
            metadata={"source_modified_at": (now - timedelta(minutes=1)).isoformat()},
        ),
        "eval-weak-recent",
    )
    while env.worker.run_once():
        pass
    service = EvaluationService(env.db, env.embedder)
    retrieval = RetrievalService(env.db, env.embedder)
    dataset = service.create_dataset(
        env.owner,
        env.space,
        DatasetInput(
            name="Recent relevance",
            cases=[
                {
                    "id": "routine",
                    "query": "Atlas routine likes created",
                    "references": [{"memory_id": answer["memory_id"]}],
                }
            ],
        ),
    )
    for ratio, expected in ((0, 0), (0.7, 1)):
        created = service.create_run(
            env.owner,
            env.space,
            EvaluationInput(
                dataset_id=UUID(dataset["id"]),
                cutoffs=[1],
                sort="recent",
                ranking_policy={"recent_relevance_ratio": ratio},
            ),
            f"recent-eval-{ratio}",
        )
        assert EvaluationRunner(env.db, retrieval).run_once()
        run = service.run(env.owner, env.space, UUID(created["id"]))
        assert run["state"] == "completed"
        assert run["configuration"]["sort"] == "recent"
        assert run["configuration"]["ranking_policy"]["recent_relevance_ratio"] == ratio
        assert "passage_time" in run["manifest"]["retrieval"]
        result = service.results(env.owner, env.space, UUID(run["id"]))["items"][0]["result"]
        assert result["metrics"]["1"]["recall"] == expected
        assert result["ranking"][0]["ranking"]["recency"]["at"]


def test_chronology_bound_and_malformed_stored_dates_fall_back_without_exposing_extra_text():
    text = "Atlas note\n" * 3000
    result = select(text, capture(text, {}, NOW), {}, NOW, "Atlas", recent=True)
    assert result["limited"] and result["at"] == NOW
    assert set(result).isdisjoint({"content", "text", "tokens"})
    for value in (
        {"version": True, "segments": []},
        {"version": 1, "segments": [[0, 5, NOW.isoformat(), []]]},
        {"version": 1, "segments": [[0, 1000, NOW.isoformat(), "recorded_at"]]},
    ):
        assert select("Atlas", value, {}, NOW, "Atlas", recent=True)["at"] == NOW
