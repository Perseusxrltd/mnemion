"""Diagnostics preserve scope, bounded collection and honest measurements."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from mnemion.service.api import create_app
from mnemion.service.insights import Insights, InsightsService
from mnemion.service.models import (
    GrantInput,
    KeyInput,
    MemoryInput,
    PrincipalInput,
    ReviewInput,
    SpaceInput,
)
from mnemion.service.telemetry import Telemetry, percentile_bound
from mnemion.service.worker import Worker


def test_numeric_telemetry_aggregation_and_histogram_bounds(env):
    telemetry = Telemetry(env.db)
    for duration in (1, 10, 100, 500, 2000):
        telemetry.record(
            env.owner,
            env.space,
            stage="recall",
            mode="semantic",
            duration_ms=duration,
            input_bytes=12,
            records=2,
            generation=env.embedder.generation.id,
        )
    telemetry.record(
        env.owner,
        env.space,
        stage="recall",
        mode="semantic",
        origin="evaluation",
        duration_ms=30,
        failed=True,
        generation=env.embedder.generation.id,
    )
    telemetry.flush()
    report = InsightsService(env.db, env.embedder).read(env.owner, env.space, origin="interactive")
    Insights.model_validate(report)
    group = report["metrics"]["groups"][0]
    assert group["calls"] == 5 and group["input_bytes"] == 60 and group["records"] == 10
    assert group["mean_ms"] == 522.2 and group["p50_upper_ms"] == 100
    assert group["p95_upper_ms"] == 2500 and group["max_ms"] == 2000
    assert sum(group["latency_histogram"]) == 5
    assert report["metrics"]["recorded_calls"] == 5
    assert telemetry.snapshot()["persisted_samples"] == 6
    assert percentile_bound([0] * 18, 0.95) is None
    assert percentile_bound([0] * 17 + [1], 0.95) is None  # Unbounded final bin, not 300s.
    with pytest.raises(ValueError):
        telemetry.record(
            env.owner,
            env.space,
            stage="recall",
            duration_ms=1,
            private_query="must never become a label",
        )


def test_overflow_and_revoked_buffered_identity_drop_only_diagnostics(env):
    telemetry = Telemetry(env.db, max_series=1)
    telemetry.record(env.owner, env.space, stage="recall", duration_ms=1)
    telemetry.record(env.owner, env.space, stage="context", duration_ms=2)
    assert telemetry.snapshot()["dropped_samples"] == 1
    assert telemetry.snapshot()["buffered_series"] == 1
    key = env.identities.create_key(env.owner, env.owner.principal_id, KeyInput(name="temporary"))
    caller = env.db.authenticate(key["api_key"])
    telemetry.flush()
    telemetry.record(caller, env.space, stage="recall", duration_ms=1)
    env.identities.revoke_key(env.owner, caller.key_id)
    telemetry.flush()
    assert telemetry.snapshot()["dropped_samples"] == 2
    report = InsightsService(env.db, env.embedder).read(env.owner, env.space)
    assert report["metrics"]["recorded_calls"] == 1
    assert (
        env.memory.save(
            env.owner,
            env.space,
            MemoryInput(content="Durable after diagnostics overflow"),
            "overflow",
        )["state"]
        == "accepted"
    )


def test_memory_health_and_worker_metrics_use_current_evidence(env):
    text = "PostgreSQL stores the shared memories."
    for index in range(2):
        env.memory.save(env.owner, env.space, MemoryInput(content=text), f"same-{index}")
    quarantined = env.memory.save(
        env.owner, env.space, MemoryInput(content="Review this claim"), "review"
    )
    env.memory.review(
        env.owner,
        UUID(quarantined["memory_id"]),
        ReviewInput(expected_version=1, state="quarantined", reason="Pending human review"),
    )
    env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="Expired", valid_to=datetime.now(timezone.utc) - timedelta(days=1)),
        "expired",
    )
    service = InsightsService(env.db, env.embedder, cache_seconds=0)
    first = service.read(env.owner, env.space)
    assert first["memory"]["active"] == 4 and first["memory"]["eligible"] == 2
    assert first["memory"]["quarantined"] == 1 and first["memory"]["expired"] == 1
    assert first["memory"]["duplicate_copies"] == 1 and first["memory"]["indexed"] == 0
    telemetry = Telemetry(env.worker_db)
    worker = Worker(env.worker_db, env.embedder, telemetry=telemetry)
    while worker.run_once():
        pass
    telemetry.flush()
    report = service.read(env.owner, env.space)
    Insights.model_validate(report)
    assert report["memory"]["indexed"] == 2
    assert report["generations"][0]["chunks"] == 4
    assert report["metrics"]["groups"][0]["records"] == 4
    assert report["queue_latency"]["completed_operations"] == 4
    assert (
        sum(point["count"] for point in report["changes"] if point["action"] == "memory.created")
        == 4
    )


def test_metrics_and_cached_snapshots_require_current_reviewer_access(env):
    env.memory.save(env.owner, env.space, MemoryInput(content="Private queued evidence"), "queued")
    identities = {}
    for role in ("reader", "reviewer", "unscoped-admin"):
        p = env.identities.create_principal(
            env.owner, PrincipalInput(name=role, administrator=role == "unscoped-admin")
        )
        key = env.identities.create_key(env.owner, UUID(p["id"]), KeyInput(name=role))
        caller = env.db.authenticate(key["api_key"])
        if role != "unscoped-admin":
            env.identities.grant(env.owner, env.space, caller.principal_id, GrantInput(role=role))
        identities[role] = caller, key["api_key"]
    telemetry = Telemetry(env.db)
    telemetry.record(identities["reader"][0], env.space, stage="recall", duration_ms=50)
    telemetry.record(env.owner, None, stage="context", duration_ms=50)
    telemetry.flush()
    with TestClient(create_app(env.db, env.embedder)) as client:
        for role, status in (("reader", 403), ("reviewer", 200), ("unscoped-admin", 404)):
            caller, key = identities[role]
            response = client.get(
                f"/v1/spaces/{env.space}/insights", headers={"Authorization": "Bearer " + key}
            )
            assert response.status_code == status, response.text
            if status == 200:
                assert response.json()["metrics"]["recorded_calls"] == 1
                assert response.json()["queue_work"][0]["count"] == 1
            with env.db.transaction(caller) as conn:
                rows = conn.execute("SELECT space_id FROM mnemion.metric_buckets").fetchall()
                assert len(rows) == (0 if role == "reader" else 1)
                if role == "unscoped-admin":
                    assert rows[0]["space_id"] is None
        caller, key = identities["reviewer"]
        env.identities.revoke_grant(env.owner, env.space, caller.principal_id)
        assert (
            client.get(
                f"/v1/spaces/{env.space}/insights", headers={"Authorization": "Bearer " + key}
            ).status_code
            == 404
        )
        assert (
            client.get(
                "/v1/insights/runtime", headers={"Authorization": "Bearer " + key}
            ).status_code
            == 403
        )
        response = client.get(
            "/v1/insights/runtime", headers={"Authorization": "Bearer " + env.token}
        )
        assert response.status_code == 200, response.text
        assert response.json()["resources"]["rss_bytes"] > 0
        cache = response.json()["model_cache"]
        assert cache["scope"] == "this_process" and cache["idle_seconds"] == 300
        assert cache["idle_cleanup_enabled"] and cache["idle_cleanup_running"]
        assert cache["loaded_local_models"] == 0
        assert cache["idle_model_evictions"] == 0 and cache["cleanup_failures"] == 0
        assert (
            client.get(
                f"/v1/spaces/{uuid4()}/insights", headers={"Authorization": "Bearer " + env.token}
            ).status_code
            == 404
        )


def test_queue_work_distinguishes_backoff_leases_cleanup_and_space_boundaries(env):
    text = "évidence " * 1500
    large = env.memory.save(env.owner, env.space, MemoryInput(content=text), "large")
    delayed = env.memory.save(env.owner, env.space, MemoryInput(content="Delayed"), "delayed")
    retired = env.memory.save(env.owner, env.space, MemoryInput(content="Withdrawn"), "retired")
    env.memory.forget(
        env.owner, UUID(retired["memory_id"]), expected_version=1, key="withdraw-retired"
    )
    elsewhere = env.identities.create_space(env.owner, SpaceInput(name="Different space"))
    env.memory.save(
        env.owner, UUID(elsewhere["id"]), MemoryInput(content="Other space " * 5000), "elsewhere"
    )
    with psycopg.connect(env.admin_dsn) as connection:
        connection.execute(
            """UPDATE mnemion.jobs SET available_at=now()+interval '1 hour',attempts=2,
                created_at=now()-interval '45 minutes' WHERE operation_id=%s""",
            (UUID(delayed["operation_id"]),),
        )
    service = InsightsService(env.db, env.embedder, cache_seconds=0)
    report = service.read(env.owner, env.space)
    Insights.model_validate(report)
    work = {(row["kind"], row["state"]): row for row in report["queue_work"]}
    assert set(work) == {("embed", "pending"), ("purge", "pending")}
    index, purge = work["embed", "pending"], work["purge", "pending"]
    assert (index["count"], index["due"], index["retried"]) == (2, 1, 1)
    assert index["input_bytes"] == len(text.encode()) + len(b"Delayed")
    assert index["largest_input_bytes"] == len(text.encode())
    assert index["oldest_age_seconds"] >= 45 * 60
    assert (purge["count"], purge["due"], purge["input_bytes"]) == (1, 1, 0)
    assert purge["largest_input_bytes"] == 0
    assert any(row["state"] == "cancelled" for row in report["queue"])
    with psycopg.connect(env.admin_dsn) as connection:
        connection.execute(
            """UPDATE mnemion.jobs SET state='leased',lease_id=%s,
                lease_until=now()+interval '1 hour' WHERE operation_id=%s""",
            (uuid4(), UUID(large["operation_id"])),
        )
    leased = next(
        row for row in service.read(env.owner, env.space)["queue_work"] if row["state"] == "leased"
    )
    assert leased["count"] == 1 and leased["due"] == 0
    with psycopg.connect(env.admin_dsn) as connection:
        connection.execute(
            "UPDATE mnemion.jobs SET lease_until=now()-interval '1 second' WHERE operation_id=%s",
            (UUID(large["operation_id"]),),
        )
    expired = next(
        row for row in service.read(env.owner, env.space)["queue_work"] if row["state"] == "leased"
    )
    assert expired["due"] == 1
    with psycopg.connect(env.admin_dsn) as connection:
        connection.execute(
            "UPDATE mnemion.jobs SET state='failed' WHERE operation_id=%s",
            (UUID(large["operation_id"]),),
        )
    failed = next(
        row for row in service.read(env.owner, env.space)["queue_work"] if row["state"] == "failed"
    )
    assert failed["due"] == 0 and failed["input_bytes"] == len(text.encode())


def test_telemetry_expiry_never_deletes_current_samples_or_memories(env):
    telemetry = Telemetry(env.db)
    telemetry.record(env.owner, env.space, stage="recall", duration_ms=1)
    telemetry.flush()
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            "UPDATE mnemion.metric_buckets SET bucket=now()-interval '32 days' WHERE tenant_id=%s",
            (env.owner.tenant_id,),
        )
    env.memory.save(env.owner, env.space, MemoryInput(content="Retained evidence"), "kept")
    telemetry.record(env.owner, env.space, stage="recall", duration_ms=3)
    telemetry.flush()
    report = InsightsService(env.db, env.embedder).read(env.owner, env.space)
    assert report["metrics"]["recorded_calls"] == 1 and report["memory"]["active"] == 1
    with psycopg.connect(env.admin_dsn) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM mnemion.metric_buckets WHERE tenant_id=%s",
                (env.owner.tenant_id,),
            ).fetchone()[0]
            == 1
        )
