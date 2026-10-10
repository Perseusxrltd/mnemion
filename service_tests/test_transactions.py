from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import psycopg
import pytest

from mnemion.service.admin import bootstrap_tenant
from mnemion.service.db import Database
from mnemion.service.errors import ServiceError
from mnemion.service.models import (
    GrantInput,
    KeyInput,
    MemoryInput,
    PrincipalInput,
    RevisionInput,
    ReviewInput,
)


def app_identity(env, role="contributor"):
    principal = env.identities.create_principal(env.owner, PrincipalInput(name="Billing app"))
    key = env.identities.create_key(env.owner, UUID(principal["id"]), KeyInput(name="Test client"))
    env.identities.grant(env.owner, env.space, UUID(principal["id"]), GrantInput(role=role))
    return env.db.authenticate(key["api_key"]), key


def test_save_is_atomic_idempotent_and_immediately_lexical(env):
    command = MemoryInput(content="Billing stores its ledger in PostgreSQL.", subject="Billing")
    first = env.memory.save(env.owner, env.space, command, "one")
    assert first == env.memory.save(env.owner, env.space, command, "one")
    assert first["state"] == "accepted" and first["lexical_ready"]
    with env.db.transaction(env.owner) as conn:
        assert conn.execute("SELECT count(*) AS n FROM mnemion.memories").fetchone()["n"] == 1
        assert conn.execute("SELECT count(*) AS n FROM mnemion.jobs").fetchone()["n"] == 1
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.memory_revisions WHERE search_text @@ plainto_tsquery('simple','PostgreSQL')"
            ).fetchone()["n"]
            == 1
        )
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.audit_events WHERE action='memory.created'"
            ).fetchone()["n"]
            == 1
        )
    with pytest.raises(ServiceError, match="different request") as error:
        env.memory.save(env.owner, env.space, MemoryInput(content="Different"), "one")
    assert error.value.status == 409
    record = env.memory.fetch(env.owner, UUID(first["memory_id"]))
    assert record["evidence"]["excerpt"] == command.content


def test_failed_canonical_transaction_has_no_partial_memory(env, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("injected before job creation")

    monkeypatch.setattr(env.memory, "_operation", fail)
    with pytest.raises(RuntimeError):
        env.memory.save(env.owner, env.space, MemoryInput(content="Must roll back"), "atomic")
    with env.db.transaction(env.owner) as conn:
        for table in (
            "memories",
            "memory_revisions",
            "sources",
            "source_revisions",
            "idempotency_keys",
        ):
            assert conn.execute(f"SELECT count(*) AS n FROM mnemion.{table}").fetchone()["n"] == 0


def test_concurrent_idempotency_and_revision_conflicts(env):
    command = MemoryInput(content="One durable result")
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(
            pool.map(
                lambda _: env.memory.save(env.owner, env.space, command, "concurrent"), range(4)
            )
        )
    assert all(r == receipts[0] for r in receipts)
    memory = UUID(receipts[0]["memory_id"])

    def revise(index):
        try:
            return env.memory.revise(
                env.owner,
                memory,
                RevisionInput(
                    content=f"Changed {index}", expected_version=1, reason="Concurrent edit"
                ),
                f"revision-{index}",
            )
        except ServiceError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(revise, range(2)))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert "version_conflict" in results
    history = env.memory.history(env.owner, memory)
    assert [r["revision_version"] for r in history] == [2, 1]
    assert history[-1]["content"] == command.content


def test_roles_revocation_and_connection_pool_scope(env):
    writer, key = app_identity(env)
    first = env.memory.save(
        writer, env.space, MemoryInput(content="An app wrote this", subject="Someone else"), "app"
    )
    memory = UUID(first["memory_id"])
    assert env.memory.fetch(env.owner, memory)["created_by"] == str(writer.principal_id)
    other = bootstrap_tenant(
        env.admin_dsn,
        tenant_name="Other team",
        administrator_name="Other owner",
        generation=env.embedder.generation,
    )
    outsider = env.db.authenticate(other["api_key"])
    with env.db.transaction(outsider) as conn:
        assert conn.execute("SELECT count(*) AS n FROM mnemion.memories").fetchone()["n"] == 0
    with pytest.raises(ServiceError) as error:
        env.memory.fetch(outsider, memory)
    assert error.value.status == 404
    with pytest.raises(ServiceError):
        env.memory.save(outsider, env.space, MemoryInput(content="Unauthorized"), "bad")
    with env.db.pool.connection() as conn:
        assert conn.execute("SELECT mnemion.tenant() AS tenant").fetchone()["tenant"] is None
        assert conn.execute("SELECT count(*) AS n FROM mnemion.memories").fetchone()["n"] == 0
    with pytest.raises(ServiceError) as error:
        env.memory.review(
            writer,
            memory,
            ReviewInput(expected_version=1, state="quarantined", reason="Not a reviewer"),
        )
    assert error.value.status == 403
    env.identities.revoke_grant(env.owner, env.space, writer.principal_id)
    with pytest.raises(ServiceError):
        env.memory.fetch(writer, memory)
    env.identities.revoke_key(env.owner, UUID(key["id"]))
    with pytest.raises(ServiceError) as error:
        env.identities.me(writer)
    assert error.value.status == 401
    assert "api_key" not in str(env.identities.keys(env.owner))
    assert "token_hash" not in str(env.identities.keys(env.owner))


def test_readers_cannot_write_and_verified_content_needs_reviewer(env):
    reader, _ = app_identity(env, "reader")
    with pytest.raises(ServiceError) as error:
        env.memory.save(reader, env.space, MemoryInput(content="Reader write"), "reader")
    assert error.value.status == 403
    with env.db.transaction(reader) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO mnemion.memories(tenant_id, space_id, id, created_by) VALUES (%s,%s,%s,%s)",
                (reader.tenant_id, env.space, uuid4(), reader.principal_id),
            )
    writer, _ = app_identity(env, "contributor")
    approved = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="Approved decision", claim_status="verified"),
        "approved",
    )
    with pytest.raises(ServiceError) as error:
        env.memory.revise(
            writer,
            UUID(approved["memory_id"]),
            RevisionInput(content="Silently change approval", expected_version=1, reason="Test"),
            "override",
        )
    assert error.value.status == 403


def test_worker_indexing_quarantine_and_physical_deletion(env):
    receipt = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="Postgres billing", subject="Sensitive name"),
        "life",
    )
    memory = UUID(receipt["memory_id"])
    record = env.memory.fetch(env.owner, memory)
    operation = UUID(receipt["operation_id"])
    job = env.worker.claim()
    # Other tests leave independent tenants' durable jobs. Process until ours.
    while job and job["operation_id"] != operation:
        env.worker.process(job)
        job = env.worker.claim()
    assert job and env.worker.process(job)
    assert env.memory.operation(env.owner, operation)["state"] == "ready"
    with env.db.transaction(env.owner) as conn:
        assert conn.execute("SELECT count(*) AS n FROM mnemion.embeddings").fetchone()["n"] == 1
    env.memory.review(
        env.owner,
        memory,
        ReviewInput(expected_version=1, state="quarantined", reason="Check source"),
    )
    with pytest.raises(ServiceError):
        env.memory.fetch(env.owner, memory)
    with pytest.raises(ServiceError):
        env.memory.source(env.owner, UUID(record["evidence"]["source_revision_id"]))
    assert env.memory.fetch(env.owner, memory, review=True)["content"] == "Postgres billing"
    deleted = env.memory.forget(env.owner, memory, expected_version=2, key="delete")
    with pytest.raises(ServiceError):
        env.memory.fetch(env.owner, memory, review=True)
    while env.worker.run_once():
        pass
    assert env.memory.operation(env.owner, UUID(deleted["operation_id"]))["state"] == "ready"
    with env.db.transaction(env.owner) as conn:
        for table in ("source_revisions", "memory_revisions", "embeddings"):
            assert conn.execute(f"SELECT count(*) AS n FROM mnemion.{table}").fetchone()["n"] == 0
        assert (
            conn.execute("SELECT subject FROM mnemion.memories WHERE id=%s", (memory,)).fetchone()[
                "subject"
            ]
            is None
        )
        assert (
            conn.execute(
                "SELECT purged_at FROM mnemion.deletion_receipts WHERE memory_id=%s", (memory,)
            ).fetchone()["purged_at"]
            is not None
        )


def test_owner_database_credentials_are_rejected(postgres):
    with pytest.raises(RuntimeError, match="must not own"):
        Database(postgres[0]).open()
