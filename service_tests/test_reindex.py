"""Live PostgreSQL reindex tests preserve search, history and tenant boundaries."""

from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from mnemion.service.admin import register_generation
from mnemion.service.api import create_app
from mnemion.service.embedding_api import ReindexInput
from mnemion.service.embeddings import EmbeddedChunk, Generation
from mnemion.service.errors import ServiceError
from mnemion.service.model_registry import ModelRegistry
from mnemion.service.model_worker import ModelWorker
from mnemion.service.models import MemoryInput, RecallInput, RevisionInput
from mnemion.service.reindex import ReindexBackfill, ReindexService
from mnemion.service.retrieval import RetrievalService
from mnemion.service.worker import Worker


class OtherModel:
    generation = Generation("second-fixture-only", 3, {"purpose": "reindex-transaction-test"})

    def __init__(self):
        self.documents = []
        self.queries = []
        self.before_return = None

    def query(self, text):
        self.queries.append(text)
        return [1.0, 0.0, 0.0]

    def document(self, text):
        self.documents.append(text)
        if self.before_return:
            self.before_return()
        return [EmbeddedChunk(0, len(text), [1.0, 0.0, 0.0])]

    def token_count(self, text):
        return len(text.split())


@pytest.fixture
def models(env):
    other = OtherModel()
    with psycopg.connect(env.admin_dsn) as conn:
        register_generation(conn, other.generation)
    registry = ModelRegistry(env.embedder, {"baseline": env.embedder, "candidate": other})
    return (
        registry,
        ReindexService(env.db, registry),
        ReindexBackfill(env.worker_db, registry),
        Worker(env.worker_db, other, default_generation=env.embedder.generation.id),
        other,
    )


def save(env, text="postgres billing memory"):
    return env.memory.save(env.owner, env.space, MemoryInput(content=text), uuid4().hex)


def start(env, service, *, profile="candidate", version=0):
    return service.start(
        env.owner,
        env.space,
        ReindexInput(profile_id=profile, expected_version=version),
        uuid4().hex,
    )


def drain(worker):
    for _ in range(100):
        if not worker.run_once():
            return
    pytest.fail("Index queue did not drain")


def finish(env, service, backfill, worker):
    while backfill.run_once(batch_size=2):
        pass
    drain(worker)
    return service.read(env.owner, env.space)


def test_background_candidate_does_not_starve_active_indexing(env, models):
    registry, service, _, _, other = models
    # Workers share the session database's queue across tenant fixtures. Finish
    # earlier tests' eligible work before measuring this explicit eight-record
    # backlog; otherwise a fair baseline turn may index another test's memory.
    drain(ModelWorker(env.worker_db, registry))
    for number in range(8):
        save(env, f"shared worker backlog {number}")
    start(env, service)
    worker = ModelWorker(env.worker_db, registry)
    for _ in range(4):
        assert worker.run_once()
    with env.db.transaction(env.owner) as conn:
        progress = {
            row["generation_id"]: row["n"]
            for row in conn.execute(
                "SELECT generation_id, count(*) AS n FROM mnemion.embeddings "
                "WHERE space_id=%s GROUP BY generation_id",
                (env.space,),
            ).fetchall()
        }
    assert 0 < progress[env.embedder.generation.id] < 8
    assert 0 < progress[other.generation.id] < 8
    drain(worker)
    assert service.read(env.owner, env.space)["candidate"]["ready_to_activate"]
    recall = RetrievalService(env.db, env.embedder, registry=registry)
    assert (
        len(
            recall.recall(
                env.owner,
                RecallInput(query="shared worker backlog", space_ids=[env.space], limit=10),
            )["hits"]
        )
        == 8
    )


def test_candidate_preserves_baseline_and_historical_revisions_then_switches(env, models):
    registry, service, backfill, worker, other = models
    first = save(env)
    env.memory.revise(
        env.owner,
        UUID(first["memory_id"]),
        RevisionInput(
            content="postgres corrected memory", expected_version=1, reason="test correction"
        ),
        uuid4().hex,
    )
    drain(env.worker)
    selected = start(env, service)
    run = UUID(selected["candidate"]["id"])
    recall = RetrievalService(env.db, env.embedder, registry=registry)
    assert (
        recall.recall(env.owner, RecallInput(query="postgres", space_ids=[env.space]))["index"][
            "generation_id"
        ]
        == env.embedder.generation.id
    )
    assert other.queries == []
    with pytest.raises(ServiceError) as caught:
        service.control(env.owner, env.space, run, "activate", selected["version"])
    assert caught.value.code == "candidate_index_incomplete"
    result = finish(env, service, backfill, worker)
    assert result["candidate"]["revisions"] == result["candidate"]["indexed_revisions"] == 2
    assert result["candidate"]["ready_to_activate"]
    preview = recall.recall(
        env.owner,
        RecallInput(
            query="postgres",
            space_ids=[env.space],
            embedding_generation=other.generation.id,
            mode="semantic",
        ),
    )
    assert len(preview["hits"]) == 1 and preview["index"]["generation_id"] == other.generation.id
    activated = service.control(env.owner, env.space, run, "activate", result["version"])
    assert (
        activated["active_generation_id"] == other.generation.id and activated["candidate"] is None
    )
    assert activated["previous_generation_id"] == env.embedder.generation.id
    assert (
        recall.recall(env.owner, RecallInput(query="postgres", space_ids=[env.space]))["index"][
            "generation_id"
        ]
        == other.generation.id
    )
    with env.db.transaction(env.owner) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.embeddings WHERE space_id=%s AND generation_id=%s",
                (env.space, env.embedder.generation.id),
            ).fetchone()["n"]
            == 2
        )
    receipt = save(env, "new after switch")
    assert receipt["generation_id"] == other.generation.id
    assert env.worker.claim() is None
    drain(worker)
    assert "new after switch" in other.documents


def test_writes_during_pause_are_queued_and_cancelled_candidates_cannot_publish(env, models):
    registry, service, backfill, worker, other = models
    save(env)
    result = start(env, service)
    run = UUID(result["candidate"]["id"])
    assert backfill.run_once()
    result = service.control(env.owner, env.space, run, "pause", result["version"])
    save(env, "written while paused")
    assert not worker.run_once() and other.documents == []
    result = service.control(env.owner, env.space, run, "resume", result["version"])
    job = worker.claim()
    assert job
    other.before_return = lambda: service.control(
        env.owner, env.space, run, "cancel", result["version"]
    )
    assert worker.process(job) is False
    with env.db.transaction(env.owner) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.embeddings WHERE space_id=%s AND generation_id=%s",
                (env.space, other.generation.id),
            ).fetchone()["n"]
            == 0
        )
        assert not conn.execute(
            "SELECT 1 FROM mnemion.jobs WHERE space_id=%s AND reindex_run_id=%s AND state IN ('pending','leased')",
            (env.space, run),
        ).fetchone()
    assert not worker.run_once()
    drain(env.worker)
    assert service.read(env.owner, env.space)["active_generation_id"] == env.embedder.generation.id


def test_backfill_and_concurrent_new_revision_queue_each_revision_once(env, models):
    registry, service, backfill, worker, other = models
    save(env)
    result = start(env, service)
    for index in range(5):
        save(env, f"new while indexing {index}")
    result = finish(env, service, backfill, worker)
    assert result["candidate"]["revisions"] == 6 and len(other.documents) == 6
    with env.db.transaction(env.owner) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.jobs WHERE space_id=%s AND reindex_run_id=%s",
                (env.space, result["candidate"]["id"]),
            ).fetchone()["n"]
            == 6
        )


def test_delete_during_candidate_inference_denies_publication_and_purges_every_generation(
    env, models
):
    registry, service, backfill, worker, other = models
    memory = save(env)
    drain(env.worker)
    start(env, service)
    backfill.run_once()
    job = worker.claim()
    other.before_return = lambda: env.memory.forget(
        env.owner, UUID(memory["memory_id"]), expected_version=1, key=uuid4().hex
    )
    assert worker.process(job) is False
    other.before_return = None
    drain(worker)
    with env.db.transaction(env.owner) as conn:
        assert not conn.execute(
            "SELECT 1 FROM mnemion.embeddings WHERE space_id=%s", (env.space,)
        ).fetchone()
    assert service.read(env.owner, env.space)["candidate"]["revisions"] == 0


def test_http_controls_validate_version_and_do_not_accept_arbitrary_endpoints(env, models):
    registry, service, backfill, worker, other = models
    with TestClient(create_app(env.db, registry=registry)) as client:
        headers = {"Authorization": "Bearer " + env.token, "Idempotency-Key": uuid4().hex}
        base = f"/v1/spaces/{env.space}/embedding"
        response = client.get(base, headers=headers)
        assert response.status_code == 200 and response.json()["version"] == 0
        payload = {"profile_id": "candidate", "expected_version": 0}
        result = client.post(base + "/reindex", headers=headers, json=payload)
        assert result.status_code == 202, result.text
        assert client.post(base + "/reindex", headers=headers, json=payload).json() == result.json()
        assert (
            client.post(
                base + "/reindex",
                headers=headers,
                json={**payload, "endpoint": "https://unapproved.example"},
            ).status_code
            == 422
        )
        candidate = result.json()["candidate"]["id"]
        assert (
            client.post(
                base + f"/reindex/{candidate}/pause", headers=headers, json={"expected_version": 0}
            ).status_code
            == 409
        )
        assert client.get(f"/v1/spaces/{uuid4()}/embedding", headers=headers).status_code in (
            403,
            404,
        )


def test_model_switch_during_query_returns_conflict_instead_of_mixed_vectors(env, models):
    registry, service, backfill, worker, other = models
    save(env)
    drain(env.worker)
    start(env, service)
    result = finish(env, service, backfill, worker)
    previous = env.embedder.query

    def switch(text):
        service.control(
            env.owner, env.space, UUID(result["candidate"]["id"]), "activate", result["version"]
        )
        return previous(text)

    env.embedder.query = switch
    with pytest.raises(ServiceError) as caught:
        RetrievalService(env.db, env.embedder, registry=registry).recall(
            env.owner, RecallInput(query="postgres", space_ids=[env.space])
        )
    assert caught.value.code == "generation_changed"


def test_cross_space_search_keeps_vector_dimensions_separate_and_labels_context_budget(env, models):
    from mnemion.service.models import ContextInput, SpaceInput

    registry, service, backfill, worker, other = models
    first = save(env)
    second_space = UUID(
        env.identities.create_space(env.owner, SpaceInput(name="Different model space"))["id"]
    )
    second = env.memory.save(
        env.owner, second_space, MemoryInput(content="postgres separate space"), uuid4().hex
    )
    drain(env.worker)
    start(env, service)
    result = finish(env, service, backfill, worker)
    service.control(
        env.owner, env.space, UUID(result["candidate"]["id"]), "activate", result["version"]
    )
    retrieval = RetrievalService(env.db, env.embedder, registry=registry)
    command = RecallInput(query="postgres", space_ids=[env.space, second_space], mode="semantic")
    result = retrieval.recall(env.owner, command)
    assert {h["memory_id"] for h in result["hits"]} == {first["memory_id"], second["memory_id"]}
    assert result["index"]["generation_id"] is None
    assert result["index"]["space_generations"] == {
        str(env.space): other.generation.id,
        str(second_space): env.embedder.generation.id,
    }
    context = retrieval.context(env.owner, ContextInput(**command.model_dump(), token_budget=512))
    assert context["token_count_unit"] == "utf8_bytes"
    assert context["token_count"] == len(context["text"].encode()) <= 512
    with pytest.raises(ServiceError) as caught:
        retrieval.recall(
            env.owner, command.model_copy(update={"embedding_generation": other.generation.id})
        )
    assert caught.value.code == "generation_changed"


def test_rollback_reuses_vectors_but_requires_new_revisions_to_be_indexed(env, models):
    registry, service, backfill, worker, other = models
    save(env)
    drain(env.worker)
    start(env, service)
    result = finish(env, service, backfill, worker)
    result = service.control(
        env.owner, env.space, UUID(result["candidate"]["id"]), "activate", result["version"]
    )
    save(env, "created after activation")
    drain(worker)
    result = start(env, service, profile="baseline", version=result["version"])
    assert result["candidate"]["indexed_revisions"] == 1 and result["candidate"]["revisions"] == 2
    result = finish(env, service, backfill, env.worker)
    assert result["candidate"]["jobs"] == [{"state": "ready", "count": 1}]
    result = service.control(
        env.owner, env.space, UUID(result["candidate"]["id"]), "activate", result["version"]
    )
    assert result["active_generation_id"] == env.embedder.generation.id


def test_writers_can_dual_queue_but_cannot_change_models_or_preview_candidates(env, models):
    from mnemion.service.models import GrantInput, KeyInput, PrincipalInput

    registry, service, backfill, worker, other = models
    person = env.identities.create_principal(env.owner, PrincipalInput(name="Contributor"))
    key = env.identities.create_key(env.owner, UUID(person["id"]), KeyInput(name="Writer key"))
    writer = env.db.authenticate(key["api_key"])
    env.identities.grant(env.owner, env.space, writer.principal_id, GrantInput(role="contributor"))
    started = start(env, service)
    with pytest.raises(ServiceError) as caught:
        service.control(
            writer, env.space, UUID(started["candidate"]["id"]), "cancel", started["version"]
        )
    assert caught.value.status == 403
    result = env.memory.save(
        writer, env.space, MemoryInput(content="writer can contribute during reindex"), uuid4().hex
    )
    assert result["generation_id"] == env.embedder.generation.id
    with pytest.raises(ServiceError) as caught:
        RetrievalService(env.db, env.embedder, registry=registry).recall(
            writer,
            RecallInput(
                query="memory", space_ids=[env.space], embedding_generation=other.generation.id
            ),
        )
    assert caught.value.status == 403 and other.queries == []
    with env.db.transaction(writer) as conn:
        assert not conn.execute(
            "UPDATE mnemion.space_embedding_settings SET version=version+1 WHERE space_id=%s RETURNING version",
            (env.space,),
        ).fetchone()
    result = finish(env, service, backfill, worker)
    assert result["candidate"]["ready_to_activate"]
    service.control(
        env.owner, env.space, UUID(result["candidate"]["id"]), "cancel", result["version"]
    )
    drain(env.worker)


def test_cloud_profile_requires_explicit_space_approval_before_any_request(env, tmp_path):
    import httpx
    import json
    from mnemion.service.http_embeddings import HttpEmbedder
    from mnemion.service.model_config import RemoteEmbeddingProfile

    calls = []
    profile = RemoteEmbeddingProfile(
        id="cloud-fixture",
        label="Cloud protocol fixture",
        protocol="openai",
        endpoint="https://approved-provider.example/v1/embeddings",
        model="fixture-remote",
        revision="1",
        dimensions=2,
    )

    def endpoint(request):
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(
            200,
            json={
                "model": "fixture-remote",
                "data": [{"index": i, "embedding": [1, 0]} for i, _ in enumerate(body["input"])],
            },
        )

    remote = HttpEmbedder(profile, tmp_path, transport=httpx.MockTransport(endpoint))
    registry = ModelRegistry(env.embedder, {"baseline": env.embedder, profile.id: remote})
    with psycopg.connect(env.admin_dsn) as conn:
        register_generation(conn, profile.generation)
    service = ReindexService(env.db, registry)
    command = ReindexInput(profile_id=profile.id, expected_version=0)
    save(env, "synthetic authorized cloud test memory")
    with pytest.raises(ServiceError) as caught:
        service.start(env.owner, env.space, command, uuid4().hex)
    assert caught.value.code == "embedding_egress_approval_required"
    assert calls == [] and service.read(env.owner, env.space)["candidate"] is None
    service.start(
        env.owner,
        env.space,
        command.model_copy(update={"approve_network_egress": True}),
        uuid4().hex,
    )
    worker = Worker(env.worker_db, remote, default_generation=env.embedder.generation.id)
    result = finish(env, service, ReindexBackfill(env.worker_db, registry), worker)
    assert calls[0]["input"] == ["synthetic authorized cloud test memory"]
    assert result["candidate"]["ready_to_activate"]
    service.control(
        env.owner, env.space, UUID(result["candidate"]["id"]), "cancel", result["version"]
    )
    registry.close()
    drain(env.worker)


def test_evaluations_freeze_and_compare_candidate_generations(env, models):
    from mnemion.service.evaluation_models import DatasetInput, EvaluationInput
    from mnemion.service.evaluation_runner import EvaluationRunner
    from mnemion.service.evaluations import EvaluationService

    registry, service, backfill, worker, other = models
    memory = save(env)
    drain(env.worker)
    start(env, service)
    result = finish(env, service, backfill, worker)
    evaluations = EvaluationService(env.db, env.embedder, registry=registry)
    dataset = evaluations.create_dataset(
        env.owner,
        env.space,
        DatasetInput.model_validate(
            {
                "name": "Model change test",
                "cases": [
                    {
                        "id": "query_1",
                        "query": "postgres",
                        "references": [{"memory_id": memory["memory_id"]}],
                    }
                ],
            }
        ),
    )
    command = EvaluationInput(
        dataset_id=UUID(dataset["id"]),
        embedding_generation=other.generation.id,
        modes=["semantic"],
        context=True,
        cutoffs=[1],
    )
    run = evaluations.create_run(env.owner, env.space, command, uuid4().hex)
    assert run["generation_id"] == other.generation.id
    runner = EvaluationRunner(env.db, RetrievalService(env.db, env.embedder, registry=registry))
    for _ in range(5):
        if not runner.run_once():
            break
    assert evaluations.run(env.owner, env.space, UUID(run["id"]))["state"] == "completed"
    assert other.queries
    queued = evaluations.create_run(env.owner, env.space, command, uuid4().hex)
    service.control(
        env.owner, env.space, UUID(result["candidate"]["id"]), "cancel", result["version"]
    )
    previous_calls = len(other.queries)
    assert runner.run_once()
    failed = evaluations.run(env.owner, env.space, UUID(queued["id"]))
    assert failed["state"] == "failed" and failed["error_code"] == "generation_changed"
    assert len(other.queries) == previous_calls
