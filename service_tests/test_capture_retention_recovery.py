"""Older real snapshots cannot resurrect a family's later approved expiry."""

from copy import deepcopy
from datetime import datetime, timedelta
import json
from uuid import UUID, uuid4

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
import pytest

from mnemion.service import capture_recovery, capture_retention_recovery, recovery
from mnemion.service.capture_custody import CaptureCustody
from mnemion.service.capture_models import CaptureGrantInput, CapturePolicyChange
from mnemion.service.capture_retention import CaptureRetentionWorker
from mnemion.service.db import Database
from mnemion.service.errors import ServiceError
from mnemion.service.memory import MemoryService
from mnemion.service.models import json_value
from mnemion.capture_identity import capture_lineage_id
from mnemion.connectors.live_conversations import ConversationProvider
from service_tests.test_capture_custody import custody as custody, page, selected
from service_tests.test_capture_retention import (
    expiring as expiring,
    expiry,
    expiring_policy,
    make_due,
)
from service_tests.test_live_conversations import (
    conversation_source as conversation_source,
    encoded,
)
from service_tests.test_recovery import destination as destination


def test_expiry_recovery_rejects_missing_deadlines_or_approval_and_cannot_extend(
    env, conversation_source, expiring
):
    service, source_id, grant_id, _, scope, item = expiring
    operator = conversation_source[2]
    service.page(operator, grant_id, page(source_id, scope, item))
    before = expiry(env, source_id)
    with psycopg.connect(env.admin_dsn, row_factory=dict_row) as conn:
        ledger = json_value(capture_recovery.capture(conn))
    tenants = {row["tenant_id"] for row in ledger["sources"]}
    capture_recovery.validate(ledger, tenants)
    bad = deepcopy(ledger)
    bad["expiries"] = [row for row in bad["expiries"] if row["source_id"] != str(source_id)]
    with (
        pytest.raises(ValueError, match="complete expiry-aware"),
        psycopg.connect(env.admin_dsn, row_factory=dict_row) as conn,
    ):
        capture_recovery.restore(conn, bad)
    bad = deepcopy(ledger)
    next(row for row in bad["policies"] if row["source_id"] == str(source_id))["approved_by"] = None
    with pytest.raises(ValueError, match="approval"):
        capture_recovery.validate(bad, tenants)
    bad = deepcopy(ledger)
    bad["version"] = 2
    del bad["expiries"]
    with pytest.raises(ValueError, match="expiry-aware"):
        capture_recovery.validate(bad, tenants)
    later = deepcopy(ledger)
    row = next(row for row in later["expiries"] if row["source_id"] == str(source_id))
    for name in ("first_accepted_at", "expires_at"):
        row[name] = (datetime.fromisoformat(row[name]) + timedelta(days=1)).isoformat()
    capture_recovery.validate(later, tenants)
    with psycopg.connect(env.admin_dsn, row_factory=dict_row) as conn:
        capture_recovery.restore(conn, later)
    assert expiry(env, source_id) == before


def test_restore_applies_later_family_expiry_before_publication(
    env, conversation_source, custody, postgres, pg_bin, tmp_path, destination
):
    service, source_id, original_grant, source, _ = custody
    _, connector, operator, _, _, config = conversation_source
    scope, items = selected(config)
    accepted = service.page(operator, original_grant, page(source_id, scope, *items))
    memory = UUID(accepted["items"][0]["memory_id"])
    archive, ledger, credentials = [
        tmp_path / name for name in ("before-expiry.mnemion", "ledger.json", "owner.json")
    ]
    recovery.create_backup(env.admin_dsn, archive, pg_bin=pg_bin)
    policy = expiring_policy(30)
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
    later_grant = uuid4()
    service.grant(
        env.owner, source_id, later_grant, CaptureGrantInput(device_key_id=operator.key_id)
    )
    config.provider.capture_policy = policy
    previous_lineage = capture_lineage_id(scope, items[0].model_dump(mode="json"))
    provider = ConversationProvider(config.provider)
    assert provider.scopes() == [scope]
    with provider.snapshot(scope, None) as snapshot:
        items = [item for item in snapshot.items() if item is not None]
    assert capture_lineage_id(scope, items[0].model_dump(mode="json")) == previous_lineage
    service.page(operator, later_grant, page(source_id, scope, *items))
    make_due(env, source_id)
    due = expiry(env, source_id)
    recovery.export_ledger(env.admin_dsn, ledger)
    recovery.restore_backup(
        env.admin_dsn,
        archive,
        database_name=destination,
        deletion_ledger=ledger,
        credentials_output=credentials,
        pg_bin=pg_bin,
    )
    db = Database(make_conninfo(postgres[1], dbname=destination))
    db.open()
    try:
        owner_data = next(
            row
            for row in json.loads(credentials.read_text())["organizations"]
            if row["tenant_id"] == str(env.owner.tenant_id)
        )
        owner = db.authenticate(owner_data["api_key"])
        restored_memory = MemoryService(db, env.embedder.generation)
        with pytest.raises(ServiceError):
            restored_memory.fetch(owner, memory)
        with psycopg.connect(
            make_conninfo(env.admin_dsn, dbname=destination), row_factory=dict_row
        ) as conn:
            expiry_row = conn.execute(
                "SELECT * FROM mnemion.capture_expiries WHERE source_id=%s", (source_id,)
            ).fetchone()
            assert (
                expiry_row["expires_at"] == due["expires_at"] and expiry_row["state"] == "expired"
            )
            assert conn.execute(
                "SELECT 1 FROM mnemion.recovery_denials WHERE memory_id=%s", (memory,)
            ).fetchone()
            assert (
                conn.execute(
                    "SELECT current_revision_id FROM mnemion.memories WHERE id=%s", (memory,)
                ).fetchone()["current_revision_id"]
                is None
            )
            version = conn.execute(
                "SELECT approved_by FROM mnemion.capture_policy_versions WHERE source_id=%s AND policy_version=2",
                (source_id,),
            ).fetchone()
            assert version["approved_by"] == env.owner.principal_id
        restored = CaptureCustody(restored_memory)
        assert restored.source_status(owner, connector, source_id)["policy_version"] == 2
    finally:
        db.close()
    assert CaptureRetentionWorker(env.worker_db).run_once()


def test_deadline_crossed_during_reconciliation_is_purged_before_marked_complete(
    env, conversation_source, expiring
):
    service, source_id, grant_id, _, scope, item = expiring
    operator, config = conversation_source[2], conversation_source[5]
    first = service.page(operator, grant_id, page(source_id, scope, item))["items"][0]
    (config.provider.path / "second.jsonl").write_bytes(
        encoded("A separate fragment approaching expiry")
    )
    provider = ConversationProvider(config.provider)
    second_scope = next(identifier for identifier in provider.scopes() if identifier != scope)
    with provider.snapshot(second_scope, None) as snapshot:
        items = [item for item in snapshot.items() if item is not None]
    second = service.page(operator, grant_id, page(source_id, second_scope, *items))["items"][0]
    applied, advanced = [], False
    with psycopg.connect(env.admin_dsn, row_factory=dict_row) as conn:

        def advance(lineage):
            conn.execute(
                """UPDATE mnemion.capture_expiries SET first_accepted_at=now()-interval '744 hours',
                expires_at=now()-interval '24 hours' WHERE source_id=%s AND lineage_id=%s""",
                (source_id, lineage),
            )

        advance(first["lineage_id"])

        def delete_and_advance(connection, ledger):
            nonlocal advanced
            ids = [row["memory_id"] for row in ledger["deletions"]]
            applied.extend(ids)
            result = recovery._reconcile_deletions(connection, ledger)
            if first["memory_id"] in ids:
                advance(second["lineage_id"])
                advanced = True
            return result

        capture_retention_recovery.reconcile(conn, delete_and_advance)
        assert advanced and first["memory_id"] in applied and second["memory_id"] in applied
        rows = conn.execute(
            """SELECT m.deleted_at,m.current_revision_id,x.state
            FROM mnemion.capture_expiries x JOIN mnemion.capture_events e USING(tenant_id,source_id,lineage_id)
            JOIN mnemion.memories m ON m.id=e.memory_id WHERE x.source_id=%s""",
            (source_id,),
        ).fetchall()
        assert len(rows) == 2
        assert all(
            row["deleted_at"] and row["current_revision_id"] is None and row["state"] == "expired"
            for row in rows
        )
