"""Recovery administration remains independent, scoped and outside memory."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi.testclient import TestClient
import psycopg
import pytest

from mnemion.service.admin import bootstrap_tenant
from mnemion.service.api import create_app
from mnemion.service.errors import ServiceError
from mnemion.service.recovery_directory import (
    RecoveryDirectory,
    RecoveryDirectoryInput,
    RecoveryDirectoryService,
)
from service_tests.test_administration_continuity import authorization, create_identity


def directory():
    return RecoveryDirectory.model_validate(
        {
            "instructions": "recoverydirectoryonlyfixture Use the independently held host login.",
            "independent_url": "https://recovery.example.org/team",
            "hosts": [
                {
                    "name": "Primary",
                    "operator_url": "https://provider.example.org/console",
                    "operator": "Company operator",
                }
            ],
            "materials": [
                {
                    "name": "Encrypted snapshot",
                    "kind": "database_backup",
                    "location": "Company drive / snapshots",
                },
                {
                    "name": "Current revocations",
                    "kind": "recovery_ledger",
                    "location": "Company drive / ledger",
                },
                {
                    "name": "Tracked notes",
                    "kind": "source_mirror",
                    "location": "git@example.org:team/notes.git",
                },
            ],
            "contacts": [
                {
                    "name": "Recovery team",
                    "channel": "Company help desk",
                    "responsibility": "Host and backup access",
                }
            ],
        }
    ).model_dump(mode="json")


def test_independent_admin_controls_directory_without_a_memory_grant(env):
    with TestClient(create_app(env.db, env.embedder, mcp_enabled=False)) as api:
        owner = authorization(env.token)
        _, human = create_identity(
            api, owner, "Independent recovery administrator", administrator=True
        )
        _, agent = create_identity(api, owner, "Restricted assistant", kind="application")
        empty = api.get("/v1/recovery-directory", headers=human)
        assert empty.status_code == 200 and empty.json()["revision"] == 0
        saved = api.put(
            "/v1/recovery-directory",
            headers=human,
            json={"expected_revision": 0, "directory": directory()},
        )
        assert saved.status_code == 200
        record = saved.json()
        assert record["tenant_id"] == str(env.owner.tenant_id) and record["revision"] == 1
        assert record["directory"]["materials"][2]["kind"] == "source_mirror"
        assert (
            api.post(f"/v1/principals/{env.owner.principal_id}/disable", headers=human).status_code
            == 200
        )
        assert api.get("/v1/recovery-directory", headers=human).json() == record
        assert api.get("/v1/recovery-directory", headers=owner).status_code == 401
        assert api.get("/v1/recovery-directory", headers=agent).status_code == 403
        assert (
            api.put(
                "/v1/recovery-directory",
                headers=agent,
                json={"expected_revision": 1, "directory": {}},
            ).status_code
            == 403
        )
        assert all(
            space.get("role") is None
            for space in api.get("/v1/spaces", headers=human).json()["items"]
        )
        agent_identity = env.db.authenticate(agent["Authorization"].removeprefix("Bearer "))
        with env.db.transaction(agent_identity) as conn:
            assert conn.execute("SELECT * FROM mnemion.recovery_directories").fetchall() == []
        with (
            pytest.raises(psycopg.errors.InsufficientPrivilege),
            env.worker_db.worker_transaction(env.owner.tenant_id) as conn,
        ):
            conn.execute("SELECT * FROM mnemion.recovery_directories")


def test_directory_never_enters_memory_search_and_audit_omits_references(env):
    service = RecoveryDirectoryService(env.db)
    saved = service.update(
        env.owner, RecoveryDirectoryInput(expected_revision=0, directory=directory())
    )
    with TestClient(create_app(env.db, env.embedder, mcp_enabled=False)) as api:
        found = api.post(
            "/v1/recall",
            headers=authorization(env.token),
            json={
                "query": "recoverydirectoryonlyfixture",
                "all_accessible": True,
                "mode": "lexical",
            },
        )
        assert found.status_code == 200 and found.json()["hits"] == []
    with env.db.transaction(env.owner) as conn:
        event = conn.execute(
            "SELECT details FROM mnemion.audit_events WHERE action='recovery_directory.updated'"
        ).fetchone()
        assert event["details"] == {"revision": 1, "hosts": 1, "materials": 3, "contacts": 1}
    assert service.get(env.owner) == saved


def test_different_tenants_and_stale_revisions_cannot_replace_a_directory(env):
    other = bootstrap_tenant(
        env.admin_dsn,
        tenant_name="Other company",
        administrator_name="Other owner",
        generation=env.embedder.generation,
    )
    service = RecoveryDirectoryService(env.db)
    other_identity = env.db.authenticate(other["api_key"])
    original = service.update(
        env.owner, RecoveryDirectoryInput(expected_revision=0, directory=directory())
    )
    assert service.get(other_identity)["revision"] == 0
    changed = directory()
    changed["instructions"] = "Other company only"
    service.update(other_identity, RecoveryDirectoryInput(expected_revision=0, directory=changed))
    assert service.get(env.owner) == original
    with pytest.raises(ServiceError) as error:
        service.update(env.owner, RecoveryDirectoryInput(expected_revision=0, directory=changed))
    assert error.value.status == 409 and error.value.code == "recovery_directory_changed"
    assert service.get(env.owner) == original


def test_concurrent_administrators_do_not_silently_lose_an_update(env):
    service = RecoveryDirectoryService(env.db)

    def update(label):
        try:
            return service.update(
                env.owner,
                RecoveryDirectoryInput(expected_revision=0, directory={"instructions": label}),
            )["revision"]
        except ServiceError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(update, ["First reviewed edit", "Second reviewed edit"]))
    assert sorted(outcomes, key=str) == [1, "recovery_directory_changed"]
    assert service.get(env.owner)["revision"] == 1


@pytest.mark.parametrize(
    "invalid",
    [
        {"instructions": "Unreadable\x1bsequence"},
        {"materials": [{"name": "Snapshot", "kind": "database_backup", "location": "  "}]},
        {"contacts": [{"name": "Operator", "channel": "  "}]},
        {"hosts": [{"name": "Host", "operator_url": "javascript:alert(1)"}]},
        {"hosts": [{"name": "Host", "operator_url": "https://name:password@example.org"}]},
        {"hosts": [{"name": "Host", "operator_url": "https://example.org/?token=hidden"}]},
        {"independent_url": "http://example.org"},
        {"contacts": [{"name": " ", "channel": "Contact"}]},
        {"instructions": "mnm_" + "a" * 43},
        {"instructions": "界" * 2000, "hosts": [{"name": "Host", "notes": "x" * 600}]},
        {
            "materials": [
                {
                    "name": "Future proof",
                    "kind": "database_backup",
                    "location": "Copy",
                    "reported_verified_at": "2099-01-01T00:00:00Z",
                }
            ]
        },
    ],
)
def test_invalid_or_secret_directory_input_changes_nothing(env, invalid):
    with TestClient(create_app(env.db, env.embedder, mcp_enabled=False)) as api:
        response = api.put(
            "/v1/recovery-directory",
            headers=authorization(env.token),
            json={"expected_revision": 0, "directory": invalid},
        )
        assert response.status_code == 422
        assert "mnm_" + "a" * 43 not in response.text
        assert (
            api.get("/v1/recovery-directory", headers=authorization(env.token)).json()["revision"]
            == 0
        )


def test_repeated_entry_ids_and_tenant_overrides_are_rejected(env):
    identifier = str(uuid4())
    invalid = {
        "hosts": [{"id": identifier, "name": "Host"}],
        "contacts": [{"id": identifier, "name": "Person", "channel": "Help desk"}],
    }
    with TestClient(create_app(env.db, env.embedder, mcp_enabled=False)) as api:
        for body in (
            {"expected_revision": 0, "directory": invalid},
            {"expected_revision": 0, "directory": {}, "tenant_id": str(uuid4())},
        ):
            assert (
                api.put(
                    "/v1/recovery-directory", headers=authorization(env.token), json=body
                ).status_code
                == 422
            )
