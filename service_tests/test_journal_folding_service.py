"""Filing is opt-in, observable, versioned, and revocable for the real service."""

import pytest
from fastapi.testclient import TestClient

from mnemion.journal.config import Configuration
from mnemion.journal.git import GitJournal
from mnemion.journal.notes import note_path
from mnemion.service.api import create_app
from mnemion.service.errors import ServiceError
from mnemion.service.models import MemoryInput
from mnemion.service.writeback import WritebackService
from service_tests.test_journal_folding import OLD, content
from service_tests.test_memory_journal import entry, git
from service_tests.test_writeback import identity, policy, setup


def enable(env, service, destination, **changes):
    current = service.status(env.owner, env.space)
    return service.configure(
        env.owner,
        env.space,
        policy(destination).model_copy(
            update={"expected_version": current["version"], "fold_enabled": True, **changes}
        ),
    )


def seed(destination):
    old = entry(ts=OLD, tenant_id=destination.tenant_id, space_id=destination.space_id)
    GitJournal(destination).publish([old])
    return old


def test_filing_requires_opt_in_and_schedules_real_notes_with_observable_status(env, tmp_path):
    service, destination = setup(env, tmp_path)
    first = seed(destination)
    assert not service.status(env.owner, env.space)["fold_enabled"]
    assert not service.run_once()
    with pytest.raises(ServiceError) as failure:
        service.organize(env.owner, env.space, expected_version=1)
    assert failure.value.code == "journal_folding_disabled"
    enabled = enable(env, service, destination)
    assert enabled["fold_enabled"] and enabled["next_fold_at"]
    assert service.run_once()
    status = service.status(env.owner, env.space)
    assert status["last_fold_notes"] == status["last_fold_archived_files"] == 1
    assert status["last_fold_read_bytes"] > 0 and status["last_fold_written_bytes"] > 0
    assert status["last_fold_at"] and status["last_fold_commit"]
    assert first.text.encode() in content(destination, note_path(destination, first.memory_id))
    assert not service.run_once()
    before = env.memory.activity(env.owner, env.space, action="journal.organized")["items"]
    assert len(before) == 1
    repeated = service.organize(env.owner, env.space, expected_version=enabled["version"])
    assert repeated["notes"] == repeated["archived_files"] == 0
    after = service.status(env.owner, env.space)
    assert after["last_fold_at"] >= status["last_fold_at"] and after["next_fold_at"]
    assert after["last_fold_notes"] == after["last_fold_archived_files"] == 0
    assert env.memory.activity(env.owner, env.space, action="journal.organized")["items"] == before
    # A 4.15 client has no filing fields. Updating its publication interval must
    # neither disable filing nor change the administrator's selected schedule.
    retained = service.configure(
        env.owner,
        env.space,
        policy(destination).model_copy(
            update={"expected_version": status["version"], "interval_seconds": 90}
        ),
    )
    assert (
        retained["fold_enabled"]
        and retained["fold_interval_seconds"] == status["fold_interval_seconds"]
    )
    assert retained["destination"] == status["destination"]


def test_pending_local_change_and_stale_policy_cannot_file_an_old_snapshot(env, tmp_path):
    service, destination = setup(env, tmp_path)
    first = seed(destination)
    enabled = enable(env, service, destination)
    with pytest.raises(ServiceError) as failure:
        service.organize(env.owner, env.space, expected_version=1)
    assert failure.value.code == "version_conflict"
    env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="A new change still waiting for Git."),
        "pending-filing",
    )
    with pytest.raises(ServiceError) as failure:
        service.organize(env.owner, env.space, expected_version=enabled["version"])
    assert failure.value.code == "journal_pending_changes"
    assert service.status(env.owner, env.space)["last_fold_error"] == "journal_pending_changes"
    assert not service.status(env.owner, env.space)["last_fold_at"]
    service.push(env.owner, env.space)
    service.organize(env.owner, env.space, expected_version=enabled["version"])
    assert first.text.encode() in content(destination, note_path(destination, first.memory_id))
    assert service.status(env.owner, env.space)["last_fold_error"] is None


def test_filing_permissions_pause_and_publisher_revocation_are_enforced(env, tmp_path):
    service, destination = setup(env, tmp_path)
    seed(destination)
    enabled = enable(env, service, destination)
    contributor = identity(env, "contributor")
    assert not service.status(contributor, env.space)["can_organize"]
    with pytest.raises(ServiceError) as failure:
        service.organize(contributor, env.space, expected_version=enabled["version"])
    assert failure.value.status == 403
    paused = enable(env, service, destination, paused=True)
    assert not service.run_once()
    with pytest.raises(ServiceError) as failure:
        service.organize(env.owner, env.space, expected_version=paused["version"])
    assert failure.value.code == "journal_paused"
    enable(env, service, destination, paused=False)
    with env.db.transaction(env.owner) as conn:
        key = service._settings(conn, env.space)["key_id"]
    env.identities.revoke_key(env.owner, key)
    assert not service.run_once()
    assert service.status(env.owner, env.space)["state"] == "publisher_unavailable"
    with pytest.raises(ServiceError):
        service.organize(env.owner, env.space)


def test_a_policy_change_during_filing_cannot_push_prepared_notes(env, tmp_path, monkeypatch):
    service, destination = setup(env, tmp_path)
    seed(destination)
    enabled = enable(env, service, destination)
    head = git(destination.local_repository, "rev-parse", "main")
    original = GitJournal._commit_push

    def pause_before_push(journal, *args, **kwargs):
        enable(env, service, destination, paused=True)
        return original(journal, *args, **kwargs)

    monkeypatch.setattr(GitJournal, "_commit_push", pause_before_push)
    with pytest.raises(ServiceError) as failure:
        service.organize(env.owner, env.space, expected_version=enabled["version"])
    assert failure.value.code == "journal_policy_changed"
    assert git(destination.local_repository, "rev-parse", "main") == head


def test_http_and_python_sdk_share_the_same_filing_contract(env, tmp_path, monkeypatch):
    from mnemion.sdk import Client

    service, destination = setup(env, tmp_path)
    seed(destination)
    enabled = enable(env, service, destination)
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
        response = api.post(
            f"/v1/spaces/{env.space}/writeback/organize",
            headers=headers,
            json={"expected_version": enabled["version"]},
        )
        assert response.status_code == 200
        assert response.json()["last_fold_notes"] == 1
        client = Client("http://127.0.0.1:8080", api_key=env.token)
        observed = []

        def request(method, path, *, body=None, **kwargs):
            observed.append((method, path, body))
            result = api.request(method, path, headers=headers, json=body)
            assert result.status_code == 200
            return result.json()

        monkeypatch.setattr(client, "request", request)
        status = client.organize_journal(str(env.space), expected_version=enabled["version"])
        assert status.last_fold_notes == 0 and status.last_fold_commit
        client.configure_journal(
            str(env.space),
            policy(destination).model_copy(update={"expected_version": status.version}),
        )
        assert "fold_enabled" not in observed[-1][2]
        assert "fold_after_hours" not in observed[-1][2]
        assert service.status(env.owner, env.space)["fold_enabled"]
        client.close()
