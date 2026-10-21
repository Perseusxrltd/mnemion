"""Acceptance for custody review findings: family forgetting and stale authority."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from mnemion.capture_identity import capture_lineage_id
from mnemion.service.admin import bootstrap_tenant
from mnemion.service.api import create_app
from mnemion.service.capture_custody import CaptureCustody
from mnemion.service.capture_models import CaptureGrantInput, CaptureSourceInput
from mnemion.service.connector_models import BindingInput
from mnemion.service.errors import ServiceError
from service_tests.test_capture_custody import (
    changed_revision,
    conversation_source as conversation_source,
    custody as custody,
    page,
    selected,
)


def complete_family(env, conversation_source, *, long=False):
    _, connector, operator, reader, secret, config = conversation_source
    service, source_id, grant_id = CaptureCustody(env.memory), uuid4(), uuid4()
    source = service.source(
        env.owner,
        connector,
        source_id,
        CaptureSourceInput(
            namespace="fixture",
            name="Complete custody",
            members=["employee:reader"],
            capture_mode="complete",
            keep_accepted=True,
        ),
    )
    service.grant(env.owner, source_id, grant_id, CaptureGrantInput(device_key_id=operator.key_id))
    scope, items = selected(
        config, "A selected fragment. " * (5000 if long else 1), mode="complete"
    )
    first = page(source_id, scope, *items)
    original = service.page(operator, grant_id, first)
    revisions = [
        changed_revision(item, text="Later version " + str(i)) for i, item in enumerate(items)
    ]
    if long:
        revisions.extend(
            changed_revision(items[0], text="Accepted tail revision " + str(i)) for i in range(33)
        )
    second = page(source_id, scope, *revisions)
    later = service.page(operator, grant_id, second)
    return service, source_id, grant_id, source, scope, items, first, second, original, later


def test_fragment_forget_removes_parts_raw_projection_and_all_retained_revisions(
    env, conversation_source
):
    service, source_id, grant_id, source, scope, items, first, second, original, later = (
        complete_family(env, conversation_source, long=True)
    )
    _, _, operator, reader, _, _ = conversation_source
    ids = [UUID(item["memory_id"]) for result in (original, later) for item in result["items"]]
    assert len(items) > 2  # Actual selected raw/projection documents split into multiple parts.
    assert len(ids) > 32  # Withdrawal crosses its bounded identity-page boundary.
    assert len({capture_lineage_id(scope, item.model_dump(mode="json")) for item in items}) == 1
    target = ids[-1]
    preview = env.memory.fetch(reader, target)["capture_forget"]
    assert preview["retained_memories"] == len(ids)
    assert preview["scope"] == "conversation_fragment"
    assert preview["includes_adjacent_messages"] and preview["includes_revisions_and_projections"]
    # Authorization of the requested memory precedes any family mutation.
    with pytest.raises(ServiceError):
        env.memory.forget(env.owner, target, expected_version=1, key="unauthorized-family")
    receipt = env.memory.forget(reader, target, expected_version=1, key="forget-fragment-family")
    assert receipt["capture_forget"] == preview
    assert (
        env.memory.forget(reader, target, expected_version=1, key="forget-fragment-family")
        == receipt
    )
    for identifier in ids:
        with pytest.raises(ServiceError):
            env.memory.fetch(reader, identifier)
    for old in (first, second):
        assert all(
            item["outcome"] == "forgotten"
            for item in service.page(operator, grant_id, old)["items"]
        )
    late = service.page(
        operator,
        grant_id,
        page(source_id, scope, changed_revision(items[0], text="A delayed raw revision")),
    )
    assert late["items"][0]["outcome"] == "forgotten"
    with env.db.transaction(operator) as conn:
        assert conn.execute(
            "SELECT count(*) AS n FROM mnemion.deletion_receipts WHERE space_id=%s",
            (UUID(source["space_id"]),),
        ).fetchone()["n"] == len(ids)
        assert conn.execute(
            "SELECT count(*) AS n FROM mnemion.recovery_denials WHERE space_id=%s",
            (UUID(source["space_id"]),),
        ).fetchone()["n"] == len(ids)
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.capture_denials WHERE source_id=%s", (source_id,)
            ).fetchone()["n"]
            == 1
        )
    # Exercise canonical worker erasure for exactly these isolated purge jobs.
    with env.worker_db.worker_transaction(operator.tenant_id) as conn:
        jobs = conn.execute(
            """UPDATE mnemion.jobs j SET state='leased',lease_id=%s,lease_until=now()+interval '1 minute'
               FROM mnemion.operations o WHERE o.tenant_id=j.tenant_id AND o.id=j.operation_id
                 AND o.memory_id=ANY(%s) AND j.kind='purge' RETURNING j.*""",
            (uuid4(), ids),
        ).fetchall()
    assert len(jobs) == len(ids)
    for job in jobs:
        assert env.worker.process(job)
    with env.db.transaction(operator) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.source_revisions WHERE space_id=%s",
                (UUID(source["space_id"]),),
            ).fetchone()["n"]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.deletion_receipts WHERE space_id=%s AND purged_at IS NULL",
                (UUID(source["space_id"]),),
            ).fetchone()["n"]
            == 0
        )


def test_a_failed_sibling_withdrawal_rolls_back_the_entire_family(
    env, conversation_source, monkeypatch
):
    _, source_id, _, source, _, _, _, _, original, later = complete_family(env, conversation_source)
    _, _, operator, reader, _, _ = conversation_source
    target = UUID(later["items"][0]["memory_id"])
    normal = env.memory._operation
    deletes = 0

    def fail_second(*args, **kwargs):
        nonlocal deletes
        if args[-1] == "delete":
            deletes += 1
            if deletes == 2:
                raise RuntimeError("Injected canonical deletion failure")
        return normal(*args, **kwargs)

    monkeypatch.setattr(env.memory, "_operation", fail_second)
    with pytest.raises(RuntimeError, match="Injected canonical"):
        env.memory.forget(reader, target, expected_version=1, key="atomic-family")
    assert deletes == 2
    for result in (original, later):
        for item in result["items"]:
            assert env.memory.fetch(reader, UUID(item["memory_id"]))
    with env.db.transaction(operator) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.capture_denials WHERE source_id=%s", (source_id,)
            ).fetchone()["n"]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.deletion_receipts WHERE space_id=%s",
                (UUID(source["space_id"]),),
            ).fetchone()["n"]
            == 0
        )


def test_source_versions_prevent_stale_audience_reenrollment_and_allow_safe_replay(
    env, conversation_source, custody
):
    service, source_id, grant_id, source, command = custody
    _, connector, operator, reader, _, config = conversation_source
    scope, items = selected(config)
    saved = service.page(operator, grant_id, page(source_id, scope, *items))
    memory = UUID(saved["items"][0]["memory_id"])
    with TestClient(create_app(env.db, env.embedder)) as client:
        endpoint = f"/v1/connectors/{connector}/capture-sources/{source_id}"
        headers = {"Authorization": "Bearer " + env.token}
        assert client.get(endpoint, headers=headers).json()["version"] == 1
        replacement = command.model_copy(update={"expected_version": 1, "members": []})
        changed = client.put(endpoint, headers=headers, json=replacement.model_dump(mode="json"))
        assert changed.status_code == 200 and changed.json()["version"] == 2
        assert (
            client.put(endpoint, headers=headers, json=replacement.model_dump(mode="json")).json()
            == changed.json()
        )
        old = client.put(endpoint, headers=headers, json=command.model_dump(mode="json"))
        assert old.status_code == 409 and old.json()["error"]["code"] == "version_conflict"
        assert client.get(endpoint, headers=headers).json()["members"] == []
    with pytest.raises(ServiceError):
        env.memory.fetch(reader, memory)
    first = service.revoke_source(env.owner, connector, source_id)
    assert first["version"] == 3
    assert service.revoke_source(env.owner, connector, source_id)["version"] == 3


def test_source_history_metadata_does_not_grant_content_access(env, conversation_source, custody):
    service, source_id, grant_id, source, _ = custody
    _, connector, operator, reader, _, config = conversation_source
    assert not source["has_capture_history"]
    scope, items = selected(config)
    saved = service.page(operator, grant_id, page(source_id, scope, *items))
    memory_id = UUID(saved["items"][0]["memory_id"])
    for identity in (env.owner, operator):
        assert service.source_status(identity, connector, source_id)["has_capture_history"]
    # An unmapped administrator sees the migration guard, never the event rows.
    with env.db.transaction(env.owner) as conn:
        assert not conn.execute(
            "SELECT 1 FROM mnemion.capture_events WHERE source_id=%s", (source_id,)
        ).fetchall()
        assert not conn.execute(
            "SELECT mnemion.capture_source_has_history(%s) AS present", (uuid4(),)
        ).fetchone()["present"]
    with pytest.raises(ServiceError):
        env.memory.fetch(env.owner, memory_id)
    assert env.memory.fetch(reader, memory_id)
    # Content readership does not grant source administration or its metadata.
    with env.db.transaction(reader) as conn:
        assert not conn.execute(
            "SELECT mnemion.capture_source_has_history(%s) AS present", (source_id,)
        ).fetchone()["present"]
    with pytest.raises(ServiceError):
        service.source_status(reader, connector, source_id)
    assert service.revoke_source(env.owner, connector, source_id)["has_capture_history"]


def test_custody_rows_and_operations_cannot_cross_tenants(env, conversation_source, custody):
    service, source_id, grant_id, _, command = custody
    _, connector, operator, _, _, config = conversation_source
    scope, items = selected(config)
    saved = service.page(operator, grant_id, page(source_id, scope, *items))
    setup = bootstrap_tenant(
        env.admin_dsn,
        tenant_name="Other isolated tenant",
        administrator_name="Other owner",
        generation=env.embedder.generation,
    )
    foreign = env.db.authenticate(setup["api_key"])
    for invoke in (
        lambda: service.source_status(foreign, connector, source_id),
        lambda: service.page(foreign, grant_id, page(source_id, scope, *items)),
        lambda: service.status(foreign, grant_id, revoke=True),
        lambda: service.fences(foreign, grant_id),
        lambda: env.memory.fetch(foreign, UUID(saved["items"][0]["memory_id"])),
    ):
        with pytest.raises(ServiceError):
            invoke()
    with env.db.transaction(foreign) as conn:
        assert not conn.execute(
            "SELECT mnemion.capture_source_has_history(%s) AS present", (source_id,)
        ).fetchone()["present"]
        for table in (
            "capture_sources",
            "capture_grants",
            "capture_events",
            "capture_pages",
            "capture_denials",
        ):
            assert conn.execute(f"SELECT count(*) AS n FROM mnemion.{table}").fetchone()["n"] == 0
    assert service.source_status(env.owner, connector, source_id)["version"] == 1


def test_fragment_family_does_not_conflate_other_offsets_or_generations(conversation_source):
    *_, config = conversation_source
    scope, items = selected(config, mode="complete")
    first = items[0].model_dump(mode="json")
    identifier = capture_lineage_id(scope, first)
    first["memory"]["metadata"]["source_byte_start"] += 1
    assert capture_lineage_id(scope, first) != identifier
    first["memory"]["metadata"]["source_byte_start"] -= 1
    first["memory"]["metadata"]["source_generation"] = "f" * 32
    assert capture_lineage_id(scope, first) != identifier


def test_pages_enforce_actual_byte_limit(conversation_source):
    *_, config = conversation_source
    source_id = uuid4()
    scope, items = selected(config)
    large = [
        changed_revision(items[0], text=str(i) + "x" * (65536 - len(str(i)))) for i in range(12)
    ]
    assert len(page(source_id, scope, *large[:11]).events) == 11
    with pytest.raises(ValidationError, match="1.5 MB"):
        page(source_id, scope, *large)


@pytest.mark.parametrize(
    "revocation,when",
    [("source", "before"), ("connector", "before"), ("principal", "before"), ("source", "during")],
)
def test_revoked_custody_blocks_background_inference_and_late_vector_publication(
    env, conversation_source, custody, monkeypatch, revocation, when
):
    service, source_id, grant_id, source, _ = custody
    legacy, connector, operator, _, _, config = conversation_source
    scope, items = selected(config)
    saved = service.page(operator, grant_id, page(source_id, scope, *items))
    operation = UUID(saved["items"][0]["operation_id"])

    def revoke():
        if revocation == "source":
            service.revoke_source(env.owner, connector, source_id)
        elif revocation == "connector":
            legacy.disable(env.owner, connector)
        else:
            env.identities.disable_principal(env.owner, operator.principal_id)

    calls = []
    original = env.embedder.document

    def inference(text):
        calls.append(True)
        assert when == "during"
        revoke()
        return original(text)

    monkeypatch.setattr(env.embedder, "document", inference)
    if when == "before":
        revoke()
    with env.worker_db.worker_transaction(operator.tenant_id) as conn:
        job = conn.execute(
            """UPDATE mnemion.jobs SET state='leased',lease_id=%s,lease_until=now()+interval '1 minute',attempts=1
               WHERE operation_id=%s RETURNING *""",
            (uuid4(), operation),
        ).fetchone()
    assert env.worker.process(job) is False
    assert len(calls) == (1 if when == "during" else 0)
    with env.worker_db.worker_transaction(operator.tenant_id) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.embeddings WHERE space_id=%s",
                (UUID(source["space_id"]),),
            ).fetchone()["n"]
            == 0
        )
        assert conn.execute(
            "SELECT state,error_code FROM mnemion.jobs WHERE id=%s", (job["id"],)
        ).fetchone() == {"state": "pending", "error_code": "source_access_unavailable"}


@pytest.mark.parametrize("creating", [False, True])
def test_source_members_and_binding_removal_serialize_including_new_source(
    env, conversation_source, custody, monkeypatch, creating
):
    from mnemion.service import capture_custody

    service, source_id, _, source, command = custody
    legacy, connector, _, reader, _, _ = conversation_source
    entered, release = threading.Event(), threading.Event()
    original = capture_custody.source_lock
    target = uuid4() if creating else source_id
    update = (
        command
        if creating
        else command.model_copy(
            update={"expected_version": 1, "members": ["employee:reader", "later-approved-member"]}
        )
    )

    def paused(conn, identifier):
        if identifier == target:
            entered.set()
            assert release.wait(4)
        original(conn, identifier)

    monkeypatch.setattr(capture_custody, "source_lock", paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        configured = pool.submit(service.source, env.owner, connector, target, update)
        assert entered.wait(3)
        removed = pool.submit(
            legacy.binding,
            env.owner,
            connector,
            BindingInput(
                external_id="employee:reader", principal_id=reader.principal_id, role="reviewer"
            ),
            remove=True,
        )
        try:
            deadline = time.monotonic() + 2
            with psycopg.connect(env.admin_dsn, autocommit=True) as conn:
                while not conn.execute(
                    "SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE 'DELETE FROM mnemion.connector_bindings%'"
                ).fetchone():
                    assert time.monotonic() < deadline
                    time.sleep(0.01)
            assert not removed.done()
        finally:
            release.set()
        result = configured.result(timeout=3)
        removed.result(timeout=3)
    with env.db.transaction(env.owner) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.space_grants WHERE space_id=ANY(%s) AND principal_id=%s",
                ([UUID(source["space_id"]), UUID(result["space_id"])], reader.principal_id),
            ).fetchone()["n"]
            == 0
        )


@pytest.mark.parametrize("binding", ["missing", "reader"])
def test_stale_derived_grant_cannot_override_current_membership_role(
    env, conversation_source, custody, binding
):
    service, source_id, grant_id, source, _ = custody
    legacy, connector, operator, reader, _, config = conversation_source
    scope, items = selected(config)
    saved = service.page(operator, grant_id, page(source_id, scope, *items))
    memory = UUID(saved["items"][0]["memory_id"])
    legacy.binding(
        env.owner,
        connector,
        BindingInput(
            external_id="employee:reader", principal_id=reader.principal_id, role="reader"
        ),
        remove=binding == "missing",
    )
    # Deliberately reproduce a stale derived row using the isolated schema owner.
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            "INSERT INTO mnemion.space_grants(tenant_id,space_id,principal_id,role) VALUES(%s,%s,%s,'reviewer') ON CONFLICT(tenant_id,space_id,principal_id) DO UPDATE SET role='reviewer'",
            (operator.tenant_id, UUID(source["space_id"]), reader.principal_id),
        )
    if binding == "missing":
        with pytest.raises(ServiceError):
            env.memory.fetch(reader, memory)
    else:
        assert env.memory.fetch(reader, memory)["can_forget"] is False
    with pytest.raises(ServiceError):
        env.memory.forget(reader, memory, expected_version=1, key="stale-derived-grant")
