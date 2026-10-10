import json
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from mnemion.connectors.config import ConnectorConfig
from mnemion.connectors.protocol import Document, Scope
from mnemion.connectors.providers import ProviderError
from mnemion.connectors.runner import sync
from mnemion.sdk import Client
from mnemion.service import recovery
from mnemion.service.api import create_app
from mnemion.service.connector_models import BindingInput, ScopeInput, utc_now
from mnemion.service.connectors import ConnectorService
from mnemion.service.db import Database
from mnemion.service.errors import ServiceError
from mnemion.service.identity import IdentityService
from mnemion.service.memory import MemoryService
from mnemion.service.models import KeyInput
from service_tests.test_connectors import begin, ingest, item
from service_tests.test_connectors import connected as connected
from service_tests.test_clients import running as serve


def test_real_http_runner_handles_failed_inventory_and_competing_agents(env, connected):
    service, connection, space, operator, identities = connected
    config = ConnectorConfig.model_validate(
        {
            "service_url": "http://127.0.0.1",
            "connector_id": str(connection),
            "service_token": {"env": "UNUSED_INJECTED_CLIENT"},
            "provider": {
                "type": "slack",
                "team_id": "T123",
                "channels": ["C123"],
                "token": {"env": "UNUSED_INJECTED_PROVIDER"},
            },
        }
    )

    class Adapter:
        access_mode = "provider"
        fail = False

        def scopes(self):
            return ["channel:C_PRIVATE"]

        def access(self, identifier):
            return Scope(identifier, "Private channel", ["U_reader", "U_reviewer"])

        def documents(self, identifier):
            yield Document("message-1", "1", "Decision", "Use Postgres")
            yield None
            if self.fail:
                raise ProviderError("provider_unavailable")
            yield Document("message-2", "1", "Context", "Two replicas")

    adapter = Adapter()
    with (
        serve(create_app(env.db, env.embedder)) as url,
        Client(url, identities["connector"][1]) as client,
    ):
        first = sync(config, adapter=adapter, client=client)
        assert first["completed"] and first["scopes"][0]["outcomes"] == {"created": 2}
        running = begin(service, operator, space)
        busy = sync(config, adapter=adapter, client=client)
        assert not busy["completed"] and busy["scopes"][0]["error_code"] == "connector_busy"
        with env.db.transaction(operator) as conn:
            assert (
                conn.execute(
                    "SELECT state FROM mnemion.connector_runs WHERE id=%s", (running,)
                ).fetchone()["state"]
                == "running"
            )
            assert (
                conn.execute(
                    "SELECT suspended_at FROM mnemion.connector_scopes WHERE space_id=%s", (space,)
                ).fetchone()["suspended_at"]
                is None
            )
        service.suspend(operator, space, "provider_unavailable")
        adapter.fail = True
        failed = sync(config, adapter=adapter, client=client)
        assert not failed["completed"] and failed["scopes"][0]["access_suspended"]
        with env.db.transaction(operator) as conn:
            assert (
                conn.execute(
                    "SELECT count(*) AS n FROM mnemion.memories WHERE space_id=%s AND deleted_at IS NULL",
                    (space,),
                ).fetchone()["n"]
                == 2
            )
        adapter.fail = False
        assert sync(config, adapter=adapter, client=client)["completed"]


def test_recovery_retains_provider_revocations_and_post_backup_negative_source_ids(
    env, connected, postgres, pg_bin, tmp_path
):
    service, connection, space, operator, identities = connected
    saved = ingest(service, operator, space, item("kept"), item("withdrawn"))
    kept = UUID(saved["items"][0]["memory_id"])
    archive, ledger, credentials = [
        tmp_path / name for name in ("source.mnemion", "ledger.json", "recovered.json")
    ]
    recovery.create_backup(env.admin_dsn, archive, pg_bin=pg_bin)
    ingest(service, operator, space, item("kept"))
    later = UUID(
        service.refresh_scope(
            operator,
            connection,
            ScopeInput(
                external_id="after-backup",
                name="Later source",
                members=["U_reader", "U_reviewer"],
                observed_at=utc_now(),
            ),
        )["space_id"]
    )
    ingest(service, operator, later, item("later-source"))
    ingest(service, operator, later)
    service.binding(
        env.owner,
        connection,
        BindingInput(external_id="U_reader", principal_id=identities["reader"][0].principal_id),
        remove=True,
    )
    service.suspend(env.owner, later, "operator_paused")
    recovery.export_ledger(env.admin_dsn, ledger)
    name = "connector_recovery_" + uuid4().hex
    db = None
    try:
        recovery.restore_backup(
            env.admin_dsn,
            archive,
            database_name=name,
            deletion_ledger=ledger,
            credentials_output=credentials,
            pg_bin=pg_bin,
        )
        db = Database(make_conninfo(postgres[1], dbname=name))
        db.open()
        owner_data = next(
            row
            for row in json.loads(credentials.read_text())["organizations"]
            if row["tenant_id"] == str(env.owner.tenant_id)
        )
        owner = db.authenticate(owner_data["api_key"])
        ids = IdentityService(db)
        memory = MemoryService(db, env.embedder.generation)
        restored = ConnectorService(memory)
        recovered = {}
        for role in ("connector", "reader", "reviewer"):
            key = ids.create_key(
                owner, identities[role][0].principal_id, KeyInput(name="Revalidated " + role)
            )
            recovered[role] = db.authenticate(key["api_key"])
        with pytest.raises(ServiceError):
            memory.fetch(recovered["reviewer"], kept)
        restored.refresh_scope(
            recovered["connector"],
            connection,
            ScopeInput(
                external_id="channel:C_PRIVATE",
                name="Private channel",
                members=["U_reader", "U_reviewer"],
                observed_at=utc_now(),
            ),
        )
        assert memory.fetch(recovered["reviewer"], kept)
        with pytest.raises(ServiceError):
            memory.fetch(recovered["reader"], kept)
        later_command = ScopeInput(
            external_id="after-backup",
            name="Later source",
            members=["U_reader", "U_reviewer"],
            observed_at=utc_now(),
        )
        with pytest.raises(ServiceError, match="administrator must resume"):
            restored.refresh_scope(recovered["connector"], connection, later_command)
        restored.resume(owner, later)
        scope = restored.refresh_scope(
            recovered["connector"],
            connection,
            ScopeInput(
                external_id="after-backup",
                name="Later source",
                members=["U_reader", "U_reviewer"],
                observed_at=utc_now(),
            ),
        )
        assert scope["space_id"] == str(later)
        assert (
            ingest(restored, recovered["connector"], later, item("later-source"))["items"][0][
                "outcome"
            ]
            == "deletion_preserved"
        )
    finally:
        if db:
            db.close()
        with psycopg.connect(env.admin_dsn, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
