"""Index observations use real permission checks and current PostgreSQL state."""

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import psycopg
import pytest

from mnemion.connectors.conversation_inbox import InboxError, open_inbox
from mnemion.service.api import create_app
from mnemion.service.admin import register_generation
from mnemion.service.capture_models import CaptureIndexPage
from mnemion.service.embeddings import Generation
from mnemion.service.errors import ServiceError
from mnemion.service.models import RevisionInput
from service_tests.test_capture_coverage import selected as selected
from service_tests.test_capture_custody import (
    custody as custody,
    page,
    selected as source_items,
    changed_revision,
)
from service_tests.test_live_conversations import conversation_source as conversation_source
from service_tests.test_reindex import postgres as postgres


def accepted(custody, conversation_source, *, two=False):
    service, source, grant, _, _ = custody
    _, _, operator, _, _, config = conversation_source
    scope, items = source_items(config)
    command = page(source, scope, items[0], *([changed_revision(items[0])] if two else []))
    receipt = service.page(operator, grant, command)
    return service, operator, grant, receipt


def test_index_observation_changes_after_real_worker_commit(env, custody, conversation_source):
    service, operator, grant, _ = accepted(custody, conversation_source)
    before = CaptureIndexPage.model_validate(service.index_progress(operator, grant))
    assert before.counts.events == before.counts.lexical_indexed == before.counts.waiting == 1
    assert before.counts.vector_indexed == 0
    assert env.worker.run_once()
    after = CaptureIndexPage.model_validate(service.index_progress(operator, grant))
    assert after.generation_id == env.embedder.generation.id
    assert after.counts.lexical_indexed == after.counts.vector_indexed == 1
    assert after.counts.waiting == 0
    assert after.next_cursor is None


def test_index_pages_enforce_active_device_authority_and_bounded_pagination(
    env, custody, conversation_source
):
    service, operator, grant, receipt = accepted(custody, conversation_source, two=True)
    first = service.index_progress(operator, grant, limit=1)
    second = service.index_progress(operator, grant, after=first["next_cursor"], limit=1)
    assert first["counts"]["events"] == second["counts"]["events"] == 1
    assert first["next_cursor"] == min(item["event_id"] for item in receipt["items"])
    assert second["next_cursor"] is None
    _, _, _, _, secret, _ = conversation_source
    with TestClient(create_app(env.db, env.embedder)) as client:
        path = f"/v1/capture-grants/{grant}/index-progress"
        headers = {"Authorization": "Bearer " + secret}
        response = client.get(path, headers=headers, params={"limit": 1})
        assert response.status_code == 200
        assert CaptureIndexPage.model_validate(response.json()).counts.events == 1
        assert client.get(path, headers=headers, params={"limit": 1001}).status_code == 422
        assert (
            client.get(path, headers=headers, params={"after": "not-a-cursor"}).status_code == 422
        )
        assert (
            client.get(path.replace(str(grant), str(uuid4())), headers=headers).status_code == 404
        )
        assert client.get(path, headers={"Authorization": "Bearer " + env.token}).status_code == 403
        service.status(env.owner, grant, revoke=True)
        assert client.get(path, headers=headers).status_code == 403


def test_index_observations_use_current_revision_and_active_generation(
    env, custody, conversation_source
):
    service, operator, grant, receipt = accepted(custody, conversation_source)
    memory = UUID(receipt["items"][0]["memory_id"])
    assert env.worker.run_once()
    assert service.index_progress(operator, grant)["counts"]["vector_indexed"] == 1
    env.memory.revise(
        conversation_source[3],
        memory,
        RevisionInput(
            content="A revised memory needs its own vector",
            expected_version=1,
            reason="Verify revision-specific indexing",
        ),
        key="index-revision",
    )
    assert service.index_progress(operator, grant)["counts"]["waiting"] == 1
    assert env.worker.run_once()
    assert service.index_progress(operator, grant)["counts"]["vector_indexed"] == 1
    generation = Generation("fixture-new-index", 3, {})
    with psycopg.connect(env.admin_dsn) as conn:
        register_generation(conn, generation)
        conn.execute(
            "INSERT INTO mnemion.space_embedding_settings(tenant_id,space_id,active_generation_id,inference_paused) "
            "VALUES(%s,%s,%s,true)",
            (env.owner.tenant_id, UUID(custody[3]["space_id"]), generation.id),
        )
    after = service.index_progress(operator, grant)
    assert after["generation_id"] == generation.id and after["inference_paused"]
    assert after["counts"]["vector_indexed"] == 0 and after["counts"]["waiting"] == 1


def test_index_observation_yields_to_source_changes_and_recovers(env, custody, conversation_source):
    service, operator, grant, _ = accepted(custody, conversation_source)
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"capture:{custody[1]}",)
        )
        with pytest.raises(ServiceError) as failure:
            service.index_progress(operator, grant)
        assert failure.value.status == 503 and failure.value.code == "capture_index_busy"
    assert service.index_progress(operator, grant)["counts"]["events"] == 1


def test_failed_withheld_and_forgotten_are_not_reported_as_vector_ready(
    env, custody, conversation_source
):
    service, operator, grant, receipt = accepted(custody, conversation_source)
    memory = UUID(receipt["items"][0]["memory_id"])
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            "UPDATE mnemion.jobs SET state='failed' WHERE operation_id=%s",
            (UUID(receipt["items"][0]["operation_id"]),),
        )
    failed = service.index_progress(operator, grant)["counts"]
    assert failed["failed"] == failed["lexical_indexed"] == 1
    assert failed["waiting"] == failed["vector_indexed"] == 0
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            "UPDATE mnemion.memories SET review_state='quarantined' WHERE id=%s", (memory,)
        )
    withheld = service.index_progress(operator, grant)["counts"]
    assert withheld["withheld"] == 1 and withheld["lexical_indexed"] == 0
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute("UPDATE mnemion.memories SET review_state='ordinary' WHERE id=%s", (memory,))
    reader = conversation_source[3]
    env.memory.forget(reader, memory, expected_version=1, key="index-observation-forgetting")
    forgotten = service.index_progress(operator, grant)["counts"]
    assert forgotten["forgotten"] == 1 and forgotten["lexical_indexed"] == 0


def observed_page(binding, *, after=None, next_cursor=None, generation="model-one", events=1):
    return {
        "source_id": binding["source_id"],
        "grant_id": binding["grant_id"],
        "generation_id": generation,
        "inference_paused": False,
        "observed_at": "2026-10-21T02:00:00+00:00",
        "after": after,
        "next_cursor": next_cursor,
        "counts": {
            "events": events,
            "lexical_indexed": events,
            "vector_indexed": 0,
            "waiting": events,
            "failed": 0,
            "withheld": 0,
            "forgotten": 0,
            "unknown": 0,
        },
    }


def test_index_sweep_survives_restart_and_never_mixes_generations(selected):
    _, settings = selected
    binding = settings[1]
    with open_inbox(*settings, create=True) as inbox:
        assert not inbox.observations.indexed(
            observed_page(binding, next_cursor="1" * 64, events=1000)
        )
        assert inbox.status()["coverage"]["index"]["completed"] is None
    with open_inbox(*settings) as inbox:
        assert inbox.observations.index_cursor() == "1" * 64
        with pytest.raises(InboxError, match="capture_checkpoint_invalid"):
            inbox.observations.indexed(observed_page(binding))
        assert not inbox.observations.indexed(
            observed_page(binding, after="1" * 64, generation="model-two")
        )
        assert inbox.observations.index_cursor() is None
        assert inbox.observations.indexed(observed_page(binding, generation="model-two", events=2))
        complete = inbox.status()["coverage"]["index"]["completed"]
        assert complete["counts"]["events"] == 2 and complete["generation_id"] == "model-two"
        assert not inbox.observations.indexed(
            observed_page(binding, generation="model-two", next_cursor="2" * 64)
        )
        inbox.observations.index_unavailable()
        result = inbox.status()["coverage"]["index"]
        assert result["status"] == "unavailable" and result["completed"] == complete
        assert result["active"]["counts"]["events"] == 1
        wrong = observed_page(binding, after="2" * 64)
        wrong["source_id"] = str(uuid4())
        with pytest.raises(InboxError, match="capture_binding_mismatch"):
            inbox.observations.indexed(wrong)
        assert inbox.status()["coverage"]["index"] == result
