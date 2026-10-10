from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import subprocess
from uuid import UUID

from fastapi.testclient import TestClient
import psycopg
import pytest

from mnemion.connectors.config import ConnectorConfig
from mnemion.connectors.protocol import Document, Scope
from mnemion.connectors.runner import sync, wait_for_sync
from mnemion.sdk import Client, MnemionError
from mnemion.service.api import create_app
from mnemion.service.connector_models import ConnectorInput, SyncReportInput, SyncRequestInput
from mnemion.service.errors import ServiceError
from mnemion.service.models import PrincipalInput, KeyInput
from service_tests.test_connectors import connected as connected
from service_tests.test_clients import running as serve


def config_for(connection, **values):
    return ConnectorConfig.model_validate(
        {
            "service_url": "http://127.0.0.1",
            "connector_id": str(connection),
            "service_token": {"env": "INJECTED_TEST_CREDENTIAL"},
            "provider": {
                "type": "slack",
                "team_id": "T123",
                "channels": ["C123"],
                "token": {"env": "INJECTED_TEST_PROVIDER"},
            },
            **values,
        }
    )


def report(generation, successful=True):
    return SyncReportInput(
        generation=generation,
        successful=successful,
        duration_seconds=0.1,
        error_code=None if successful else "incomplete_inventory",
    )


def test_durable_sync_requests_do_not_lose_racing_requests_or_bypass_connector_acl(env, connected):
    service, connection, _, operator, identities = connected
    assert service.sync_status(operator, connection)["requested_generation"] == 0

    def competing_request():
        try:
            return service.request_sync(
                env.owner, connection, SyncRequestInput(expected_generation=0)
            )
        except ServiceError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: competing_request(), range(2)))
    assert results.count("sync_request_changed") == 1
    first = next(result for result in results if isinstance(result, dict))
    assert first["pending"] and first["requested_generation"] == 1
    with pytest.raises(ServiceError, match="current sync status"):
        service.request_sync(env.owner, connection, SyncRequestInput(expected_generation=0))
    # A scan started before the request, or an incomplete scan, cannot clear it.
    assert service.report_sync(operator, connection, report(0))["pending"]
    assert service.report_sync(operator, connection, report(1, False))["pending"]
    service.request_sync(operator, connection, SyncRequestInput(expected_generation=1))
    state = service.report_sync(operator, connection, report(1))
    assert state["pending"] and state["completed_generation"] == 1
    state = service.report_sync(operator, connection, report(2))
    assert not state["pending"] and state["completed_generation"] == 2
    assert datetime.fromisoformat(state["completed_at"]).tzinfo
    with pytest.raises(ServiceError, match="future request"):
        service.report_sync(operator, connection, report(3))
    with pytest.raises(ServiceError) as denied:
        service.report_sync(env.owner, connection, report(2))
    assert denied.value.status == 403
    for role in ("reader", "reviewer", "outsider"):
        identity = identities[role][0]
        with pytest.raises(ServiceError) as denied:
            service.sync_status(identity, connection)
        assert denied.value.status == 404
        with env.db.transaction(identity) as conn:
            assert not conn.execute("SELECT * FROM mnemion.connector_sync_control").fetchall()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with env.db.transaction(identity) as conn:
                conn.execute(
                    "INSERT INTO mnemion.connector_sync_control(tenant_id,connector_id) VALUES(%s,%s)",
                    (identity.tenant_id, connection),
                )
    with TestClient(create_app(env.db, env.embedder)) as client:
        base = f"/v1/connectors/{connection}/sync"
        assert client.get(base).status_code == 401
        assert (
            client.post(
                base,
                headers={"Authorization": "Bearer " + identities["reader"][1]},
                json={"expected_generation": 2},
            ).status_code
            == 404
        )
        assert (
            client.post(
                base,
                headers={"Authorization": "Bearer " + env.token},
                json={"expected_generation": 2},
            ).status_code
            == 202
        )
    service.disable(env.owner, connection)
    with pytest.raises(ServiceError) as disabled:
        service.request_sync(env.owner, connection, SyncRequestInput(expected_generation=3))
    assert disabled.value.code == "connector_disabled"


def test_live_runner_acknowledges_only_requests_visible_before_scan(env, connected):
    service, connection, _, operator, _ = connected
    config = config_for(connection)
    service.request_sync(env.owner, connection, SyncRequestInput(expected_generation=0))

    class Adapter:
        access_mode = "provider"
        first = True

        def scopes(self):
            return ["channel:C_PRIVATE"]

        def access(self, _):
            return Scope("channel:C_PRIVATE", "Private channel", ["U_reader"])

        def documents(self, _):
            if self.first:
                self.first = False
                service.request_sync(env.owner, connection, SyncRequestInput(expected_generation=1))
                yield Document("gone", "1", "Temporary", "A source removed by the next scan")
            yield Document("kept", "1", "Decision", "Keep Postgres")

    token = env.identities.create_key(env.owner, operator.principal_id, KeyInput(name="Runner"))[
        "api_key"
    ]
    with serve(create_app(env.db, env.embedder)) as url, Client(url, token) as client:
        adapter = Adapter()
        first = sync(config, adapter=adapter, client=client)
        assert first["changed"] == 2 and first["removed"] == 0 and first["control_reported"]
        assert first["sync_generation"] == 1 and first["duration_seconds"] >= 0
        assert datetime.fromisoformat(first["timestamp"]).tzinfo
        assert service.sync_status(operator, connection)["pending"]
        original_request = client.request
        commit_before_failure = False

        def interrupted_report(method, path, **kwargs):
            if path.endswith("/sync/report"):
                if commit_before_failure:
                    original_request(method, path, **kwargs)
                raise MnemionError(503, "unavailable", "The report response was lost")
            return original_request(method, path, **kwargs)

        client.request = interrupted_report
        second = sync(config, adapter=adapter, client=client)
        assert second["removed"] == 1 and second["unchanged"] == 1 and second["changed"] == 0
        assert not second["control_reported"]
        assert service.sync_status(operator, connection)["pending"]
        # Repeating the scan is safe whether the report was lost before or after
        # its transaction committed. Source deletion itself was already durable.
        commit_before_failure = True
        third = sync(config, adapter=adapter, client=client)
        assert third["completed"] and not third["control_reported"]
        assert third["removed"] == 0 and third["unchanged"] == 1
        state = service.sync_status(operator, connection)
        assert not state["pending"] and state["last_removed"] == 0
        assert client.connector_sync_status(str(connection)).completed_generation == 2


def test_git_deletion_after_requested_scan_is_removed_and_counted(env, tmp_path):
    from mnemion.service.connectors import ConnectorService

    def git(*args):
        subprocess.run(
            ["git", "-c", "user.name=Mnemion test", "-c", "user.email=test@example.invalid", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            timeout=10,
        )

    git("init")
    (tmp_path / "keep.md").write_text("# Keep\nPostgres remains the database.")
    (tmp_path / "remove.md").write_text("# Remove\nThis source is being withdrawn.")
    git("add", ".")
    git("commit", "-m", "Initial source")
    identity = env.identities.create_principal(env.owner, PrincipalInput(name="Git runner"))
    token = env.identities.create_key(env.owner, UUID(identity["id"]), KeyInput(name="Git"))[
        "api_key"
    ]
    operator = env.db.authenticate(token)
    service = ConnectorService(env.memory)
    connection = UUID(
        service.create(
            env.owner,
            ConnectorInput(
                name="Git source",
                provider="git",
                principal_id=operator.principal_id,
                access_mode="published",
            ),
        )["id"]
    )
    config = config_for(
        connection,
        provider={
            "type": "git",
            "path": str(tmp_path),
            "scope_id": "repo",
            "name": "Repository",
            "members": [],
            "publish_to_mapped_members": True,
        },
    )
    with serve(create_app(env.db, env.embedder)) as url, Client(url, token) as client:
        assert sync(config, client=client)["changed"] == 2
        git("rm", "remove.md")
        git("commit", "-m", "Withdraw source")
        requested = client.request_connector_sync(str(connection), expected_generation=0)
        assert requested.pending
        result = sync(config, client=client)
        assert result["completed"] and result["removed"] == 1
        state = service.sync_status(operator, connection)
        assert not state["pending"] and state["last_removed"] == 1
        with env.db.transaction(operator) as conn:
            rows = conn.execute(
                "SELECT id FROM mnemion.memories WHERE deleted_at IS NULL"
            ).fetchall()
        assert len(rows) == 1
        assert "Postgres" in env.memory.fetch(operator, rows[0]["id"])["content"]


def test_watch_control_wakes_without_source_poll_and_backs_off_failures():
    from uuid import uuid4

    config = config_for(uuid4())
    now, calls = [0.0], []

    def sleep(seconds):
        now[0] += seconds

    class ClientFixture:
        mode = "pending"

        def request(self, method, path):
            calls.append((now[0], method, path))
            if self.mode == "old":
                raise MnemionError(404, "http_error", "Old service")
            if self.mode == "offline":
                raise MnemionError(503, "service_busy", "Unavailable")
            return {
                "connector_id": str(config.connector_id),
                "requested_generation": 1,
                "completed_generation": 0,
                "requested_at": None,
                "completed_at": None,
                "pending": True,
                "last_attempt_at": None,
                "last_successful": None,
                "last_duration_seconds": None,
                "last_changed": 0,
                "last_removed": 0,
                "last_unchanged": 0,
                "last_error_code": None,
            }

    client = ClientFixture()
    assert wait_for_sync(config, client=client, clock=lambda: now[0], sleep=sleep) == "requested"
    assert now[0] == 5 and len(calls) == 1
    assert (
        wait_for_sync(config, failed=True, client=client, clock=lambda: now[0], sleep=sleep)
        == "requested"
    )
    assert now[0] == 35
    client.mode = "old"
    assert wait_for_sync(config, client=client, clock=lambda: now[0], sleep=sleep) == "poll"
    assert now[0] == 335 and len(calls) == 3
    client.mode = "offline"
    calls.clear()
    assert wait_for_sync(config, client=client, clock=lambda: now[0], sleep=sleep) == "poll"
    assert now[0] == 635 and len(calls) <= 10
