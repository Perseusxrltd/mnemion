"""Legacy source recovery preserves review, current permissions and permanent denial."""

import json
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from mnemion.service.api import create_app
from mnemion.service.buffer_import import BufferImportService
from mnemion.service.buffer_import_models import BufferImportInput, BufferPreviewInput
from mnemion.service.errors import ServiceError
from mnemion.service.models import RevisionInput
from mnemion.sdk import Client
from mnemion import agent_control
from service_tests.test_clients import running
from service_tests.test_writeback import identity, setup, events


def record(**changes):
    return {
        "id": str(uuid4()),
        "ts": "2026-10-01T09:10:11+00:00",
        "desk": "previous-agent",
        "kind": "memory",
        "subject": "Continuity",
        "important": False,
        "text": "PostgreSQL buffer continuity — mémoire 🌌",
        "journal": "memory/buffer/2026-10-01/previous-agent.jsonl",
        **changes,
    }


def command(*rows, withdrawn=(), **changes):
    return BufferPreviewInput(
        namespace="office-buffer",
        jsonl="".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        withdrawn_ids=list(withdrawn),
        **changes,
    )


def approve(service, env, input, key="apply-buffer", preview=None):
    preview = preview or service.preview(env.owner, env.space, input)
    approved = BufferImportInput(
        **input.model_dump(),
        preview_sha256=preview["preview_sha256"],
        reviewed_withdrawals=True,
        acknowledge_source_only=True,
    )
    return service.apply(env.owner, env.space, approved, key)


def test_import_is_writable_repeatable_and_retains_original_provenance(env):
    service = BufferImportService(env.memory)
    first, second = (
        record(),
        record(desk="other-agent", kind="action", text="Prepare independent recovery"),
    )
    input = command(first, second, first)
    preview = service.preview(env.owner, env.space, input)
    assert preview["counts"] == {"create": 2} and preview["duplicates"] == 1
    assert preview["writers"] == ["other-agent", "previous-agent"]
    with env.db.transaction(env.owner) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.memories WHERE space_id=%s", (env.space,)
            ).fetchone()["n"]
            == 0
        )
    result = approve(service, env, input, preview=preview)
    assert result == approve(service, env, input, preview=preview)
    assert result["source_only"] and result["remote_delivery_verified"] is False
    item = next(item for item in result["items"] if item["legacy_id"] == first["id"])
    memory = UUID(item["memory_id"])
    fetched = env.memory.fetch(env.owner, memory)
    assert fetched["content"] == first["text"] and fetched["kind"] == "note"
    assert fetched["created_by"] == str(env.owner.principal_id)
    assert fetched["metadata"]["buffer_import"]["desk"] == first["desk"]
    assert fetched["metadata"]["buffer_import"]["id"] == first["id"]
    env.memory.revise(
        env.owner,
        memory,
        RevisionInput(
            content="A newer current decision", expected_version=1, reason="New information"
        ),
        "new-decision",
    )
    repeated = approve(service, env, input, key="same-source-later")
    assert repeated["counts"] == {"preserved_changes": 1, "already_imported": 1}
    assert env.memory.fetch(env.owner, memory)["content"] == "A newer current decision"
    with env.db.transaction(env.owner) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.space_grants WHERE space_id=%s", (env.space,)
            ).fetchone()["n"]
            == 1
        )


def test_later_withdrawals_and_purge_never_resurrect_an_old_record(env):
    service = BufferImportService(env.memory)
    old, never_imported = record(), record()
    result = approve(service, env, command(old))
    memory = UUID(result["items"][0]["memory_id"])
    withdrawals = command(withdrawn=[old["id"], never_imported["id"]])
    preview = service.preview(env.owner, env.space, withdrawals)
    assert preview["counts"] == {"withdraw": 1, "deny": 1}
    assert env.memory.fetch(env.owner, memory)["content"] == old["text"]
    approve(service, env, withdrawals, key="reviewed-withdrawals", preview=preview)
    while env.worker.run_once():
        pass
    with pytest.raises(ServiceError) as missing:
        env.memory.fetch(env.owner, memory)
    assert missing.value.status == 404
    repeated = approve(service, env, command(old, never_imported), key="old-backup")
    assert repeated["counts"] == {"withdrawn": 2}
    with env.db.transaction(env.owner) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.recovery_denials WHERE space_id=%s", (env.space,)
            ).fetchone()["n"]
            == 2
        )
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.memories WHERE space_id=%s AND deleted_at IS NULL",
                (env.space,),
            ).fetchone()["n"]
            == 0
        )


def test_manual_deletion_is_not_undone_by_a_repeat_import(env):
    service = BufferImportService(env.memory)
    input = command(record())
    result = approve(service, env, input)
    memory = UUID(result["items"][0]["memory_id"])
    env.memory.forget(env.owner, memory, expected_version=1, key="human-deletion")
    assert service.preview(env.owner, env.space, input)["counts"] == {"withdrawn": 1}


def test_changed_original_id_conflicts_and_rolls_back_the_whole_batch(env):
    service = BufferImportService(env.memory)
    old = record()
    approve(service, env, command(old))
    input = command({**old, "text": "Different source bytes"}, record())
    preview = service.preview(env.owner, env.space, input)
    assert not preview["can_import"] and preview["counts"] == {"conflict": 1, "create": 1}
    with pytest.raises(ServiceError, match="Resolve rejected"):
        approve(service, env, input, key="changed-source", preview=preview)
    with env.db.transaction(env.owner) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.memories WHERE space_id=%s", (env.space,)
            ).fetchone()["n"]
            == 1
        )


def test_changed_destination_requires_a_fresh_review(env):
    service = BufferImportService(env.memory)
    input = command(record())
    preview = service.preview(env.owner, env.space, input)
    approve(service, env, input, key="other-admin-action", preview=preview)
    with pytest.raises(ServiceError, match="destination changed"):
        approve(service, env, input, key="stale-preview", preview=preview)


@pytest.mark.parametrize("role", ["reader", "contributor", "reviewer", "administrator"])
def test_space_roles_do_not_grant_organization_import_authority(env, role):
    caller = identity(env, role)
    with pytest.raises(ServiceError) as denied:
        BufferImportService(env.memory).preview(caller, env.space, command(record()))
    assert denied.value.status == 403


def test_an_existing_git_policy_cannot_publish_imported_plaintext(env, tmp_path):
    setup(env, tmp_path)
    with pytest.raises(ServiceError, match="private native space"):
        BufferImportService(env.memory).preview(
            env.owner, env.space, command(record(important=True))
        )
    assert events(env) == []


def test_shared_space_requires_separate_private_reconciliation(env):
    identity(env, "reader")
    with pytest.raises(ServiceError, match="private native space"):
        BufferImportService(env.memory).preview(env.owner, env.space, command(record()))


@pytest.mark.parametrize(
    "problem",
    ["partial", "duplicate-key", "conflicting-id", "unknown-field", "naive-time", "limit"],
)
def test_invalid_or_incomplete_input_never_writes_any_memory(env, problem):
    row = record()
    text = json.dumps(row) + "\n"
    if problem == "partial":
        text = text.rstrip("\n")
    elif problem == "duplicate-key":
        text = text.replace('{"id":', '{"id":"ignored","id":')
    elif problem == "conflicting-id":
        text += json.dumps({**row, "text": "Conflict"}) + "\n"
    elif problem == "unknown-field":
        text = json.dumps({**row, "unknown": True}) + "\n"
    elif problem == "naive-time":
        text = json.dumps({**row, "ts": "2026-10-01T09:10:11"}) + "\n"
    else:
        text = "".join(json.dumps(record()) + "\n" for _ in range(101))
    with pytest.raises(ServiceError) as invalid:
        BufferImportService(env.memory).preview(
            env.owner,
            env.space,
            BufferPreviewInput(namespace="office-buffer", jsonl=text, withdrawn_ids=[]),
        )
    assert invalid.value.status == 422
    with env.db.transaction(env.owner) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.memories WHERE space_id=%s", (env.space,)
            ).fetchone()["n"]
            == 0
        )


def test_secret_checks_remain_required_and_personal_data_is_an_explicit_choice(env):
    service = BufferImportService(env.memory)
    private = record(text="Contact fixture.person@example.invalid")
    plan = service.preview(env.owner, env.space, command(private))
    assert plan["counts"] == {"rejected": 1} and "fixture.person" not in str(plan)
    assert service.preview(env.owner, env.space, command(private, reject_personal_data=False))[
        "can_import"
    ]
    secret = record(text="Bearer " + "synthetic-never-valid" * 3)
    rejected = service.preview(env.owner, env.space, command(secret, reject_personal_data=False))
    assert not rejected["can_import"] and rejected["items"][0]["code"] == "journal_secret_detected"


def test_rejected_writer_labels_are_not_echoed_in_the_review(env):
    private_label = "mnm_" + "not-a-real-key" * 4
    preview = BufferImportService(env.memory).preview(
        env.owner, env.space, command(record(desk=private_label))
    )
    assert not preview["can_import"] and preview["writers"] == []
    assert private_label not in str(preview)


def test_windows_newlines_bom_and_unicode_line_separators_preserve_text(env):
    text = "First paragraph\u2028Second paragraph"
    input = command(record(text=text))
    input = BufferPreviewInput(
        namespace=input.namespace,
        jsonl="\ufeff" + input.jsonl.get_secret_value().replace("\n", "\r\n"),
        withdrawn_ids=[],
    )
    result = approve(BufferImportService(env.memory), env, input)
    assert env.memory.fetch(env.owner, UUID(result["items"][0]["memory_id"]))["content"] == text


def test_http_review_import_and_immediate_lexical_recall(env):
    input = command(record())
    body = {**input.model_dump(mode="json"), "jsonl": input.jsonl.get_secret_value()}
    with TestClient(create_app(env.db, env.embedder)) as client:
        client.headers["Authorization"] = "Bearer " + env.token
        path = f"/v1/spaces/{env.space}/buffer-import"
        preview = client.post(path + "/preview", json=body)
        assert preview.status_code == 200, preview.text
        approved = {
            **body,
            "preview_sha256": preview.json()["preview_sha256"],
            "reviewed_withdrawals": True,
            "acknowledge_source_only": True,
        }
        imported = client.post(path, json=approved, headers={"Idempotency-Key": "http-reviewed"})
        assert imported.status_code == 200, imported.text
        assert (
            imported.json()
            == client.post(path, json=approved, headers={"Idempotency-Key": "http-reviewed"}).json()
        )
        recalled = client.post(
            "/v1/recall",
            json={
                "query": "PostgreSQL buffer continuity",
                "space_ids": [str(env.space)],
                "mode": "lexical",
            },
        )
        assert recalled.status_code == 200, recalled.text
        assert len(recalled.json()["hits"]) == 1


def test_python_sdk_transmits_private_input_and_agent_catalog_keeps_it_private(env):
    input = command(record())
    assert "PostgreSQL" not in repr(input)
    for operation in ("memory.buffer.preview", "memory.buffer.import"):
        assert agent_control.describe(operation)["sensitive_input"] is True
    with (
        running(create_app(env.db, env.embedder, mcp_enabled=False)) as url,
        Client(url, env.token) as client,
    ):
        preview = client.preview_legacy_buffer(str(env.space), input)
        assert preview.can_import and preview.counts == {"create": 1}
        approved = BufferImportInput(
            **input.model_dump(),
            preview_sha256=preview.preview_sha256,
            reviewed_withdrawals=True,
            acknowledge_source_only=True,
        )
        receipt = client.import_legacy_buffer(
            str(env.space), approved, idempotency_key="sdk-buffer"
        )
        assert receipt == client.import_legacy_buffer(
            str(env.space), approved, idempotency_key="sdk-buffer"
        )
        assert env.memory.fetch(env.owner, receipt.items[0].memory_id)["content"].startswith(
            "PostgreSQL"
        )
