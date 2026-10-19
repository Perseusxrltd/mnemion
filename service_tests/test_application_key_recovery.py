"""Application continuity never revives newer revocations or privileged keys."""

from uuid import UUID, uuid4
import json

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
import pytest

from mnemion.service import recovery
from mnemion.service.db import Database
from mnemion.service.errors import ServiceError
from mnemion.service.memory import MemoryService
from mnemion.service.models import GrantInput, KeyInput, MemoryInput, PrincipalInput


def test_ledger_can_capture_a_database_without_the_later_session_key_column(env):
    principal = env.identities.create_principal(env.owner, PrincipalInput(name="Legacy agent"))
    key = env.identities.create_key(env.owner, UUID(principal["id"]), KeyInput(name="Existing key"))
    with psycopg.connect(env.admin_dsn, row_factory=dict_row) as connection:
        try:
            # Reproduce the precise pre-sign-in table boundary without
            # committing a schema change to the shared disposable fixture.
            connection.execute(
                "ALTER TABLE mnemion.api_keys RENAME COLUMN session_key TO fixture_later_column"
            )
            ledger = recovery._ledger(connection)
            assert any(row["id"] == key["id"] for row in ledger["application_key_state"]["keys"])
            assert key["api_key"] not in json.dumps(ledger)
        finally:
            connection.rollback()


def test_reviewed_application_keys_survive_but_later_access_and_deletion_denials_win(
    env, postgres, pg_bin, tmp_path
):
    from mnemion.service.admin import bootstrap_tenant

    other = bootstrap_tenant(
        env.admin_dsn, tenant_name="Rotation-only organization", administrator_name="Other owner"
    )
    keys = {}
    for name in ("kept", "revoked", "disabled", "admin", "human", "session", "expired"):
        principal = env.identities.create_principal(
            env.owner,
            PrincipalInput(
                name=name,
                kind="human" if name == "human" else "application",
                administrator=name == "admin",
            ),
        )
        key = env.identities.create_key(env.owner, UUID(principal["id"]), KeyInput(name=name))
        env.identities.grant(
            env.owner, env.space, UUID(principal["id"]), GrantInput(role="contributor")
        )
        keys[name] = key, principal
    with psycopg.connect(env.admin_dsn) as connection:
        connection.execute(
            "UPDATE mnemion.api_keys SET session_key=true WHERE id=%s", (keys["session"][0]["id"],)
        )
    saved = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="Remove this after the snapshot"),
        "before-host-recovery",
    )
    archive, ledger, credentials = (
        tmp_path / name for name in ("backup.mnemion", "ledger.json", "credentials.json")
    )
    recovery.create_backup(env.admin_dsn, archive, pg_bin=pg_bin)
    with psycopg.connect(env.admin_dsn) as connection:
        connection.execute(
            "UPDATE mnemion.api_keys SET revoked_at=clock_timestamp() WHERE id=%s",
            (keys["revoked"][0]["id"],),
        )
        connection.execute(
            "UPDATE mnemion.api_keys SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s",
            (keys["expired"][0]["id"],),
        )
        connection.execute(
            "UPDATE mnemion.principals SET disabled_at=clock_timestamp() WHERE id=%s",
            (keys["disabled"][1]["id"],),
        )
    env.memory.forget(
        env.owner, UUID(saved["memory_id"]), expected_version=1, key="withdraw-before-recovery"
    )
    recovery.export_ledger(env.admin_dsn, ledger)
    name = "keys_recovered_" + uuid4().hex
    database = None
    try:
        result = recovery.restore_backup(
            env.admin_dsn,
            archive,
            database_name=name,
            deletion_ledger=ledger,
            credentials_output=credentials,
            pg_bin=pg_bin,
            preserve_application_keys=True,
        )
        assert result["application_keys_preserved"] >= 1
        assert not result["keys_rotated"]
        database = Database(make_conninfo(postgres[1], dbname=name))
        database.open()
        allowed = database.authenticate(keys["kept"][0]["api_key"])
        assert allowed.principal_id == UUID(keys["kept"][1]["id"])
        for rejected in (
            env.token,
            other["api_key"],
            *(item[0]["api_key"] for label, item in keys.items() if label != "kept"),
        ):
            with pytest.raises(ServiceError):
                database.authenticate(rejected)
        with pytest.raises(ServiceError):
            MemoryService(database, env.embedder.generation).fetch(
                allowed, UUID(saved["memory_id"])
            )
        issued = json.loads(credentials.read_text())
        assert [
            item
            for item in issued["preserved_application_keys"]
            if item["tenant_id"] == str(env.owner.tenant_id)
        ] == [{"tenant_id": str(env.owner.tenant_id), "key_id": keys["kept"][0]["id"]}]
        assert result["application_keys_preserved"] == len(issued["preserved_application_keys"])
        with psycopg.connect(make_conninfo(env.admin_dsn, dbname=name)) as connection:
            audits = {
                str(tenant): details
                for tenant, details in connection.execute(
                    "SELECT tenant_id,details FROM mnemion.audit_events WHERE action='recovery.completed' AND resource_id=%s",
                    (issued["backup_id"],),
                )
            }
        assert audits[str(env.owner.tenant_id)]["application_keys_preserved"] == 1
        assert not audits[str(env.owner.tenant_id)]["keys_rotated"]
        assert audits[other["tenant_id"]]["application_keys_preserved"] == 0
        assert audits[other["tenant_id"]]["keys_rotated"]
    finally:
        if database is not None:
            database.close()
        with psycopg.connect(env.admin_dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
