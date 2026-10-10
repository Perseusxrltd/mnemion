from datetime import timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from mnemion.service.api import create_app
from mnemion.service.connector_models import (
    BatchInput,
    BindingInput,
    ConnectorInput,
    ConnectorItemInput,
    FinishInput,
    ResolveInput,
    RunInput,
    ScopeInput,
    utc_now,
)
from mnemion.service.connectors import ConnectorService
from mnemion.service.errors import ServiceError
from mnemion.service.models import (
    GrantInput,
    KeyInput,
    MemoryInput,
    PrincipalInput,
    RevisionInput,
    ReviewInput,
)


@pytest.fixture
def connected(env):
    service = ConnectorService(env.memory)
    identities = {}
    for name in ("connector", "reader", "reviewer", "outsider"):
        person = env.identities.create_principal(env.owner, PrincipalInput(name=name))
        key = env.identities.create_key(env.owner, UUID(person["id"]), KeyInput(name=name))
        identities[name] = env.db.authenticate(key["api_key"]), key["api_key"]
    operator = identities["connector"][0]
    connection = UUID(
        service.create(
            env.owner,
            ConnectorInput(
                name="Company source", provider="slack", principal_id=operator.principal_id
            ),
        )["id"]
    )
    for name in ("reader", "reviewer"):
        service.binding(
            env.owner,
            connection,
            BindingInput(
                external_id="U_" + name, principal_id=identities[name][0].principal_id, role=name
            ),
        )
    scope = service.refresh_scope(
        operator,
        connection,
        ScopeInput(
            external_id="channel:C_PRIVATE",
            name="Private channel",
            members=["U_reader", "U_reviewer", "U_unknown"],
            observed_at=utc_now(),
        ),
    )
    return service, connection, UUID(scope["space_id"]), operator, identities


def begin(service, operator, space, mode="snapshot"):
    run = uuid4()
    service.begin(operator, space, RunInput(run_id=run, mode=mode))
    return run


def item(identity="message:1", text="Private billing decision", revision="1"):
    return ConnectorItemInput(
        external_id=identity, revision=revision, memory=MemoryInput(content=text)
    )


def ingest(service, operator, space, *items, mode="snapshot"):
    run = begin(service, operator, space, mode)
    result = service.page(
        operator,
        space,
        run,
        BatchInput(sequence=0, items=list(items), checkpoint="cursor:" + str(run)),
    )
    service.finish(operator, space, run, FinishInput(complete_inventory=mode == "snapshot"))
    return result


def test_provider_scope_acl_and_expiry_apply_to_all_content_paths(env, connected):
    service, connection, space, operator, identities = connected
    result = ingest(service, operator, space, item())
    memory = UUID(result["items"][0]["memory_id"])
    reader, token = identities["reader"]
    source = env.memory.fetch(reader, memory)["evidence"]["source_revision_id"]
    with TestClient(create_app(env.db, env.embedder)) as client:
        assert (
            client.post(
                "/v1/exports",
                headers={"Authorization": "Bearer " + token},
                json={"space_ids": [str(space)]},
            ).status_code
            == 200
        )
    for denied in (env.owner, identities["outsider"][0]):
        with pytest.raises(ServiceError) as error:
            env.memory.fetch(denied, memory)
        assert error.value.status == 404
    with pytest.raises(ServiceError, match="connector identity mappings"):
        env.identities.grant(
            env.owner, space, identities["outsider"][0].principal_id, GrantInput(role="reader")
        )
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with env.db.transaction(env.owner) as conn:
            conn.execute(
                "INSERT INTO mnemion.space_grants(tenant_id,space_id,principal_id,role) VALUES(%s,%s,%s,'reader')",
                (env.owner.tenant_id, space, identities["outsider"][0].principal_id),
            )
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            "UPDATE mnemion.connector_scopes SET access_valid_until=now()-interval '1 second' WHERE space_id=%s",
            (space,),
        )
    with env.db.transaction(reader) as conn:
        for table in ("memories", "memory_revisions", "source_revisions", "embeddings"):
            assert (
                conn.execute(
                    f"SELECT count(*) AS n FROM mnemion.{table} WHERE space_id=%s", (space,)
                ).fetchone()["n"]
                == 0
            )
    with TestClient(create_app(env.db, env.embedder)) as client:
        auth = {"Authorization": "Bearer " + token}
        for path in (
            f"/v1/memories/{memory}",
            f"/v1/sources/{source}",
            f"/v1/spaces/{space}/memories",
            f"/v1/spaces/{space}/connector-proposals",
        ):
            assert client.get(path, headers=auth).status_code == 404
        for path in ("/v1/recall", "/v1/context"):
            assert (
                client.post(
                    path, headers=auth, json={"space_ids": [str(space)], "query": "billing"}
                ).status_code
                == 404
            )
        assert (
            client.post("/v1/exports", headers=auth, json={"space_ids": [str(space)]}).status_code
            == 404
        )
    service.refresh_scope(
        operator,
        connection,
        ScopeInput(
            external_id="channel:C_PRIVATE",
            name="Private channel",
            members=["U_reviewer"],
            observed_at=utc_now(),
        ),
    )
    with pytest.raises(ServiceError):
        env.memory.fetch(reader, memory)
    assert (
        env.memory.fetch(identities["reviewer"][0], memory)["content"] == "Private billing decision"
    )


def test_checkpoint_page_replay_concurrent_agents_and_atomic_failure(env, connected, monkeypatch):
    service, _, space, operator, _ = connected
    run = begin(service, operator, space)
    with pytest.raises(ServiceError) as error:
        begin(service, operator, space)
    assert error.value.code == "connector_busy"
    batch = BatchInput(sequence=0, items=[item()], checkpoint="first")
    result = service.page(operator, space, run, batch)
    assert service.page(operator, space, run, batch) == result
    with pytest.raises(ServiceError) as error:
        service.page(operator, space, run, BatchInput(sequence=0, items=[], checkpoint="different"))
    assert error.value.code == "page_conflict"
    with pytest.raises(ServiceError) as error:
        service.page(operator, space, run, BatchInput(sequence=2, items=[]))
    assert error.value.code == "page_sequence"
    original = service._item

    def fail_second(conn, identity, scoped, running, incoming, key):
        result = original(conn, identity, scoped, running, incoming, key)
        if incoming.external_id == "message:3":
            raise OSError("Injected failure before page commit")
        return result

    monkeypatch.setattr(service, "_item", fail_second)
    with pytest.raises(OSError):
        service.page(
            operator,
            space,
            run,
            BatchInput(
                sequence=1, items=[item("message:2"), item("message:3")], checkpoint="second"
            ),
        )
    with env.db.transaction(operator) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.connector_items WHERE space_id=%s", (space,)
            ).fetchone()["n"]
            == 1
        )
        assert (
            conn.execute(
                "SELECT checkpoint FROM mnemion.connector_scopes WHERE space_id=%s", (space,)
            ).fetchone()["checkpoint"]
            is None
        )
    result = service.finish(operator, space, run, FinishInput(complete_inventory=True))
    assert service.finish(operator, space, run, FinishInput(complete_inventory=True)) == result
    with env.db.transaction(operator) as conn:
        assert (
            conn.execute(
                "SELECT checkpoint FROM mnemion.connector_scopes WHERE space_id=%s", (space,)
            ).fetchone()["checkpoint"]
            == "first"
        )


def test_operator_pause_survives_refresh_and_enable_until_explicit_resume(env, connected):
    service, connection, space, operator, identities = connected
    result = ingest(service, operator, space, item())
    memory = UUID(result["items"][0]["memory_id"])
    reader = identities["reader"][0]

    def command():
        return ScopeInput(
            external_id="channel:C_PRIVATE",
            name="Private channel",
            members=["U_reader", "U_reviewer"],
            observed_at=utc_now(),
        )

    service.suspend(env.owner, space, "operator_paused")
    with pytest.raises(ServiceError, match="administrator must resume"):
        service.refresh_scope(operator, connection, command())
    with pytest.raises(ServiceError):
        service.resume(operator, space)
    service.disable(env.owner, connection)
    service.enable(env.owner, connection)
    assert service.scopes(env.owner, connection)["items"][0]["operator_paused"]
    with pytest.raises(ServiceError):
        service.refresh_scope(operator, connection, command())
    service.resume(env.owner, space)
    with pytest.raises(ServiceError):
        env.memory.fetch(reader, memory)
    service.refresh_scope(operator, connection, command())
    assert env.memory.fetch(reader, memory)["content"] == "Private billing decision"
    service.enable(env.owner, connection)  # Idempotent enables do not re-suspend a live source.
    assert env.memory.fetch(reader, memory)


def test_local_review_proposals_quarantine_and_deletion_win(env, connected):
    service, _, space, operator, identities = connected
    result = ingest(service, operator, space, item())
    memory = UUID(result["items"][0]["memory_id"])
    reviewer = identities["reviewer"][0]
    env.memory.revise(
        reviewer,
        memory,
        RevisionInput(content="Human correction", expected_version=1, reason="Reviewed"),
        "human-correction",
    )
    result = ingest(service, operator, space, item(text="New upstream evidence", revision="2"))
    assert result["items"][0]["outcome"] == "conflict"
    assert env.memory.fetch(reviewer, memory)["content"] == "Human correction"
    proposal = service.proposals(reviewer, space)["items"][0]
    assert proposal["payload"]["memory"]["content"] == "New upstream evidence"
    with pytest.raises(ServiceError):
        service.proposals(identities["reader"][0], space)
    service.resolve(
        reviewer,
        memory,
        ResolveInput(
            expected_version=2,
            proposal_hash=proposal["proposal_hash"],
            resolution="accept",
            reason="Upstream change confirmed",
        ),
    )
    assert env.memory.fetch(reviewer, memory)["content"] == "New upstream evidence"
    env.memory.review(
        reviewer,
        memory,
        ReviewInput(expected_version=3, state="quarantined", reason="Needs checking"),
    )
    result = ingest(
        service, operator, space, item(text="Yet another upstream change", revision="3")
    )
    assert result["items"][0]["outcome"] == "conflict"
    with pytest.raises(ServiceError):
        env.memory.fetch(identities["reader"][0], memory)
    env.memory.forget(reviewer, memory, expected_version=4, key="erase-upstream-memory")
    assert service.proposals(reviewer, space)["items"] == []
    result = ingest(service, operator, space, item(text="Source still exists", revision="4"))
    assert result["items"][0]["outcome"] == "deletion_preserved"
    while env.worker.run_once():
        pass
    with psycopg.connect(env.admin_dsn) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM mnemion.connector_proposals WHERE memory_id=%s", (memory,)
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM mnemion.memory_revisions WHERE memory_id=%s", (memory,)
            ).fetchone()[0]
            == 0
        )


def test_only_complete_snapshots_infer_withdrawal_and_missing_ids_stay_deleted(env, connected):
    service, _, space, operator, identities = connected
    results = ingest(service, operator, space, item("a"), item("b"))
    memories = {row["external_id"]: UUID(row["memory_id"]) for row in results["items"]}
    run = begin(service, operator, space, "incremental")
    service.page(operator, space, run, BatchInput(sequence=0, items=[item("a")]))
    with pytest.raises(ServiceError):
        service.finish(operator, space, run, FinishInput(complete_inventory=True))
    service.finish(operator, space, run, FinishInput())
    assert env.memory.fetch(identities["reader"][0], memories["b"])
    ingest(service, operator, space, item("a"))
    with pytest.raises(ServiceError):
        env.memory.fetch(identities["reader"][0], memories["b"])
    result = ingest(
        service,
        operator,
        space,
        ConnectorItemInput(external_id="never-positive", revision="deleted", action="delete"),
        mode="incremental",
    )
    assert result["items"][0]["memory_id"] is None
    assert (
        ingest(service, operator, space, item("never-positive"), mode="incremental")["items"][0][
            "outcome"
        ]
        == "deletion_preserved"
    )


def test_permission_mapping_revocation_and_lost_access_suspend_inflight_runs(env, connected):
    service, connection, space, operator, identities = connected
    result = ingest(service, operator, space, item())
    memory = UUID(result["items"][0]["memory_id"])
    run = begin(service, operator, space)
    service.binding(
        env.owner,
        connection,
        BindingInput(external_id="U_reader", principal_id=identities["reader"][0].principal_id),
        remove=True,
    )
    with pytest.raises(ServiceError):
        env.memory.fetch(identities["reader"][0], memory)
    with pytest.raises(ServiceError) as error:
        service.page(operator, space, run, BatchInput(sequence=0, items=[item()]))
    assert error.value.code == "connector_access_stale"
    service.refresh_scope(
        operator,
        connection,
        ScopeInput(
            external_id="channel:C_PRIVATE",
            name="Private channel",
            members=["U_reader", "U_reviewer"],
            observed_at=utc_now(),
        ),
    )
    assert env.memory.fetch(identities["reviewer"][0], memory)
    with pytest.raises(ServiceError):
        env.memory.fetch(identities["reader"][0], memory)
    service.suspend(operator, space, "access_lost")
    with pytest.raises(ServiceError):
        env.memory.fetch(identities["reviewer"][0], memory)
    with env.db.transaction(operator) as conn:
        assert (
            conn.execute(
                "SELECT deleted_at FROM mnemion.memories WHERE id=%s", (memory,)
            ).fetchone()["deleted_at"]
            is None
        )


def test_connector_cannot_grant_itself_access_to_other_spaces_or_register_an_admin(env, connected):
    service, connection, space, operator, identities = connected
    with pytest.raises(ServiceError):
        service.refresh_scope(
            identities["outsider"][0],
            connection,
            ScopeInput(external_id="evil", name="evil", members=[], observed_at=utc_now()),
        )
    with pytest.raises(ServiceError):
        begin(service, operator, env.space)
    with pytest.raises(ServiceError):
        service.create(
            env.owner,
            ConnectorInput(name="Bad", provider="test", principal_id=env.owner.principal_id),
        )
    with pytest.raises(ServiceError):
        service.binding(
            operator,
            connection,
            BindingInput(external_id="U_reader", principal_id=operator.principal_id),
        )
    with pytest.raises(ServiceError):
        service.refresh_scope(
            operator,
            connection,
            ScopeInput(
                external_id="old", name="old", members=[], observed_at=utc_now() - timedelta(days=1)
            ),
        )
    with TestClient(create_app(env.db, env.embedder)) as client:
        auth = {"Authorization": "Bearer " + identities["connector"][1]}
        result = client.get("/v1/connectors", headers=auth)
        assert result.status_code == 200 and len(result.json()["items"]) == 1
        result = client.post(
            f"/v1/connector-scopes/{space}/runs", headers=auth, json={"run_id": str(uuid4())}
        )
        assert result.status_code == 200, result.text
        schema = client.get("/openapi.json").json()
        assert schema["paths"]["/v1/connectors"]["post"]["security"]
