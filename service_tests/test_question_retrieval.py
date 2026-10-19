"""Question fallback uses real authorized PostgreSQL candidates, never model claims."""

from datetime import datetime, timezone
from uuid import UUID

import psycopg
import pytest

from mnemion.service.connector_models import ScopeInput, utc_now
from mnemion.service.errors import ServiceError
from mnemion.service.models import ContextInput, MemoryInput, RecallInput, ReviewInput
from mnemion.service.retrieval import RetrievalService
from service_tests.test_connectors import connected as connected
from service_tests.test_connectors import ingest, item


@pytest.fixture
def question_case(env):
    target = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(
            content="Projet Atlas : les sauvegardes restent au bureau de Stockholm. postgres",
            subject="Atlas sauvegardes",
        ),
        "atlas-backups",
    )
    env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="The unrelated pension review is complete."),
        "unrelated-review",
    )
    while env.worker.run_once():
        pass
    return RetrievalService(env.db, env.embedder), target


def test_question_terms_support_semantic_search_without_claiming_full_match(env, question_case):
    service, target = question_case
    command = RecallInput(
        query="Where will we keep the Atlas backup copy?",
        space_ids=[env.space],
        keyword_fallback=False,
        ranking_policy={"recency_weight": 0, "archive_weight": 1},
    )
    before = service.recall(env.owner, command)
    assert before["hits"][0]["memory_id"] != target["memory_id"]
    result = service.recall(env.owner, command.model_copy(update={"keyword_fallback": True}))
    best = result["hits"][0]
    assert best["memory_id"] == target["memory_id"]
    assert best["ranking"]["keywords"]["terms"] == ["atlas"]
    assert best["ranking"]["keywords"]["matched"] == 1
    assert best["ranking"]["keywords"]["requested"] > 1
    assert best["relevance_score"] <= 0.75
    assert result["match_status"] == "semantic_only"
    assert "partial_keyword_support" in result["warnings"]
    assert "semantic_matches_require_evidence_review" in result["warnings"]
    assert "lexical" not in best["ranking"]["ranks"]
    assert best["evidence"]["excerpt"] == best["text"]
    context = service.context(
        env.owner,
        ContextInput(**command.model_dump(exclude={"keyword_fallback"}), keyword_fallback=True),
    )
    assert context["citations"][0]["memory_id"] == target["memory_id"]


def test_partial_terms_do_not_bypass_similarity_or_relevance_filters(env, question_case):
    service, target = question_case
    command = RecallInput(
        query="Where will we keep the Atlas backup copy?",
        space_ids=[env.space],
        keyword_fallback=True,
    )
    for controls in ({"min_similarity": 0.99}, {"min_score": 0.9}):
        result = service.recall(env.owner, command.model_copy(update=controls))
        assert target["memory_id"] not in {hit["memory_id"] for hit in result["hits"]}


@pytest.mark.parametrize(
    "query",
    [
        '"Atlas backup copy"',
        "Atlas backup -copy",
        "Atlas OR backup copy",
        "Atlas backup",
        "Atlas " * 40,
    ],
)
def test_explicit_syntax_and_query_budgets_keep_existing_channels(env, question_case, query):
    service, _ = question_case
    result = service.recall(
        env.owner, RecallInput(query=query, space_ids=[env.space], keyword_fallback=True)
    )
    assert "partial_keyword_support" not in result["warnings"]
    assert all("keywords" not in hit["ranking"] for hit in result["hits"])


@pytest.mark.parametrize("mode", ["lexical", "semantic"])
def test_explicit_search_mode_is_not_reinterpreted(env, question_case, mode):
    service, _ = question_case
    result = service.recall(
        env.owner,
        RecallInput(
            query="Where will we keep the Atlas backup copy?",
            space_ids=[env.space],
            mode=mode,
            keyword_fallback=True,
        ),
    )
    assert "partial_keyword_support" not in result["warnings"]
    assert all("keywords" not in hit["ranking"] for hit in result["hits"])


def test_full_lexical_match_keeps_its_original_priority(env, question_case):
    service, _ = question_case
    command = RecallInput(
        query="Atlas les sauvegardes",
        space_ids=[env.space],
        known_at=datetime.now(timezone.utc),
        keyword_fallback=False,
    )
    before = service.recall(env.owner, command)
    after = service.recall(env.owner, command.model_copy(update={"keyword_fallback": True}))
    assert before["hits"] == after["hits"]
    assert "partial_keyword_support" not in after["warnings"]


@pytest.mark.parametrize("change", ["expired", "mapping", "paused", "quarantined"])
def test_question_candidates_follow_current_source_authority(env, connected, change):
    sources, connection, space, operator, identities = connected
    saved = ingest(sources, operator, space, item(text="Atlas backup copy"))
    memory = saved["items"][0]["memory_id"]
    query = "Where will we keep the Atlas backup copy?"
    env.memory.save(env.owner, env.space, MemoryInput(content=query), "private-full-match")
    while env.worker.run_once():
        pass
    service = RetrievalService(env.db, env.embedder)
    reader = identities["reader"][0]
    command = RecallInput(query=query, all_accessible=True)
    result = service.recall(reader, command)
    assert [hit["memory_id"] for hit in result["hits"]] == [memory]
    assert "partial_keyword_support" in result["warnings"]
    assert result["hits"][0]["ranking"]["keywords"]["rank"] == 1
    assert result["index"]["eligible_records"] == 1
    if change == "expired":
        with psycopg.connect(env.admin_dsn) as conn:
            conn.execute(
                "UPDATE mnemion.connector_scopes SET access_valid_until=now()-interval '1 second' WHERE space_id=%s",
                (space,),
            )
    elif change == "mapping":
        sources.refresh_scope(
            operator,
            connection,
            ScopeInput(
                external_id="channel:C_PRIVATE",
                name="Private channel",
                members=["U_reviewer"],
                observed_at=utc_now(),
            ),
        )
    elif change == "paused":
        sources.suspend(operator, space, "operator_paused")
    else:
        env.memory.review(
            identities["reviewer"][0],
            UUID(memory),
            ReviewInput(expected_version=1, state="quarantined", reason="Review required"),
        )
    assert service.recall(reader, command)["hits"] == []
    context = service.context(reader, ContextInput(query=query, all_accessible=True))
    assert context["citations"] == []


def test_busy_keyword_only_mode_does_not_silently_use_partial_terms(
    env, question_case, monkeypatch
):
    service, _ = question_case

    def busy(_):
        raise ServiceError(503, "inference_busy", "Model is busy")

    monkeypatch.setattr(env.embedder, "query", busy)
    result = service.recall(
        env.owner,
        RecallInput(
            query="Where will we keep the Atlas backup copy?",
            space_ids=[env.space],
            on_inference_busy="lexical",
        ),
    )
    assert result["hits"] == []
    assert "inference_busy_lexical_only" in result["warnings"]
    assert "partial_keyword_support" not in result["warnings"]


def test_evaluations_keep_question_and_ranking_settings_and_compare_their_results(
    env, question_case
):
    from mnemion.service.evaluation_models import DatasetInput, EvaluationInput
    from mnemion.service.evaluation_runner import EvaluationRunner
    from mnemion.service.evaluations import EvaluationService
    from mnemion.version import __version__

    retrieval, target = question_case
    service = EvaluationService(env.db, env.embedder)
    dataset = service.create_dataset(
        env.owner,
        env.space,
        DatasetInput(
            name="Question retrieval",
            cases=[
                {
                    "id": "atlas",
                    "query": "Where will we keep the Atlas backup copy?",
                    "references": [{"memory_id": target["memory_id"]}],
                }
            ],
        ),
    )
    runs = []
    for enabled in (False, True):
        run = service.create_run(
            env.owner,
            env.space,
            EvaluationInput(
                dataset_id=UUID(dataset["id"]),
                cutoffs=[1],
                keyword_fallback=enabled,
                ranking_policy={"recency_weight": 0, "archive_weight": 1},
            ),
            f"question-eval-{enabled}",
        )
        runner = EvaluationRunner(env.db, retrieval)
        assert runner.run_once()
        run = service.run(env.owner, env.space, UUID(run["id"]))
        assert run["state"] == "completed"
        assert run["configuration"]["keyword_fallback"] is enabled
        assert run["manifest"]["configuration"]["ranking_policy"]["recency_weight"] == 0
        assert run["manifest"]["execution"]["service_version"] == __version__
        result = service.results(env.owner, env.space, UUID(run["id"]))["items"][0]["result"]
        assert result["metrics"]["1"]["recall"] == int(enabled)
        assert result["ranking_reference_time"]
        assert ("partial_keyword_support" in result["warnings"]) is enabled
        runs.append(run)
    comparison = service.compare(env.owner, env.space, UUID(runs[0]["id"]), UUID(runs[1]["id"]))
    assert comparison["comparable"]
    assert next(row for row in comparison["deltas"] if row["metric"] == "recall")["delta"] == 1
