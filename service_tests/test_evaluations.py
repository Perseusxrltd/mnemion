"""Real service evidence, test-set isolation, scoring, leases and erasure."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import threading
from uuid import UUID

import psycopg
import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from mnemion.service.api import create_app
from mnemion.service.errors import ServiceError
from mnemion.service.evaluation_metrics import ranking_metrics, wilson
from mnemion.service.evaluation_models import (
    AssessmentInput,
    DatasetInput,
    EvaluationInput,
    EvaluationPage,
    EvaluationRun,
)
from mnemion.service.evaluation_runner import EvaluationRunner
from mnemion.service.evaluations import EvaluationService
from mnemion.service.models import GrantInput, KeyInput, MemoryInput, PrincipalInput, RecallInput
from mnemion.service.retrieval import RetrievalService


@pytest.mark.parametrize(
    "options",
    [
        {"cutoffs": [True]},
        {"cutoffs": [1.0]},
        {"cutoffs": ["5"]},
        {"context": "false"},
        {"token_budget": 512.0},
        {"max_seconds": "300"},
        {"interval_seconds": True},
        {"keyword_fallback": "false"},
    ],
)
def test_run_options_do_not_silently_coerce_resource_or_scoring_settings(options):
    with pytest.raises(ValidationError):
        EvaluationInput.model_validate(
            {"dataset_id": "00000000-0000-0000-0000-000000000001", **options}
        )


def test_history_pages_are_stable_compact_and_bound_to_their_space(env):
    service, dataset, _ = setup(env)
    for index in range(4):
        service.create_dataset(
            env.owner,
            env.space,
            DatasetInput.model_validate(
                {
                    "name": f"Page {index}",
                    "cases": [{"id": "absent", "query": "No source", "unanswerable": True}],
                }
            ),
        )
    first = service.datasets(env.owner, env.space, limit=2)
    assert first["next_cursor"] and len(first["items"]) == 2
    assert all(row["cases"] is None and row["case_count"] == 1 for row in first["items"])
    second = service.datasets(env.owner, env.space, cursor=first["next_cursor"], limit=2)
    third = service.datasets(env.owner, env.space, cursor=second["next_cursor"], limit=2)
    assert third["next_cursor"] is None
    rows = first["items"] + second["items"] + third["items"]
    assert len({row["id"] for row in rows}) == 5
    original = next(row for row in rows if row["id"] == dataset["id"])
    assert original["development_count"] == 3 and original["held_out_count"] == 1
    from uuid import uuid4
    from mnemion.service.evaluations import history_page

    for bad in ("!bad", "bm90LWpzb24=", "W10="):
        with pytest.raises(ServiceError) as error:
            service.datasets(env.owner, env.space, cursor=bad)
        assert error.value.status == 422
    with pytest.raises(ServiceError):
        history_page(uuid4(), first["next_cursor"], 2, 200)
    ids = []
    for index in range(3):
        run = service.create_run(
            env.owner,
            env.space,
            EvaluationInput(dataset_id=UUID(dataset["id"])),
            f"history-{index}",
        )
        ids.append(run["id"])
        service.cancel(env.owner, env.space, UUID(run["id"]))
    first_runs = service.runs(env.owner, env.space, limit=2)
    assert first_runs["next_cursor"] and all(
        "selected_cases" not in row["manifest"] for row in first_runs["items"]
    )
    second_runs = service.runs(env.owner, env.space, cursor=first_runs["next_cursor"], limit=2)
    assert second_runs["next_cursor"] is None
    assert {row["id"] for row in first_runs["items"] + second_runs["items"]} == set(ids)
    assert service.run(env.owner, env.space, UUID(ids[0]))["manifest"]["selected_cases"]
    service.remove_dataset(env.owner, env.space, UUID(dataset["id"]))
    assert all(row["state"] == "invalidated" for row in service.runs(env.owner, env.space)["items"])


def setup(env):
    records = [
        env.memory.save(env.owner, env.space, MemoryInput(content=text), "eval-" + str(i))
        for i, text in enumerate(
            ("Postgres stores billing data", "The garden needs coffee compost")
        )
    ]
    while env.worker.run_once():
        pass
    service = EvaluationService(env.db, env.embedder)
    refs = [{"memory_id": row["memory_id"]} for row in records]
    dataset = service.create_dataset(
        env.owner,
        env.space,
        DatasetInput.model_validate(
            {
                "name": "Retrieval fixture",
                "cases": [
                    {"id": "billing", "query": "Postgres", "references": refs[:1]},
                    {"id": "combined", "query": "Postgres", "references": refs},
                    {"id": "absent", "query": "UNINDEXED_EVALUATION_SECRET", "unanswerable": True},
                    {"id": "held", "query": "garden", "references": refs[1:], "split": "held_out"},
                ],
            }
        ),
    )
    return service, dataset, records


def execute(env, service, dataset, key="run", **options):
    config = EvaluationInput(
        dataset_id=UUID(dataset["id"]), modes=["lexical", "semantic"], cutoffs=[1, 2], **options
    )
    run = service.create_run(env.owner, env.space, config, key)
    runner = EvaluationRunner(env.db, RetrievalService(env.db, env.embedder))
    for _ in range(run["total"] + 1):
        if not runner.run_once():
            break
    return service.run(env.owner, env.space, UUID(run["id"])), runner


def test_ranking_metrics_do_not_count_duplicates_and_report_absence_honestly():
    scores = ranking_metrics(["one", "one"], {"one": 1, "two": 1}, 2)
    assert scores["recall"] == 0.5 and scores["precision"] == 0.5
    assert scores["ndcg"] == pytest.approx(0.6131471927654584)
    assert not scores["complete"]
    assert ranking_metrics(["unrelated"], {}, 10)["recall"] is None
    assert wilson(45, 45)[0] < 0.93 and wilson(0, 0) is None


def test_a_hotfix_cannot_mix_service_versions_inside_one_new_evaluation(env, monkeypatch):
    from mnemion.service import evaluation_runner

    service, dataset, _ = setup(env)
    run = service.create_run(
        env.owner, env.space, EvaluationInput(dataset_id=UUID(dataset["id"])), "versioned-run"
    )
    runner = EvaluationRunner(env.db, RetrievalService(env.db, env.embedder))
    assert runner.run_once()
    initial = service.run(env.owner, env.space, UUID(run["id"]))
    assert initial["state"] == "running" and initial["progress"] == 1
    assert initial["manifest"]["execution"]["service_version"] == evaluation_runner.__version__
    monkeypatch.setattr(evaluation_runner, "__version__", "99.0.0")
    assert runner.run_once()
    final = service.run(env.owner, env.space, UUID(run["id"]))
    assert final["state"] == "failed" and final["error_code"] == "evaluation_error"
    assert final["progress"] == 1


def test_sdk_keeps_new_evaluation_options_optional_for_older_services():
    from mnemion.sdk import Client, MnemionError

    bodies = []

    def unavailable(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(503, json={"error": {"code": "fixture", "message": "Unavailable"}})

    with Client(
        "https://example.invalid",
        "fixture-key",
        retries=0,
        transport=httpx.MockTransport(unavailable),
    ) as client:
        for options in ({}, {"keyword_fallback": False, "ranking_policy": {"recency_weight": 0}}):
            with pytest.raises(MnemionError):
                client.start_evaluation(
                    "00000000-0000-0000-0000-000000000001",
                    "00000000-0000-0000-0000-000000000002",
                    **options,
                )
    assert "keyword_fallback" not in bodies[0] and "ranking_policy" not in bodies[0]
    assert bodies[-1]["keyword_fallback"] is False
    assert bodies[-1]["ranking_policy"]["recency_weight"] == 0


def test_versioned_labels_stay_out_of_retrieval_and_runs_have_real_denominators(env):
    service, dataset, records = setup(env)
    assert dataset["case_count"] == 4 and dataset["development_count"] == 3
    assert dataset["cases"][0]["references"][0]["revision_id"] == records[0]["revision_id"]
    recall = RetrievalService(env.db, env.embedder).recall(
        env.owner,
        RecallInput(query="UNINDEXED_EVALUATION_SECRET", space_ids=[env.space], mode="lexical"),
    )
    assert recall["hits"] == []
    run, _ = execute(env, service, dataset)
    EvaluationRun.model_validate(run)
    assert run["state"] == "completed" and run["progress"] == run["total"] == 6
    assert run["manifest"]["corpus_changed"] is False and run["manifest"]["frozen_manifest_hash"]
    lexical = run["summary"]["modes"]["lexical"]
    assert lexical["answerable"] == 2 and lexical["unanswerable"] == 1
    assert lexical["metrics"]["2"]["recall"] == 0.75
    assert lexical["metrics"]["1"]["n"] == 2
    assert lexical["citation_validity"] == 1 and lexical["context_recall"] == 0.75
    assert run["summary"]["modes"]["semantic"]["metrics"]["2"]["recall"] == 1
    page = service.results(env.owner, env.space, UUID(run["id"]), limit=2)
    EvaluationPage.model_validate(page)
    assert len(page["items"]) == 2 and page["next_cursor"] == 2
    assert "UNINDEXED_EVALUATION_SECRET" not in json.dumps(page)
    exported = json.loads(service.export(env.owner, env.space, UUID(run["id"]), format="json"))
    assert len(exported["results"]) == 6 and exported["dataset"]["cases"][2]["unanswerable"]
    assert b"recall,precision,ndcg" in service.export(
        env.owner, env.space, UUID(run["id"]), format="csv"
    )


def test_runs_replay_requests_compare_pairs_and_detect_corpus_changes(env):
    service, dataset, _ = setup(env)
    first, _ = execute(env, service, dataset, key="first")
    replay = service.create_run(
        env.owner,
        env.space,
        EvaluationInput(
            dataset_id=UUID(dataset["id"]), modes=["lexical", "semantic"], cutoffs=[1, 2]
        ),
        "first",
    )
    assert replay["id"] == first["id"]
    with pytest.raises(ServiceError) as conflict:
        service.create_run(
            env.owner, env.space, EvaluationInput(dataset_id=UUID(dataset["id"])), "first"
        )
    assert conflict.value.code == "idempotency_conflict"
    second, _ = execute(env, service, dataset, key="second")
    comparison = service.compare(env.owner, env.space, UUID(first["id"]), UUID(second["id"]))
    assert comparison["comparable"] and all(delta["delta"] == 0 for delta in comparison["deltas"])
    run = service.create_run(
        env.owner,
        env.space,
        EvaluationInput(dataset_id=UUID(dataset["id"]), cutoffs=[1, 2]),
        "drift",
    )
    runner = EvaluationRunner(env.db, RetrievalService(env.db, env.embedder))
    assert runner.run_once()
    env.memory.save(env.owner, env.space, MemoryInput(content="A new distractor"), "drift-write")
    while runner.run_once():
        pass
    changed = service.run(env.owner, env.space, UUID(run["id"]))
    assert changed["manifest"]["corpus_changed"]
    assert not service.compare(env.owner, env.space, UUID(first["id"]), UUID(run["id"]))[
        "comparable"
    ]


def test_cancellation_during_retrieval_fences_publication(env):
    service, dataset, _ = setup(env)
    run = service.create_run(
        env.owner, env.space, EvaluationInput(dataset_id=UUID(dataset["id"])), "cancel"
    )
    retrieval = RetrievalService(env.db, env.embedder)
    entered, release = threading.Event(), threading.Event()
    original = retrieval.recall

    def waiting(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return original(*args, **kwargs)

    retrieval.recall = waiting
    runner = EvaluationRunner(env.db, retrieval)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(runner.run_once)
        try:
            assert entered.wait(2)
            assert service.cancel(env.owner, env.space, UUID(run["id"]))["state"] == "cancelled"
        finally:
            release.set()
        assert future.result(timeout=3)
    assert service.results(env.owner, env.space, UUID(run["id"]))["items"] == []


def test_revoked_initiator_and_expired_lease_cannot_continue(env):
    service, dataset, _ = setup(env)
    key = env.identities.create_key(
        env.owner, env.owner.principal_id, KeyInput(name="evaluation initiator")
    )
    identity = env.db.authenticate(key["api_key"])
    run = service.create_run(
        identity, env.space, EvaluationInput(dataset_id=UUID(dataset["id"])), "revoked"
    )
    runner = EvaluationRunner(env.db, RetrievalService(env.db, env.embedder))
    assert runner.run_once()
    env.identities.revoke_key(env.owner, identity.key_id)
    assert runner.run_once()
    ended = service.run(env.owner, env.space, UUID(run["id"]))
    assert ended["state"] == "failed" and ended["error_code"] == "access_revoked"
    run = service.create_run(
        env.owner, env.space, EvaluationInput(dataset_id=UUID(dataset["id"])), "lease"
    )
    first = EvaluationRunner(env.db, RetrievalService(env.db, env.embedder))
    assert first.run_once()
    stale = dict(first._job)
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            "UPDATE mnemion.evaluation_runs SET lease_until=now()-interval '1 second' WHERE id=%s",
            (UUID(run["id"]),),
        )
    replacement = EvaluationRunner(env.db, RetrievalService(env.db, env.embedder))
    assert replacement.run_once()
    first._step(stale)
    assert first._job is None
    while replacement.run_once():
        pass
    assert service.run(env.owner, env.space, UUID(run["id"]))["state"] == "completed"


def test_reference_erasure_removes_labels_results_assessment_and_blocks_http_reader(
    env, monkeypatch
):
    service, dataset, records = setup(env)
    run, _ = execute(env, service, dataset)
    run_id = UUID(run["id"])
    result = service.results(env.owner, env.space, run_id)["items"][0]
    assessed = service.assess(
        env.owner,
        env.space,
        run_id,
        0,
        AssessmentInput(
            expected_recorded_at=datetime.fromisoformat(result["recorded_at"]),
            label="useful",
            note="PRIVATE_REVIEW",
        ),
    )
    assert assessed["assessment_version"] == 1
    with pytest.raises(ServiceError) as conflict:
        service.assess(
            env.owner,
            env.space,
            run_id,
            0,
            AssessmentInput(
                expected_recorded_at=datetime.fromisoformat(result["recorded_at"]),
                label="not_useful",
            ),
        )
    assert conflict.value.code == "assessment_changed"
    principal = env.identities.create_principal(env.owner, PrincipalInput(name="reader"))
    key = env.identities.create_key(env.owner, UUID(principal["id"]), KeyInput(name="reader"))
    env.identities.grant(env.owner, env.space, UUID(principal["id"]), GrantInput(role="reader"))
    monkeypatch.setenv("MNEMION_EVALUATIONS_DISABLED", "1")
    with TestClient(create_app(env.db, env.embedder)) as client:
        path = f"/v1/spaces/{env.space}/evaluations/runs/{run_id}"
        assert (
            client.get(path, headers={"Authorization": "Bearer " + key["api_key"]}).status_code
            == 403
        )
        response = client.get(path, headers={"Authorization": "Bearer " + env.token})
        assert response.status_code == 200, response.text
    env.memory.forget(
        env.owner, UUID(records[0]["memory_id"]), expected_version=1, key="delete-reference"
    )
    assert service.run(env.owner, env.space, run_id)["state"] == "invalidated"
    assert service.run(env.owner, env.space, run_id)["summary"] is None
    assert service.results(env.owner, env.space, run_id)["items"] == []
    assert service.dataset(env.owner, env.space, UUID(dataset["id"]))["cases"] == []
    while env.worker.run_once():
        pass
    with psycopg.connect(env.admin_dsn) as conn:
        cases = conn.execute(
            "SELECT cases FROM mnemion.evaluation_datasets WHERE id=%s", (UUID(dataset["id"]),)
        ).fetchone()[0]
        assert cases == []
        assert (
            conn.execute(
                "SELECT count(*) FROM mnemion.evaluation_results WHERE run_id=%s", (run_id,)
            ).fetchone()[0]
            == 0
        )
    assert "PRIVATE_REVIEW" not in json.dumps(service.run(env.owner, env.space, run_id))
