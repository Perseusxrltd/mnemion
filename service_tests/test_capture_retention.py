"""Real database acceptance for approved capture expiry and permanent forgetting."""

from datetime import UTC, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from pydantic import ValidationError

from mnemion.capture_policy import CapturePolicy
from mnemion.service.capture_custody import CaptureCustody
from mnemion.service.capture_models import CaptureGrantInput, CaptureSourceInput
from mnemion.service.capture_models import CapturePolicyChange
from mnemion.service.capture_retention import CaptureRetentionWorker
from mnemion.service.errors import ServiceError
from mnemion.service.fences import pause_space, resume_space
from mnemion.connectors.live_conversations import ConversationProvider
from service_tests.test_capture_custody import changed_revision, page, selected
from service_tests.test_live_conversations import conversation_source as conversation_source


def expiring_policy(days=30):
    return CapturePolicy(
        format="mnemion-capture-policy-v3",
        preset="conversation",
        capture_mode="messages",
        retention="expire_after",
        retention_days=days,
        expiry_scope="captured_fragment_family",
    )


@pytest.fixture
def expiring(env, conversation_source):
    _, connector, operator, _, _, config = conversation_source
    policy = expiring_policy()
    config.provider.capture_policy = policy
    service, source_id, grant_id = CaptureCustody(env.memory), uuid4(), uuid4()
    source = service.source(
        env.owner,
        connector,
        source_id,
        CaptureSourceInput(
            namespace="fixture",
            name="Expiring capture",
            members=["employee:reader"],
            capture_mode="messages",
            keep_accepted=True,
            capture_policy=policy,
        ),
    )
    service.grant(env.owner, source_id, grant_id, CaptureGrantInput(device_key_id=operator.key_id))
    scope, items = selected(config)
    return service, source_id, grant_id, source, scope, items[0]


def expiry(env, source_id):
    with psycopg.connect(env.admin_dsn, row_factory=dict_row) as conn:
        return conn.execute(
            "SELECT * FROM mnemion.capture_expiries WHERE source_id=%s", (source_id,)
        ).fetchone()


def make_due(env, source_id):
    # Move only this synthetic fixture's clock; keep the approved 30-day interval.
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            """UPDATE mnemion.capture_expiries SET first_accepted_at=now()-interval '744 hours',
               expires_at=now()-interval '24 hours' WHERE source_id=%s""",
            (source_id,),
        )


def test_expiry_requires_explicit_version_days_and_family_consent():
    policy = expiring_policy()
    assert policy.keeps_accepted
    for update in (
        {"format": "mnemion-capture-policy-v2"},
        {"retention_days": None},
        {"expiry_scope": None},
        {"retention_days": True},
        {"retention_days": "30"},
        {"retention_days": 0},
        {"retention_days": 3651},
        {"retention": "until_deleted"},
    ):
        with pytest.raises(ValidationError):
            CapturePolicy.model_validate(policy.model_dump(mode="json") | update)
    legacy = CapturePolicy(
        preset="conversation", capture_mode="messages", retention="until_deleted"
    )
    assert "retention_days" not in legacy.model_dump(mode="json")
    assert "expiry_scope" not in legacy.model_dump(mode="json")


def test_server_acceptance_starts_one_deadline_and_revisions_do_not_extend_it(
    env, conversation_source, expiring
):
    service, source_id, grant_id, _, scope, item = expiring
    _, _, operator, _, _, _ = conversation_source
    first = page(source_id, scope, item)
    result = service.page(operator, grant_id, first)
    before = expiry(env, source_id)
    assert before["expires_at"].astimezone(UTC) - before["first_accepted_at"].astimezone(
        UTC
    ) == timedelta(days=30)
    assert before["policy_version"] == 1
    assert service.page(operator, grant_id, first) == result
    service.page(operator, grant_id, page(source_id, scope, changed_revision(item)))
    assert expiry(env, source_id) == before
    with env.db.transaction(operator) as conn:
        rows = conn.execute(
            "SELECT accepted_at,policy_version FROM mnemion.capture_events WHERE source_id=%s ORDER BY accepted_at",
            (source_id,),
        ).fetchall()
    assert len(rows) == 2 and rows[0]["accepted_at"] == before["first_accepted_at"]
    assert all(row["policy_version"] == 1 for row in rows)


def test_due_family_fences_new_intake_then_canonical_cleanup_and_revoked_source(
    env, conversation_source, expiring
):
    service, source_id, grant_id, _, scope, item = expiring
    _, connector, operator, reader, _, _ = conversation_source
    result = service.page(operator, grant_id, page(source_id, scope, item, changed_revision(item)))
    memory_ids = [UUID(row["memory_id"]) for row in result["items"]]
    make_due(env, source_id)
    denied = service.page(
        operator, grant_id, page(source_id, scope, changed_revision(item, text="Late revision"))
    )
    assert denied["items"][0]["outcome"] == "forgotten"
    assert (
        service.fences(operator, grant_id)["items"][0]["lineage_id"]
        == expiry(env, source_id)["lineage_id"]
    )
    # Cleanup uses the stored approval even when the original source is offline/revoked.
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            "UPDATE mnemion.capture_sources SET revoked_at=now() WHERE source_id=%s", (source_id,)
        )
        conn.execute("UPDATE mnemion.api_keys SET revoked_at=now() WHERE id=%s", (operator.key_id,))
    worker = CaptureRetentionWorker(env.worker_db)
    job = worker.claim()
    assert job["source_id"] == source_id
    assert worker.process(job)
    current = expiry(env, source_id)
    assert current["state"] == "expired" and current["completed_at"]
    for memory in memory_ids:
        with pytest.raises(ServiceError):
            env.memory.fetch(reader, memory)
    with psycopg.connect(env.admin_dsn, row_factory=dict_row) as conn:
        for table in ("recovery_denials", "deletion_receipts"):
            assert (
                conn.execute(
                    f"SELECT count(*) AS n FROM mnemion.{table} WHERE memory_id=ANY(%s)",
                    (memory_ids,),
                ).fetchone()["n"]
                == 2
            )
        audit = conn.execute(
            "SELECT principal_id,details FROM mnemion.audit_events WHERE action='memory.deleted' AND resource_id=ANY(%s)",
            ([str(memory) for memory in memory_ids],),
        ).fetchall()
        assert len(audit) == 2
        assert all(row["principal_id"] == operator.principal_id for row in audit)
        assert all(
            row["details"]["cause"] == "capture_retention"
            and row["details"]["approved_by"] == str(env.owner.principal_id)
            for row in audit
        )
    assert worker.claim() is None


def test_cleanup_is_bounded_and_stale_lease_cannot_act(env, conversation_source, expiring):
    service, source_id, grant_id, _, scope, item = expiring
    _, _, operator, _, _, _ = conversation_source
    items = [changed_revision(item, text=f"Retained revision {n}") for n in range(35)]
    service.page(operator, grant_id, page(source_id, scope, *items))
    make_due(env, source_id)
    worker = CaptureRetentionWorker(env.worker_db)
    first = worker.claim()
    assert worker.process(first)
    assert expiry(env, source_id)["state"] == "pending"
    assert not worker.process(first)
    with psycopg.connect(env.admin_dsn) as conn:
        assert (
            conn.execute(
                """SELECT count(*) FROM mnemion.capture_events e JOIN mnemion.memories m ON m.id=e.memory_id
               WHERE e.source_id=%s AND m.deleted_at IS NULL""",
                (source_id,),
            ).fetchone()[0]
            == 3
        )
    second = worker.claim()
    assert second["lease_id"] != first["lease_id"]
    assert worker.process(second) and expiry(env, source_id)["state"] == "expired"


def test_expiry_worker_cannot_set_policy_or_deadline_and_app_cannot_claim(env, expiring):
    service, source_id, grant_id, _, scope, item = expiring
    with pytest.raises(psycopg.errors.InsufficientPrivilege), env.db.transaction(env.owner) as conn:
        conn.execute("SELECT * FROM mnemion.claim_capture_expiry(%s,120)", (uuid4(),))
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        env.worker_db.worker_transaction(env.owner.tenant_id) as conn,
    ):
        conn.execute(
            "UPDATE mnemion.capture_expiries SET expires_at=now() WHERE source_id=%s", (source_id,)
        )
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        env.worker_db.worker_transaction(env.owner.tenant_id) as conn,
    ):
        conn.execute(
            "UPDATE mnemion.capture_policy_versions SET approved_by=%s WHERE source_id=%s",
            (env.owner.principal_id, source_id),
        )
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        env.worker_db.worker_transaction(env.owner.tenant_id) as conn,
    ):
        conn.execute(
            "INSERT INTO mnemion.recovery_denials(tenant_id,space_id,memory_id) VALUES(%s,%s,%s)",
            (env.owner.tenant_id, env.space, uuid4()),
        )


def test_new_policy_can_shorten_but_never_reset_an_approved_family_deadline(
    env, conversation_source, expiring
):
    service, source_id, grant_id, _, scope, item = expiring
    _, connector, operator, _, _, config = conversation_source
    service.page(operator, grant_id, page(source_id, scope, item))
    first = expiry(env, source_id)
    for days in (60, 1, None):
        policy = (
            expiring_policy(days)
            if days
            else CapturePolicy(
                preset="conversation", capture_mode="messages", retention="until_deleted"
            )
        )
        review = service.policy_review(env.owner, connector, source_id)
        service.change_policy(
            env.owner,
            connector,
            source_id,
            uuid4(),
            CapturePolicyChange(
                expected_version=review["source"]["version"],
                review_token=review["review_token"],
                capture_policy=policy,
                previous_grants="retain",
                confirm=True,
            ),
        )
        next_grant = uuid4()
        service.grant(
            env.owner, source_id, next_grant, CaptureGrantInput(device_key_id=operator.key_id)
        )
        config.provider.capture_policy = policy
        provider = ConversationProvider(config.provider)
        assert provider.scopes() == [scope]
        with provider.snapshot(scope, None) as snapshot:
            items = [item for item in snapshot.items() if item is not None]
        service.page(operator, next_grant, page(source_id, scope, *items))
        current = expiry(env, source_id)
        if days == 1:
            assert current["expires_at"] < first["expires_at"] and current["policy_version"] == 3
            first = current
        else:
            assert current == first


def test_migration_pause_and_cleanup_progress_are_visible_then_recover(
    env, conversation_source, expiring
):
    service, source_id, grant_id, source, scope, item = expiring
    _, connector, operator, reader, _, _ = conversation_source
    accepted = service.page(operator, grant_id, page(source_id, scope, item))
    memory = UUID(accepted["items"][0]["memory_id"])
    assert service.retention_status(operator, connector, source_id)["pending_families"] == 1
    with pytest.raises(ServiceError):
        service.retention_status(reader, connector, source_id)
    make_due(env, source_id)
    paused = pause_space(
        env.admin_dsn,
        env.owner.tenant_id,
        UUID(source["space_id"]),
        reason="Synthetic retention migration",
    )
    worker = CaptureRetentionWorker(env.worker_db)
    assert not worker.run_once()
    status = service.retention_status(env.owner, connector, source_id)
    assert status["due_families"] == status["failed_families"] == 1
    assert status["error_code"] == "space_paused" and status["expired_families"] == 0
    assert env.memory.fetch(reader, memory)["content"]  # Scheduled cleanup is not a hard read TTL.
    resume_space(
        env.admin_dsn, env.owner.tenant_id, UUID(source["space_id"]), UUID(paused["token"])
    )
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            "UPDATE mnemion.capture_expiries SET available_at=now() WHERE source_id=%s",
            (source_id,),
        )
    assert worker.run_once()
    status = service.retention_status(env.owner, connector, source_id)
    assert (
        status["expired_families"] == 1 and status["due_families"] == status["failed_families"] == 0
    )
    assert status["purges_pending"] == 1
    for _ in range(100):
        if not env.worker.run_once():
            break
    assert service.retention_status(env.owner, connector, source_id)["purges_pending"] == 0


def test_crashed_worker_lease_can_be_reclaimed_without_duplicate_deletions(
    env, conversation_source, expiring
):
    service, source_id, grant_id, _, scope, item = expiring
    service.page(conversation_source[2], grant_id, page(source_id, scope, item))
    make_due(env, source_id)
    worker = CaptureRetentionWorker(env.worker_db)
    abandoned = worker.claim()
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            "UPDATE mnemion.capture_expiries SET lease_until=now()-interval '1 second' WHERE source_id=%s",
            (source_id,),
        )
    replacement = worker.claim()
    assert replacement["lease_id"] != abandoned["lease_id"]
    assert not worker.process(abandoned)
    assert worker.process(replacement)
    with psycopg.connect(env.admin_dsn) as conn:
        assert (
            conn.execute(
                """SELECT count(*) FROM mnemion.capture_events e JOIN mnemion.deletion_receipts d
            ON d.memory_id=e.memory_id WHERE e.source_id=%s""",
                (source_id,),
            ).fetchone()[0]
            == 1
        )
