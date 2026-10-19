"""Real PostgreSQL ordering checks; the fixture model is not a quality benchmark."""

from datetime import datetime, timedelta, timezone

import httpx
import json
import pytest
from pydantic import ValidationError

from mnemion.sdk import Client, MnemionError
from mnemion.service.contracts import Recall
from mnemion.service.models import MemoryInput, RankingPolicy, RecallInput
from mnemion.service.ranking import adjustment
from mnemion.service.retrieval import RetrievalService


def save(env, text, path, date):
    return env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content=text, metadata={"path": path, "source_modified_at": date.isoformat()}),
        path,
    )["memory_id"]


def test_recency_blends_relevance_without_adding_unrelated_fresh_memories(env):
    now = datetime.now(timezone.utc)
    old = save(env, "billing " * 40, "old.md", now - timedelta(days=14))
    current = save(env, "billing decision accepted", "current.md", now)
    unrelated = save(env, "orchard planning", "unrelated.md", now)
    service = RetrievalService(env.db, env.embedder)
    command = RecallInput(query="billing", space_ids=[env.space], mode="lexical")
    pure = service.recall(
        env.owner,
        command.model_copy(
            update={
                "ranking_policy": RankingPolicy(recency_weight=0, archive_weight=1),
            }
        ),
    )
    blended = service.recall(env.owner, command)
    assert [h["memory_id"] for h in pure["hits"]] == [old, current]
    assert [h["memory_id"] for h in blended["hits"]] == [current, old]
    assert unrelated not in {h["memory_id"] for h in blended["hits"]}
    assert {h["memory_id"]: h["relevance_score"] for h in pure["hits"]} == {
        h["memory_id"]: h["relevance_score"] for h in blended["hits"]
    }
    assert all(0.75 <= h["ranking"]["adjustment"]["recency_factor"] <= 1 for h in blended["hits"])
    Recall.model_validate(blended)


def test_archived_identifier_labels_yield_to_current_answer_and_can_be_restored(env):
    now = datetime.now(timezone.utc)
    archive = save(env, "TASK-7312 billing pending", r"ops\ARCHIVES\TASK-7312.md", now)
    current = save(
        env, "TASK-7312 billing accepted and closed", "ops/DONE.md", now - timedelta(hours=1)
    )
    service = RetrievalService(env.db, env.embedder)
    command = RecallInput(query="TASK-7312 billing", space_ids=[env.space], mode="lexical")
    result = service.recall(env.owner, command)
    assert [h["memory_id"] for h in result["hits"]] == [current, archive]
    assert result["hits"][1]["ranking"]["adjustment"]["archive_segment"] == "archives"
    assert result["hits"][0]["ranking"]["adjustment"]["archive_segment"] is None
    pure = service.recall(
        env.owner,
        command.model_copy(
            update={
                "ranking_policy": RankingPolicy(recency_weight=0, archive_weight=1),
            }
        ),
    )
    assert pure["hits"][0]["memory_id"] == archive
    date_order = service.recall(env.owner, command.model_copy(update={"sort": "recent"}))
    assert [hit["memory_id"] for hit in date_order["hits"]] == [current, archive]
    assert date_order["hits"][1]["ranking"]["archive"] == {
        "archive_factor": 0.35,
        "archive_segment": "archives",
        "demoted": True,
    }
    assert date_order["hits"][1]["ranking"]["recency"]["at"] == now.isoformat()
    assert "recent_archived_matches_demoted" in date_order["warnings"]
    assert "adjustment" not in date_order["hits"][0]["ranking"]
    for policy in (RankingPolicy(archive_weight=1), RankingPolicy(recent_relevance_ratio=0)):
        historical = service.recall(
            env.owner,
            command.model_copy(update={"sort": "recent", "ranking_policy": policy}),
        )
        assert historical["hits"][0]["memory_id"] == archive
        assert "recent_archived_matches_demoted" not in historical["warnings"]


@pytest.mark.parametrize("indexed", [False, True])
@pytest.mark.parametrize("archive_weight", [0, 0.35])
def test_recent_archive_preference_preserves_strong_history_ahead_of_weak_fresh_notes(
    env, indexed, archive_weight
):
    now = datetime.now(timezone.utc)
    old = save(env, "TASK-7312 billing completed", "archive/first.md", now - timedelta(days=10))
    latest = save(env, "TASK-7312 billing completed", "archive/final.md", now - timedelta(days=5))
    fresh = save(env, "billing unrelated revision", "README.md", now)
    if indexed:
        while env.worker.run_once():
            pass
    result = RetrievalService(env.db, env.embedder).recall(
        env.owner,
        RecallInput(
            query="TASK-7312 billing completed",
            space_ids=[env.space],
            sort="recent",
            ranking_policy=RankingPolicy(archive_weight=archive_weight),
        ),
    )
    assert [hit["memory_id"] for hit in result["hits"][:2]] == [latest, old]
    assert all(not hit["ranking"]["archive"]["demoted"] for hit in result["hits"][:2])
    assert "recent_archived_matches_demoted" not in result["warnings"]
    if indexed:
        assert fresh in {hit["memory_id"] for hit in result["hits"][2:]}
        assert "semantic_index_incomplete" not in result["warnings"]
    else:
        assert "semantic_index_incomplete" in result["warnings"]


@pytest.mark.parametrize("indexed", [False, True])
def test_recent_archive_preference_works_before_indexing_and_retains_score_filters(env, indexed):
    now = datetime.now(timezone.utc)
    archived = save(env, "CASE-7319 calendar delegate prefect", "archive/CASE-7319.md", now)
    current = save(
        env,
        "CASE-7319 calendar delegate prefect adopted",
        "reports/final.md",
        now - timedelta(minutes=2),
    )
    if indexed:
        while env.worker.run_once():
            pass
    service = RetrievalService(env.db, env.embedder)
    command = RecallInput(
        query="CASE-7319 calendar delegate prefect", space_ids=[env.space], sort="recent"
    )
    result = service.recall(env.owner, command)
    assert [hit["memory_id"] for hit in result["hits"]] == [current, archived]
    strict = service.recall(
        env.owner,
        command.model_copy(update={"ranking_policy": RankingPolicy(recent_relevance_ratio=0)}),
    )
    assert [hit["memory_id"] for hit in strict["hits"]] == [archived, current]
    assert {hit["memory_id"]: hit["relevance_score"] for hit in result["hits"]} == {
        hit["memory_id"]: hit["relevance_score"] for hit in strict["hits"]
    }
    threshold = result["hits"][0]["relevance_score"] + 0.00001
    filtered = service.recall(env.owner, command.model_copy(update={"min_score": threshold}))
    assert current not in {hit["memory_id"] for hit in filtered["hits"]}


def test_rank_threshold_preserves_archived_evidence_and_uses_historical_reference(env):
    now = datetime.now(timezone.utc)
    archived = save(env, "billing", "archive/record.md", now)
    reference = now + timedelta(days=365)
    command = RecallInput(
        query="billing", space_ids=[env.space], mode="lexical", min_score=0.99, known_at=reference
    )
    result = RetrievalService(env.db, env.embedder).recall(env.owner, command)
    assert result["hits"][0]["memory_id"] == archived
    hit = result["hits"][0]
    assert hit["relevance_score"] == 1
    assert hit["ranking"]["adjustment"]["score"] == pytest.approx(0.75)
    assert hit["ranking"]["adjustment"]["archive_uncontested"]
    assert hit["ranking"]["adjustment"]["age_days"] == 365
    assert result["ranking_reference_time"] == reference.isoformat()


def test_only_literal_historical_record_stays_ahead_of_generic_semantic_neighbors(env):
    now = datetime.now(timezone.utc)
    archived = save(
        env, "CASE-6510 cobalt invoice approved", "archive/old.md", now - timedelta(days=5)
    )
    noise = save(env, "billing", "notes/fresh.md", now)
    while env.worker.run_once():
        pass
    service = RetrievalService(env.db, env.embedder)
    command = RecallInput(query="CASE-6510 cobalt invoice", space_ids=[env.space])
    result = service.recall(env.owner, command)
    assert [hit["memory_id"] for hit in result["hits"]] == [archived, noise]
    assert result["hits"][0]["ranking"]["adjustment"]["archive_uncontested"]
    assert result["hits"][0]["ranking"]["adjustment"]["configured_archive_factor"] == 0.35
    # An explicit zero weight keeps its documented relevance-order behavior.
    suppressed = service.recall(
        env.owner, command.model_copy(update={"ranking_policy": RankingPolicy(archive_weight=0)})
    )
    assert [hit["memory_id"] for hit in suppressed["hits"]] == [noise, archived]


@pytest.mark.parametrize(
    "path,segments,matched",
    [
        ("archive/result.md", ["archive"], "archive"),
        (r"ops\ARCHIVES\result.md", ["archives"], "archives"),
        ("ops/done/result.md", ["archive", "archives"], None),
        ("ops/my-archive/result.md", ["archive"], None),
        ("ops/archive", ["archive"], None),
        ("ops/retired/result.md", ["retired"], "retired"),
        ("ops/re\u0301sume\u0301/result.md", ["RÉSUMÉ"], "résumé"),
        ("archive/result.md", [], None),
    ],
)
def test_archive_matching_is_literal_directory_based_and_future_dates_cannot_gain_extra_weight(
    path, segments, matched
):
    now = datetime.now(timezone.utc)
    result = adjustment(
        0.5, now + timedelta(days=365), path, now, RankingPolicy(archive_path_segments=segments)
    )
    assert result["archive_segment"] == matched
    assert result["age_days"] == 0 and result["recency_factor"] == 1
    assert result["score"] <= 0.5


@pytest.mark.parametrize(
    "options",
    [
        {"recency_weight": float("nan")},
        {"archive_weight": float("inf")},
        {"recency_weight": -0.1},
        {"archive_weight": 1.1},
        {"half_life_days": 0},
        {"archive_path_segments": ["archive/"]},
        {"archive_path_segments": [" "]},
        {"archive_path_segments": ["a" * 129]},
        {"archive_path_segments": ["archive"] * 17},
        {"unrecognized": True},
    ],
)
def test_ranking_policy_rejects_invalid_or_unbounded_preferences(options):
    with pytest.raises(ValidationError):
        RankingPolicy(**options)


@pytest.mark.parametrize("method", ["search", "context"])
def test_sdk_omits_new_policy_on_old_servers_unless_the_caller_requests_it(method):
    bodies = []

    def unavailable(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(
            503, json={"error": {"code": "fixture_unavailable", "message": "Unavailable"}}
        )

    with Client(
        "https://example.invalid", "fixture-key", transport=httpx.MockTransport(unavailable)
    ) as client:
        for options in (
            {},
            {
                "ranking_policy": {"recency_weight": 0, "archive_weight": 1},
                "keyword_fallback": False,
            },
        ):
            with pytest.raises(MnemionError):
                getattr(client, method)("billing", all_accessible=True, **options)
    assert "ranking_policy" not in bodies[0]
    assert "keyword_fallback" not in bodies[0]
    assert bodies[-1]["ranking_policy"]["recency_weight"] == 0
    assert bodies[-1]["ranking_policy"]["archive_weight"] == 1
    assert bodies[-1]["keyword_fallback"] is False
