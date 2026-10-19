"""Existing-memory export must preserve current identity, privacy and resumability."""

from uuid import UUID, uuid4

import pytest

from fastapi.testclient import TestClient

from mnemion.journal.config import Configuration
from mnemion.journal.format import JournalError
from mnemion.service.api import create_app
from mnemion.service import journal_backfill as backfill
from mnemion.service.backfill_models import BackfillControlInput, BackfillStartInput
from mnemion.service.errors import ServiceError
from mnemion.service.models import (
    GrantInput,
    KeyInput,
    MemoryInput,
    PrincipalInput,
    RevisionInput,
    ReviewInput,
)
from mnemion.service.writeback import WritebackService
from service_tests.test_writeback import events, identity, policy, remote_entries, setup


def save(env, name, **changes):
    return env.memory.save(env.owner, env.space, MemoryInput(content=name, **changes), str(uuid4()))


def start(env, service, *, version=1, key="start-existing", resume=None):
    return service.start_backfill(
        env.owner,
        env.space,
        BackfillStartInput(
            expected_version=version,
            publish_existing_memories=True,
            acknowledge_retained_git_history=True,
            resume_run=resume,
        ),
        key,
    )


def control(env, service, run, action, *, version=1):
    return service.control_backfill(
        env.owner,
        env.space,
        BackfillControlInput(expected_version=version, run_id=run["id"], action=action),
    )


def test_old_current_revisions_reach_real_git_without_rewriting_memories(env, tmp_path):
    original = save(env, "Résumé — 古い決定 🌌", subject="Earlier decision")
    env.memory.revise(
        env.owner,
        UUID(original["memory_id"]),
        RevisionInput(
            content="Résumé — current decision 🌌", expected_version=1, reason="New decision"
        ),
        "current-version",
    )
    before = env.memory.fetch(env.owner, UUID(original["memory_id"]))
    with env.db.transaction(env.owner) as conn:
        recorded = conn.execute(
            "SELECT recorded_at FROM mnemion.memory_revisions WHERE id=%s", (before["revision_id"],)
        ).fetchone()["recorded_at"]
    service, destination = setup(env, tmp_path)
    assert (
        not events(env) and service.backfill_status(env.owner, env.space)["eligible_memories"] == 1
    )
    first = start(env, service)
    assert first == start(env, service)
    assert first["run"]["state"] == "running" and not events(env)
    with env.db.transaction(env.owner) as conn:
        publisher = service._publisher(service._settings(conn, env.space))
    with env.db.transaction(publisher) as conn:
        assert conn.execute(
            "SELECT mnemion.writeback_backfill_approval_live(%s) AS live", (env.space,)
        ).fetchone()["live"]
        assert not conn.execute(
            "SELECT id FROM mnemion.principals WHERE id=%s", (env.owner.principal_id,)
        ).fetchone()
    assert service.run_once()  # Capture without claiming Git delivery.
    status = service.backfill_status(env.owner, env.space)
    assert status["run"]["state"] == "completed" and status["run"]["queued"] == 1
    assert status["eligible_memories"] == 0
    assert events(env)[0]["state"] == "pending"
    assert service.run_once()  # Existing publisher verifies the actual Git commit.
    published = remote_entries(destination)
    assert len(published) == 1
    assert published[0].text == before["content"] and published[0].ts == recorded
    assert str(published[0].memory_id) == original["memory_id"] and published[0].version == 2
    assert published[0].writer == env.owner.principal_id
    assert env.memory.fetch(env.owner, UUID(original["memory_id"])) == before
    # Repeating a completed scan cannot duplicate a current revision in Git.
    start(env, service, key="review-again")
    service.backfill_batch(env.owner, env.space)
    status = service.backfill_status(env.owner, env.space)
    assert status["run"]["queued"] == 0 and status["run"]["already_journaled"] == 1
    assert len(events(env)) == 1 and len(remote_entries(destination)) == 1


def test_scanner_rejections_do_not_export_secrets_or_block_safe_memories(env, tmp_path):
    safe = save(env, "Safe older design decision")
    sensitive = save(env, "Contact fixture.person@example.invalid")
    deleted = save(env, "Removed before enabling publication")
    env.memory.forget(env.owner, UUID(deleted["memory_id"]), expected_version=1, key="remove-old")
    quarantined = save(env, "Untrusted old note")
    env.memory.review(
        env.owner,
        UUID(quarantined["memory_id"]),
        ReviewInput(expected_version=1, state="quarantined", reason="Test quarantine"),
    )
    service, destination = setup(env, tmp_path)
    start(env, service)
    service.backfill_batch(env.owner, env.space)
    state = service.backfill_status(env.owner, env.space)["run"]
    assert state["examined"] == 4 and state["queued"] == state["rejected"] == 1
    assert state["excluded"] == 2 and state["state"] == "completed"
    assert state["errors"] == [
        {
            "memory_id": sensitive["memory_id"],
            "version": 1,
            "code": "journal_personal_data_detected",
        }
    ]
    assert "fixture.person" not in str(state)
    service.push(env.owner, env.space)
    assert [str(record.memory_id) for record in remote_entries(destination)] == [safe["memory_id"]]
    assert env.memory.fetch(env.owner, UUID(sensitive["memory_id"]))["content"].startswith(
        "Contact"
    )


def test_cursor_survives_restart_and_pause_with_fresh_policy_approval(env, tmp_path, monkeypatch):
    for index in range(4):
        save(env, f"Existing memory {index}")
    service, destination = setup(env, tmp_path)
    original = start(env, service)["run"]
    monkeypatch.setattr(backfill, "BATCH_RECORDS", 2)
    service.backfill_batch(env.owner, env.space)
    partial = service.backfill_status(env.owner, env.space)["run"]
    assert partial["examined"] == partial["queued"] == 2 and partial["state"] == "running"
    control(env, service, original, "pause")
    recovered = WritebackService(env.db, Configuration(destinations=[destination]))
    assert recovered.backfill_batch(env.owner, env.space)["examined"] == 0
    recovered.configure(
        env.owner, env.space, policy(destination).model_copy(update={"expected_version": 1})
    )
    assert (
        recovered.backfill_status(env.owner, env.space)["waiting_reason"]
        == "journal_policy_changed"
    )
    with pytest.raises(ServiceError, match="settings changed"):
        start(env, recovered, resume=original["id"], key="stale-resume")
    start(env, recovered, version=2, resume=original["id"], key="approved-resume")
    recovered.backfill_batch(env.owner, env.space)
    recovered.backfill_batch(env.owner, env.space)
    complete = recovered.backfill_status(env.owner, env.space)["run"]
    assert complete["id"] == original["id"] and complete["queued"] == complete["examined"] == 4
    assert complete["state"] == "completed" and len(events(env)) == 4
    recovered.push(env.owner, env.space)
    assert len(remote_entries(destination)) == 4


@pytest.mark.parametrize("role", ["reader", "contributor", "reviewer", "administrator"])
def test_space_access_alone_cannot_approve_or_inspect_backfill(env, tmp_path, role):
    service, _ = setup(env, tmp_path)
    caller = identity(env, role)
    with pytest.raises(ServiceError) as failure:
        service.backfill_status(caller, env.space)
    assert failure.value.status == 403
    with pytest.raises(ServiceError) as failure:
        service.start_backfill(
            caller,
            env.space,
            BackfillStartInput(
                expected_version=1,
                publish_existing_memories=True,
                acknowledge_retained_git_history=True,
            ),
            "not-admin",
        )
    assert failure.value.status == 403
    assert service.backfill_status(env.owner, env.space)["run"] is None
    with env.db.transaction(caller) as conn:
        assert not conn.execute(
            "SELECT mnemion.writeback_backfill_approval_live(%s) AS live", (env.space,)
        ).fetchone()["live"]


def test_cancelling_stops_capture_but_never_claims_to_retract_queued_publication(
    env, tmp_path, monkeypatch
):
    for index in range(3):
        save(env, f"Cancel example {index}")
    service, destination = setup(env, tmp_path)
    run = start(env, service)["run"]
    monkeypatch.setattr(backfill, "BATCH_RECORDS", 1)
    service.backfill_batch(env.owner, env.space)
    control(env, service, run, "cancel")
    assert service.backfill_batch(env.owner, env.space)["examined"] == 0
    assert service.backfill_status(env.owner, env.space)["run"]["state"] == "cancelled"
    assert service.status(env.owner, env.space)["pending_entries"] == 1
    service.push(env.owner, env.space)
    assert len(remote_entries(destination)) == 1


def test_new_edits_are_not_duplicated_and_later_deletion_suppresses_backfilled_text(env, tmp_path):
    changed = save(env, "Original older wording")
    removed = save(env, "Older text withdrawn after capture")
    service, destination = setup(env, tmp_path)
    start(env, service)
    env.memory.revise(
        env.owner,
        UUID(changed["memory_id"]),
        RevisionInput(
            content="New wording captured by normal native journaling",
            expected_version=1,
            reason="Concurrent edit before backfill reaches this memory",
        ),
        "new-wording",
    )
    later = save(env, "Created after the backfill cutoff")
    service.backfill_batch(env.owner, env.space)
    run = service.backfill_status(env.owner, env.space)["run"]
    assert run["total_at_start"] == run["examined"] == 2
    assert run["already_journaled"] == run["queued"] == 1
    env.memory.forget(
        env.owner, UUID(removed["memory_id"]), expected_version=1, key="after-capture-delete"
    )
    service.push(env.owner, env.space)
    published = remote_entries(destination)
    assert len(published) == 3
    assert {str(row.memory_id) for row in published} == {
        changed["memory_id"],
        removed["memory_id"],
        later["memory_id"],
    }
    assert next(row for row in published if str(row.memory_id) == changed["memory_id"]).version == 2
    assert (
        next(row for row in published if str(row.memory_id) == removed["memory_id"]).action
        == "forget"
    )
    assert "Older text withdrawn" not in str([row.text for row in published])


def test_another_authorized_admin_can_resume_after_the_approver_loses_access(env, tmp_path):
    save(env, "Memory independent of its original administrator")
    service, _ = setup(env, tmp_path)
    person = env.identities.create_principal(
        env.owner, PrincipalInput(name="Second administrator", administrator=True)
    )
    key = env.identities.create_key(env.owner, UUID(person["id"]), KeyInput(name="Second operator"))
    other = env.db.authenticate(key["api_key"])
    # Organization administration never implies content access to this space.
    with pytest.raises(ServiceError) as failure:
        service.backfill_status(other, env.space)
    assert failure.value.status == 404
    env.identities.grant(env.owner, env.space, other.principal_id, GrantInput(role="administrator"))
    original = start(env, service)["run"]
    env.identities.disable_principal(other, env.owner.principal_id)
    assert not service.run_once()
    assert (
        service.backfill_status(other, env.space)["waiting_reason"]
        == "journal_backfill_approval_expired"
    )
    resumed = service.start_backfill(
        other,
        env.space,
        BackfillStartInput(
            expected_version=1,
            publish_existing_memories=True,
            acknowledge_retained_git_history=True,
            resume_run=original["id"],
        ),
        "new-admin-approval",
    )
    assert resumed["run"]["id"] == original["id"] and resumed["waiting_reason"] is None
    assert service.run_once()
    assert service.backfill_status(other, env.space)["run"]["queued"] == 1


def test_failed_scanner_blocks_without_advancing_and_can_resume_after_repair(
    env, tmp_path, monkeypatch
):
    save(env, "A safe memory awaiting the host scanner")
    service, _ = setup(env, tmp_path)
    original = start(env, service)["run"]
    scan = backfill.scan

    def unavailable(*args, **kwargs):
        raise JournalError("journal_program_timeout")

    monkeypatch.setattr(backfill, "scan", unavailable)
    service.backfill_batch(env.owner, env.space)
    blocked = service.backfill_status(env.owner, env.space)["run"]
    assert blocked["state"] == "blocked" and blocked["examined"] == 0
    assert blocked["last_error"] == "journal_scanner_unavailable" and not events(env)
    monkeypatch.setattr(backfill, "scan", scan)
    start(env, service, key="scanner-repaired", resume=original["id"])
    service.backfill_batch(env.owner, env.space)
    assert service.backfill_status(env.owner, env.space)["run"]["queued"] == 1


def test_rejection_details_have_a_fixed_bound_and_do_not_store_text(env, tmp_path):
    for index in range(53):
        save(env, f"Private fixture contact person{index}@example.invalid")
    service, _ = setup(env, tmp_path)
    start(env, service)
    for _ in range(10):
        service.backfill_batch(env.owner, env.space)
        result = service.backfill_status(env.owner, env.space)
        if result["run"]["state"] == "completed":
            break
    assert result["run"]["state"] == "completed"
    assert result["run"]["rejected"] == 53 and len(result["run"]["errors"]) == 50
    assert "example.invalid" not in str(result) and not events(env)


def test_paused_or_revoked_publisher_cannot_capture_more_old_memories(env, tmp_path):
    save(env, "Only an active approved publisher can backfill this")
    service, destination = setup(env, tmp_path)
    original = start(env, service)["run"]
    service.configure(
        env.owner,
        env.space,
        policy(destination).model_copy(update={"expected_version": 1, "paused": True}),
    )
    assert not service.run_once()
    assert service.backfill_batch(env.owner, env.space)["examined"] == 0
    with pytest.raises(ServiceError) as failure:
        start(env, service, version=2, key="paused-resume", resume=original["id"])
    assert failure.value.code == "journal_paused"
    service.configure(
        env.owner, env.space, policy(destination).model_copy(update={"expected_version": 2})
    )
    start(env, service, version=3, key="unpaused-resume", resume=original["id"])
    with env.db.transaction(env.owner) as conn:
        publisher_key = service._settings(conn, env.space)["key_id"]
    env.identities.revoke_key(env.owner, publisher_key)
    assert not service.run_once() and not events(env)
    assert (
        service.backfill_status(env.owner, env.space)["waiting_reason"]
        == "journal_publisher_unavailable"
    )


def test_http_python_sdk_and_agent_contract_expose_the_same_backfill_controls(
    env, tmp_path, monkeypatch
):
    from mnemion.sdk import Client

    save(env, "SDK and agent publication fixture")
    service, destination = setup(env, tmp_path)
    monkeypatch.setattr(WritebackService, "start", lambda self: None)
    with TestClient(
        create_app(
            env.db,
            env.embedder,
            studio_enabled=False,
            writeback_configuration=Configuration(destinations=[destination]),
        )
    ) as api:
        headers = {"Authorization": "Bearer " + env.token}
        client = Client("http://127.0.0.1:8080", api_key=env.token)

        def request(method, path, *, body=None, key=None, **kwargs):
            result = api.request(
                method,
                path,
                headers={**headers, **({"Idempotency-Key": key} if key else {})},
                json=body,
            )
            assert result.status_code == 200, result.text
            return result.json()

        monkeypatch.setattr(client, "request", request)
        assert client.journal_backfill_status(str(env.space)).eligible_memories == 1
        command = BackfillStartInput(
            expected_version=1,
            publish_existing_memories=True,
            acknowledge_retained_git_history=True,
        )
        started = client.start_journal_backfill(
            str(env.space), command, idempotency_key="sdk-backfill"
        )
        assert (
            client.start_journal_backfill(str(env.space), command, idempotency_key="sdk-backfill")
            == started
        )
        paused = client.control_journal_backfill(
            str(env.space),
            BackfillControlInput(expected_version=1, run_id=started.run.id, action="pause"),
        )
        assert paused.run.state == "paused"
        command = command.model_copy(update={"resume_run": UUID(started.run.id)})
        client.start_journal_backfill(str(env.space), command, idempotency_key="sdk-resume")
        service.backfill_batch(env.owner, env.space)
        assert client.journal_backfill_status(str(env.space)).run.queued == 1
        assert api.get(f"/v1/spaces/{env.space}/writeback/backfill").status_code == 401
        bad = api.post(
            f"/v1/spaces/{env.space}/writeback/backfill",
            headers={**headers, "Idempotency-Key": "bad-opt-in"},
            json={
                "expected_version": 1,
                "publish_existing_memories": 1,
                "acknowledge_retained_git_history": True,
            },
        )
        assert bad.status_code == 422
        schema = api.get("/openapi.json").json()
        from mnemion.service.agent_contract import build_contract

        catalog = build_contract(schema)
        assert {item["name"] for item in catalog["operations"]} >= {
            "journal.backfill.status",
            "journal.backfill.start",
            "journal.backfill.control",
        }
        client.close()


def test_two_background_publishers_do_not_capture_duplicate_versions(env, tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    for index in range(12):
        save(env, f"Concurrent backfill memory {index}")
    first, destination = setup(env, tmp_path)
    second = WritebackService(env.db, Configuration(destinations=[destination]))
    start(env, first)
    with env.db.transaction(env.owner) as conn:
        publisher = first._publisher(first._settings(conn, env.space))
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [
            pool.submit(service.backfill_batch, publisher, env.space) for service in (first, second)
        ]
        reports = [job.result(timeout=30) for job in jobs]
    assert sum(report["examined"] for report in reports) == 12
    assert len(events(env)) == 12
    status = first.backfill_status(env.owner, env.space)
    assert status["run"]["state"] == "completed" and status["run"]["queued"] == 12
    first.push(env.owner, env.space)
    assert len(remote_entries(destination)) == 12


def test_oversized_historical_record_is_rejected_without_mutation(env, tmp_path):
    import psycopg

    old = save(env, "Historic import with an oversized record")
    # Simulate legacy imported data with the disposable database operator.
    # The application role deliberately cannot overwrite immutable revisions.
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            "UPDATE mnemion.memory_revisions SET content=repeat('historical ',100000) WHERE id=%s",
            (old["revision_id"],),
        )
    service, _ = setup(env, tmp_path)
    start(env, service)
    service.backfill_batch(env.owner, env.space)
    result = service.backfill_status(env.owner, env.space)
    assert result["run"]["rejected"] == 1 and result["run"]["queued"] == 0
    assert result["run"]["errors"][0]["code"] == "journal_record_too_large"
    assert not events(env)
    with env.db.transaction(env.owner) as conn:
        assert (
            conn.execute(
                "SELECT length(content) AS n FROM mnemion.memory_revisions WHERE id=%s",
                (old["revision_id"],),
            ).fetchone()["n"]
            == 1100000
        )


def test_revocation_during_scanning_cannot_capture_with_stale_publisher_authority(
    env, tmp_path, monkeypatch
):
    save(env, "Private until the active publisher approves capture")
    service, _ = setup(env, tmp_path)
    start(env, service)
    with env.db.transaction(env.owner) as conn:
        settings = service._settings(conn, env.space)
        publisher = service._publisher(settings)
    scan = backfill.scan

    def revoke_during_scan(*args, **kwargs):
        scan(*args, **kwargs)
        env.identities.revoke_key(env.owner, settings["key_id"])

    monkeypatch.setattr(backfill, "scan", revoke_during_scan)
    with pytest.raises(ServiceError) as failure:
        service.backfill_batch(publisher, env.space)
    assert failure.value.status == 401 and not events(env)
    assert service.backfill_status(env.owner, env.space)["run"]["examined"] == 0
