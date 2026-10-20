"""Real leased dispatch under a source backlog; no timing/load simulation."""

from uuid import UUID, uuid4

import psycopg
import pytest

from mnemion.service.admin import bootstrap_tenant
from mnemion.service.errors import ServiceError
from mnemion.service.models import MemoryInput, SpaceInput
from mnemion.service.worker import Worker
from service_tests.test_reindex import postgres as postgres


def seed(env, *, owner=None, space=None, count=1):
    return [
        env.memory.save(
            owner or env.owner,
            space or env.space,
            MemoryInput(content=f"Disposable queue evidence {index}."),
            uuid4().hex,
        )
        for index in range(count)
    ]


def other_tenant(env):
    setup = bootstrap_tenant(
        env.admin_dsn,
        tenant_name="Another independent organization",
        administrator_name="Independent owner",
        generation=env.embedder.generation,
    )
    return env.db.authenticate(setup["api_key"]), UUID(setup["space_id"])


def test_a_large_old_source_queue_yields_to_another_space_and_survives_worker_restart(env):
    backlog = seed(env, count=16)
    space = UUID(env.identities.create_space(env.owner, SpaceInput(name="Interactive team"))["id"])
    urgent = seed(env, space=space, count=2)
    first = env.worker.claim()
    assert first["operation_id"] == UUID(backlog[0]["operation_id"])
    assert env.worker.process(first)

    restarted = Worker(env.worker_db, env.embedder)
    second = restarted.claim()
    assert second["operation_id"] == UUID(urgent[0]["operation_id"])
    assert restarted.process(second)
    third = restarted.claim()
    assert third["operation_id"] == UUID(backlog[1]["operation_id"])
    assert restarted.process(third)
    fourth = restarted.claim()
    assert fourth["operation_id"] == UUID(urgent[1]["operation_id"])
    assert restarted.process(fourth)
    assert env.memory.operation(env.owner, UUID(urgent[1]["operation_id"]))["state"] == "ready"


def test_an_organization_with_many_spaces_cannot_take_every_tenant_turn(env):
    first_memory = seed(env, count=5)[0]
    other, first_space = other_tenant(env)
    other_spaces = [first_space] + [
        UUID(env.identities.create_space(other, SpaceInput(name=f"Other source {i}"))["id"])
        for i in range(4)
    ]
    for space in other_spaces:
        seed(env, owner=other, space=space, count=3)
    observed = []
    for _ in range(6):
        job = env.worker.claim()
        observed.append(job["tenant_id"])
        assert env.worker.process(job)
    assert observed == [env.owner.tenant_id, other.tenant_id] * 3
    with pytest.raises(ServiceError):
        env.memory.fetch(other, UUID(first_memory["memory_id"]))


def test_purge_overtakes_older_embeddings_even_without_an_available_model(env):
    seed(env, count=16)
    disposable = seed(env)[0]
    deleted = env.memory.forget(
        env.owner, UUID(disposable["memory_id"]), expected_version=1, key=uuid4().hex
    )
    with env.worker_db.pool.connection() as conn:
        purge = conn.execute("SELECT * FROM mnemion.claim_job(%s,120,NULL)", (uuid4(),)).fetchone()
    assert purge["kind"] == "purge"
    assert purge["operation_id"] == UUID(deleted["operation_id"])
    assert env.worker.process(purge)
    assert env.memory.operation(env.owner, UUID(deleted["operation_id"]))["state"] == "ready"
    assert env.worker.claim()["kind"] == "embed"


def test_dispatch_skips_another_workers_locked_tenant_and_never_duplicates_a_lease(env):
    seed(env, count=3)
    other, space = other_tenant(env)
    seed(env, owner=other, space=space, count=3)
    query = "SELECT * FROM mnemion.claim_job(%s,120,%s)"
    with env.worker_db.pool.connection() as first, env.worker_db.pool.connection() as second:
        one = first.execute(query, (uuid4(), env.embedder.generation.id)).fetchone()
        # The first transaction deliberately retains its dispatch locks.
        second.execute("SET LOCAL statement_timeout='2s'")
        two = second.execute(query, (uuid4(), env.embedder.generation.id)).fetchone()
        assert one["id"] != two["id"] and one["lease_id"] != two["lease_id"]
        assert {one["tenant_id"], two["tenant_id"]} == {env.owner.tenant_id, other.tenant_id}


def test_unavailable_generation_does_not_advance_turns_and_app_role_cannot_claim(env):
    seed(env)
    with env.worker_db.pool.connection() as conn:
        assert (
            conn.execute(
                "SELECT * FROM mnemion.claim_job(%s,120,%s)", (uuid4(), "unconfigured")
            ).fetchone()
            is None
        )
    with env.db.transaction(env.owner) as conn:
        row = conn.execute(
            "SELECT last_index_claim FROM mnemion.spaces WHERE id=%s", (env.space,)
        ).fetchone()
        assert row["last_index_claim"] is None
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with env.db.transaction(env.owner) as conn:
            conn.execute(
                "SELECT * FROM mnemion.claim_job(%s,120,%s)",
                (uuid4(), env.embedder.generation.id),
            )
