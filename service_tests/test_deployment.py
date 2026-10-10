"""Deployment restarts and interrupted setup against a real disposable database."""

import json
import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from mnemion.service import deployment
from mnemion.service.db import Database
from mnemion.service.errors import ServiceError
from mnemion.service.recovery import create_backup, export_ledger, restore_backup


@pytest.fixture
def deployment_database(postgres):
    admin = postgres[0]
    name = "deployment_" + uuid4().hex
    roles = ["mnemion_api_login", "mnemion_worker_login"]
    with psycopg.connect(admin, autocommit=True) as conn:
        assert not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=ANY(%s)", (roles,)).fetchone()
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield make_conninfo(admin, dbname=name)
    finally:
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
            for role in roles:
                conn.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))


def start(dsn, state):
    return deployment.initialize(
        dsn, state, tenant="Deployment test", owner="Operator", api_url="http://127.0.0.1:7892"
    )


def test_restart_preserves_organization_keys_and_separate_credentials(
    deployment_database, tmp_path
):
    dsn = deployment_database
    initial = start(dsn, tmp_path)
    owner_path = tmp_path / "operator/owner.json"
    owner_bytes = owner_path.read_bytes()
    roles_bytes = (tmp_path / "operator/roles.json").read_bytes()
    assert start(dsn, tmp_path) == {**initial, "applied_migrations": []}
    assert owner_path.read_bytes() == owner_bytes
    assert (tmp_path / "operator/roles.json").read_bytes() == roles_bytes
    api_path, worker_path = tmp_path / "api/credentials.json", tmp_path / "worker/credentials.json"
    api, worker = json.loads(api_path.read_text()), json.loads(worker_path.read_text())
    assert set(api) == {"database_url"}
    assert set(worker) == {"worker_database_url"}
    if os.name != "nt":
        assert api_path.stat().st_mode & 0o777 == 0o600
        assert worker_path.stat().st_mode & 0o777 == 0o600
    database = Database(api["database_url"])
    database.open()
    try:
        owner = json.loads(owner_bytes)
        assert str(database.authenticate(owner["api_key"]).tenant_id) == initial["tenant_id"]
    finally:
        database.close()
    with psycopg.connect(dsn) as conn:
        assert conn.execute("SELECT count(*) FROM mnemion.tenants").fetchone()[0] == 1
        conn.execute("UPDATE mnemion.api_keys SET revoked_at=now()")
    # A deliberately revoked bootstrap key must not reappear after restart.
    start(dsn, tmp_path)
    with psycopg.connect(dsn) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM mnemion.api_keys WHERE revoked_at IS NULL"
            ).fetchone()[0]
            == 0
        )
    with pytest.raises(ValueError, match="original operator state"):
        start(dsn, tmp_path / "different-state")


def test_interrupted_roles_reuse_persisted_secrets(deployment_database, tmp_path, monkeypatch):
    original = deployment.bootstrap_tenant
    monkeypatch.setattr(
        deployment,
        "bootstrap_tenant",
        lambda *a, **k: (_ for _ in ()).throw(OSError("fixture interruption")),
    )
    with pytest.raises(OSError):
        start(deployment_database, tmp_path)
    roles_bytes = (tmp_path / "operator/roles.json").read_bytes()
    monkeypatch.setattr(deployment, "bootstrap_tenant", original)
    start(deployment_database, tmp_path)
    assert (tmp_path / "operator/roles.json").read_bytes() == roles_bytes


def test_uncommitted_owner_file_fails_closed(deployment_database, tmp_path, monkeypatch):
    original = deployment.bootstrap_tenant

    def interrupted(*args, credentials_sink, **kwargs):
        def sink(values):
            credentials_sink(values)
            raise OSError("fixture crash after private publication")

        return original(*args, credentials_sink=sink, **kwargs)

    monkeypatch.setattr(deployment, "bootstrap_tenant", interrupted)
    with pytest.raises(OSError):
        start(deployment_database, tmp_path)
    monkeypatch.setattr(deployment, "bootstrap_tenant", original)
    with pytest.raises(ValueError, match="Owner state and database differ"):
        start(deployment_database, tmp_path)
    with psycopg.connect(deployment_database) as conn:
        assert conn.execute("SELECT count(*) FROM mnemion.tenants").fetchone()[0] == 0


def test_verified_restore_activation_rejects_stale_keys_and_resumes_interrupted_publication(
    deployment_database, tmp_path, pg_bin, monkeypatch
):
    dsn = deployment_database
    state = tmp_path / "operator-state"
    start(dsn, state)
    owner_path = state / "operator/owner.json"
    original = json.loads(owner_path.read_text(encoding="utf-8"))
    api_path = state / "api/credentials.json"
    original_api = api_path.read_bytes()
    destination = "activation_" + uuid4().hex
    archive, ledger, recovered_file = (
        tmp_path / name for name in ("snapshot.mnemion", "ledger.json", "recovered.json")
    )
    create_backup(dsn, archive, pg_bin=pg_bin)
    export_ledger(dsn, ledger)
    try:
        restore_backup(
            dsn,
            archive,
            database_name=destination,
            deletion_ledger=ledger,
            credentials_output=recovered_file,
            pg_bin=pg_bin,
        )
        recovered = json.loads(recovered_file.read_text(encoding="utf-8"))
        restored_dsn = make_conninfo(dsn, dbname=destination)
        invalid = {
            **recovered,
            "organizations": [{**recovered["organizations"][0], "api_key": original["api_key"]}],
        }
        with pytest.raises(ValueError, match="do not authenticate"):
            deployment.adopt_restored(restored_dsn, state, invalid, api_url="http://127.0.0.1:7892")
        assert not (state / "operator/active.json").exists()
        assert api_path.read_bytes() == original_api
        publish = deployment._runtime_credentials

        def interrupted(path, values):
            if path == api_path:
                raise OSError("fixture interruption after activation commit")
            publish(path, values)

        monkeypatch.setattr(deployment, "_runtime_credentials", interrupted)
        with pytest.raises(OSError, match="fixture interruption"):
            deployment.adopt_restored(
                restored_dsn, state, recovered, api_url="http://127.0.0.1:7892"
            )
        assert (
            json.loads((state / "operator/active.json").read_text(encoding="utf-8"))["database"]
            == destination
        )
        assert api_path.read_bytes() == original_api
        monkeypatch.setattr(deployment, "_runtime_credentials", publish)
        result = deployment.adopt_restored(
            restored_dsn, state, recovered, api_url="http://127.0.0.1:7892"
        )
        assert result["activated"] is True and result["tenant_id"] == original["tenant_id"]
        assert len(list((state / "operator/history").glob("*.json"))) == 1
        current_api = json.loads(api_path.read_text(encoding="utf-8"))["database_url"]
        assert conninfo_to_dict(current_api)["dbname"] == destination
        database = Database(current_api)
        database.open()
        try:
            database.authenticate(recovered["api_key"])
            with pytest.raises(ServiceError):
                database.authenticate(original["api_key"])
        finally:
            database.close()
        start(restored_dsn, state)
        with pytest.raises(ValueError, match="activation record differ"):
            start(dsn, state)
        old_database = Database(json.loads(original_api)["database_url"])
        old_database.open()
        try:
            old_database.authenticate(original["api_key"])
        finally:
            old_database.close()
        secret = tmp_path / "database.password"
        secret.write_text("test-password-is-at-least-32-characters", encoding="utf-8")
        monkeypatch.setenv("MNEMION_DATABASE_PASSWORD_FILE", str(secret))
        monkeypatch.setenv("MNEMION_DEPLOYMENT_STATE", str(state))
        assert conninfo_to_dict(deployment._admin_dsn())["dbname"] == destination
        assert (
            conninfo_to_dict(deployment._admin_dsn("explicit_restore"))["dbname"]
            == "explicit_restore"
        )
    finally:
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(destination)
                )
            )
