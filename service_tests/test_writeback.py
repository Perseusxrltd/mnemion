"""Native memory transactions must not acknowledge undurable journal writes."""

import io
import secrets
import time
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from mnemion.journal.config import Configuration
from mnemion.journal.format import JournalError, parse_file
from mnemion.journal.index import journal_index
from mnemion.journal.git import GitJournal
from mnemion.journal.spool import Spool
from mnemion.service.api import create_app
from mnemion.service.errors import ServiceError
from mnemion.service.models import GrantInput, KeyInput, MemoryInput, PrincipalInput, ReviewInput
from mnemion.service.writeback import WritebackService
from mnemion.service.writeback_models import WritebackPolicyInput
from service_tests.test_memory_journal import configure, entry, git
from service_tests.test_connectors import connected as connected


def setup(env, tmp_path, *, activate=True):
    destination = configure(tmp_path, entry(tenant_id=env.owner.tenant_id, space_id=env.space))
    service = WritebackService(env.db, Configuration(destinations=[destination]))
    env.memory.writeback = service
    if activate:
        service.configure(env.owner, env.space, policy(destination))
    return service, destination


def policy(destination, **changes):
    return WritebackPolicyInput(
        expected_version=0,
        destination_id=destination.id,
        publish_to_repository=True,
        acknowledge_retained_git_history=True,
        **changes,
    )


def identity(env, role):
    person = env.identities.create_principal(
        env.owner, PrincipalInput(name="Journal fixture", kind="application")
    )
    key = env.identities.create_key(env.owner, person["id"], KeyInput(name="Fixture"))
    env.identities.grant(env.owner, env.space, UUID(person["id"]), GrantInput(role=role))
    return env.db.authenticate(key["api_key"])


def events(env):
    with env.db.transaction(env.owner) as conn:
        return conn.execute(
            "SELECT * FROM mnemion.writeback_events WHERE space_id=%s ORDER BY created_at,id",
            (env.space,),
        ).fetchall()


def remote_entries(destination):
    paths = (
        git(destination.local_repository, "ls-tree", "-r", "--name-only", "main")
        .decode()
        .splitlines()
    )
    result = []
    for path in paths:
        if path.endswith(".jsonl"):
            result.extend(
                parse_file(io.BytesIO(git(destination.local_repository, "show", "main:" + path)))
            )
    return result


def test_native_save_is_journaled_before_ack_and_keeps_identity_on_retry(env, tmp_path):
    service, destination = setup(env, tmp_path)
    command = MemoryInput(content="PostgreSQL billing migration decision", subject="Billing")
    first = env.memory.save(env.owner, env.space, command, "same-save")
    second = env.memory.save(env.owner, env.space, command, "same-save")
    assert first == second and first["writeback"]["durability"] == "local_journal"
    records = list(Spool(destination).records())
    assert len(records) == 1 and str(records[0].memory_id) == first["memory_id"]
    assert events(env)[0]["state"] == "local"
    assert service.status(env.owner, env.space)["pending_entries"] == 1
    assert env.memory.fetch(env.owner, UUID(first["memory_id"]))["content"] == command.content


def test_scan_failure_rolls_back_memory_revision_jobs_and_event(env, tmp_path):
    _, destination = setup(env, tmp_path)
    with env.db.transaction(env.owner) as conn:
        before = conn.execute(
            "SELECT count(*) AS count FROM mnemion.memories WHERE space_id=%s", (env.space,)
        ).fetchone()["count"]
    secret = secrets.token_urlsafe(32)
    with pytest.raises(ServiceError) as failure:
        env.memory.save(
            env.owner,
            env.space,
            MemoryInput(content="Private value", metadata={"api_key": secret}),
            "reject-secret",
        )
    assert failure.value.status == 422 and secret not in str(failure.value)
    with env.db.transaction(env.owner) as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS count FROM mnemion.memories WHERE space_id=%s", (env.space,)
            ).fetchone()["count"]
            == before
        )
        assert not conn.execute(
            "SELECT 1 FROM mnemion.operations WHERE space_id=%s", (env.space,)
        ).fetchone()
    assert not events(env) and not list(Spool(destination).records())


def test_failed_post_commit_io_is_retryable_without_duplicate_native_memory(
    env, tmp_path, monkeypatch
):
    _, destination = setup(env, tmp_path)
    record = Spool.record

    def unavailable(*args, **kwargs):
        raise JournalError("fixture_disk_unavailable")

    monkeypatch.setattr(Spool, "record", unavailable)
    command = MemoryInput(content="A committed but not yet acknowledged change")
    with pytest.raises(ServiceError, match="idempotency") as failure:
        env.memory.save(env.owner, env.space, command, "disk-retry")
    assert failure.value.status == 503
    pending = events(env)
    assert len(pending) == 1 and pending[0]["state"] == "pending"
    monkeypatch.setattr(Spool, "record", record)
    result = env.memory.save(env.owner, env.space, command, "disk-retry")
    assert result["operation_id"] == str(pending[0]["id"])
    assert len(events(env)) == 1 and len(list(Spool(destination).records())) == 1


def test_important_memory_is_acknowledged_only_after_real_git_publication(env, tmp_path):
    service, destination = setup(env, tmp_path)
    author = identity(env, "contributor")
    result = env.memory.save(
        author,
        env.space,
        MemoryInput(content="The release is approved.", metadata={"important": True}),
        "important",
    )
    assert result["writeback"]["durability"] == "remote_git"
    assert result["writeback"]["remote_pending"] is False
    assert result["writeback"]["destination_kind"] == "local_repository"
    assert events(env)[0]["state"] == "pushed"
    assert remote_entries(destination)[0].text == "The release is approved."
    assert service.status(author, env.space)["state"] == "ready"
    assert (
        service.status(author, env.space)["destination"]["destination_kind"] == "local_repository"
    )
    assert not list(Spool(destination).records())


def test_append_after_git_upload_remains_pending_until_its_own_publication(
    env, tmp_path, monkeypatch
):
    service, destination = setup(env, tmp_path)
    first = env.memory.save(
        env.owner, env.space, MemoryInput(content="First published event."), "first-push"
    )
    original = GitJournal._commit_push
    appended = []

    def append_between_upload_and_acknowledgment(journal, *args, **kwargs):
        result = original(journal, *args, **kwargs)
        if not appended:
            appended.append(
                env.memory.save(
                    env.owner,
                    env.space,
                    MemoryInput(content="New event after upload."),
                    "after-upload",
                )
            )
        return result

    monkeypatch.setattr(GitJournal, "_commit_push", append_between_upload_and_acknowledgment)
    service.push(env.owner, env.space)
    assert [str(record.id) for record in remote_entries(destination)] == [first["operation_id"]]
    assert [str(record.id) for record in Spool(destination).records()] == [
        appended[0]["operation_id"]
    ]
    states = {str(row["id"]): row["state"] for row in events(env)}
    assert states[first["operation_id"]] == "pushed"
    assert states[appended[0]["operation_id"]] == "local"
    service.push(env.owner, env.space)
    assert {str(record.id) for record in remote_entries(destination)} == {
        first["operation_id"],
        appended[0]["operation_id"],
    }
    assert not list(Spool(destination).records())


def test_forgotten_unpublished_text_never_reaches_git_and_replay_retains_denial(env, tmp_path):
    # The test database is shared across tenants. A worker may have more than
    # eight unrelated jobs ahead of this purge; its completion receipt is the
    # boundary we need, not an assumed number of scheduler iterations.
    for number in range(9):
        env.memory.save(
            env.owner,
            env.space,
            MemoryInput(content=f"Unrelated indexing job {number}"),
            f"unrelated-{number}",
        )
    service, destination = setup(env, tmp_path)
    saved = env.memory.save(
        env.owner, env.space, MemoryInput(content="Withdraw this before sharing."), "temporary"
    )
    forgotten = env.memory.forget(
        env.owner, UUID(saved["memory_id"]), expected_version=1, key="withdraw"
    )
    pending = list(Spool(destination).records())
    assert len(pending) == 1 and pending[0].action == "forget"
    assert service.run_once()
    published = remote_entries(destination)
    assert len(published) == 1 and published[0].text is None
    with journal_index(directory=tmp_path) as index:
        for value in published:
            index.add(value)
        assert not list(index.current()) and index.describe()["forgotten_memories"] == 1
    deadline = time.monotonic() + 30
    while env.memory.operation(env.owner, UUID(forgotten["operation_id"]))["state"] != "ready":
        assert time.monotonic() < deadline, "The deletion operation did not complete"
        assert env.worker.run_once(), "The queued deletion operation was not claimed"
    assert all(row["revision_id"] is None for row in events(env))


def test_quarantine_blocks_publication_until_reviewed_release(env, tmp_path):
    service, destination = setup(env, tmp_path)
    saved = env.memory.save(
        env.owner, env.space, MemoryInput(content="Needs review first."), "review-first"
    )
    memory = UUID(saved["memory_id"])
    env.memory.review(
        env.owner, memory, ReviewInput(expected_version=1, state="quarantined", reason="Review")
    )
    service.push(env.owner, env.space)
    assert [e.action for e in remote_entries(destination)] == ["quarantine"]
    env.memory.review(
        env.owner, memory, ReviewInput(expected_version=2, state="ordinary", reason="Approved")
    )
    service.push(env.owner, env.space)
    with journal_index(directory=tmp_path) as index:
        for value in remote_entries(destination):
            index.add(value)
        assert [e.text for e in index.current()] == ["Needs review first."]


def test_capture_continues_when_publication_paused_and_revocation_is_not_reminted(env, tmp_path):
    service, destination = setup(env, tmp_path)
    current = policy(destination).model_copy(update={"expected_version": 1, "paused": True})
    service.configure(env.owner, env.space, current)
    env.memory.save(
        env.owner, env.space, MemoryInput(content="Retained while publication is paused."), "paused"
    )
    assert not service.run_once() and len(list(Spool(destination).records())) == 1
    with env.db.transaction(env.owner) as conn:
        settings = service._settings(conn, env.space)
    env.identities.revoke_key(env.owner, settings["key_id"])
    service.configure(
        env.owner, env.space, current.model_copy(update={"expected_version": 2, "paused": False})
    )
    assert not service.run_once()
    assert service.status(env.owner, env.space)["state"] == "publisher_unavailable"
    service.configure(
        env.owner,
        env.space,
        current.model_copy(
            update={"expected_version": 3, "paused": False, "repair_publisher": True}
        ),
    )
    assert service.run_once() and len(remote_entries(destination)) == 1


def test_contributor_cannot_enable_egress_or_touch_operator_state(env, tmp_path):
    service, destination = setup(env, tmp_path, activate=False)
    author = identity(env, "contributor")
    with pytest.raises(ServiceError):
        service.configure(author, env.space, policy(destination))
    assert not destination.state_directory.exists()


def test_http_routes_share_native_capture_and_status_without_local_paths(
    env, tmp_path, monkeypatch
):
    _, destination = setup(env, tmp_path, activate=False)
    monkeypatch.setattr(WritebackService, "start", lambda self: None)
    with TestClient(
        create_app(
            env.db,
            env.embedder,
            studio_enabled=False,
            writeback_configuration=Configuration(destinations=[destination]),
        )
    ) as client:
        headers = {"Authorization": "Bearer " + env.token}
        configured = client.put(
            f"/v1/spaces/{env.space}/writeback",
            headers=headers,
            json=policy(destination).model_dump(mode="json"),
        )
        assert configured.status_code == 200, configured.text
        saved = client.post(
            f"/v1/spaces/{env.space}/memories",
            headers={**headers, "Idempotency-Key": "http-journal"},
            json={"content": "Saved through the app's ordinary native route."},
        )
        assert saved.status_code == 202, saved.text
        assert saved.json()["writeback"]["durability"] == "local_journal"
        assert saved.json()["writeback"]["destination_kind"] == "local_repository"
        response = client.get(f"/v1/spaces/{env.space}/writeback", headers=headers)
        assert response.json()["pending_entries"] == 1
        assert response.json()["destination"]["destination_kind"] == "local_repository"
        assert str(destination.state_directory) not in response.text


def test_real_git_replay_through_http_keeps_source_ids_and_rejects_missing_denials(
    env, connected, tmp_path
):
    import hashlib
    from mnemion.connectors.config import ConnectorConfig
    from mnemion.connectors.protocol import Document, Scope
    from mnemion.connectors.runner import sync
    from mnemion.sdk import Client
    from service_tests.test_clients import running

    _, connector, source_space, _, identities = connected
    # Start HTTP before attaching capture to this fixture's separate native
    # writer. The server's inbound connector still cannot write upstream.
    with (
        running(create_app(env.db, env.embedder, studio_enabled=False)) as url,
        Client(url, identities["connector"][1]) as client,
    ):
        service, destination = setup(env, tmp_path)
        config = ConnectorConfig.model_validate(
            {
                "service_url": url,
                "connector_id": str(connector),
                "service_token": {"env": "UNUSED_INJECTED_CLIENT"},
                "provider": {
                    "type": "slack",
                    "team_id": "T123",
                    "channels": ["C123"],
                    "token": {"env": "UNUSED_PROVIDER"},
                },
            }
        )

        class Adapter:
            access_mode = "provider"
            omit_denials = False

            def scopes(self):
                return ["channel:C_PRIVATE"]

            def access(self, identifier):
                return Scope(identifier, "Journal replay", ["U_reader", "U_reviewer"])

            def documents(self, identifier):
                paths = (
                    git(destination.local_repository, "ls-tree", "-r", "--name-only", "main")
                    .decode()
                    .splitlines()
                )
                for path in paths:
                    content = git(destination.local_repository, "show", "main:" + path)
                    if path.endswith(".jsonl") and self.omit_denials:
                        content = b"".join(
                            e.line()
                            for e in parse_file(io.BytesIO(content))
                            if e.action != "forget"
                        )
                    yield Document(
                        path,
                        hashlib.sha256(content).hexdigest(),
                        "Journal file",
                        content.decode(),
                        metadata={"path": path},
                    )

        adapter = Adapter()
        saved = env.memory.save(
            env.owner,
            env.space,
            MemoryInput(content="Replay the approved architecture decision."),
            "replay-native",
        )
        service.push(env.owner, env.space)
        assert sync(config, adapter=adapter, client=client)["completed"]
        with env.db.transaction(identities["reviewer"][0]) as conn:
            row = conn.execute(
                "SELECT id,current_revision_id FROM mnemion.memories WHERE space_id=%s AND deleted_at IS NULL",
                (source_space,),
            ).fetchone()
            assert str(row["id"]) != saved["memory_id"]
        assert sync(config, adapter=adapter, client=client)["completed"]
        with env.db.transaction(identities["reviewer"][0]) as conn:
            assert (
                conn.execute(
                    "SELECT id,current_revision_id FROM mnemion.memories WHERE space_id=%s AND deleted_at IS NULL",
                    (source_space,),
                ).fetchone()
                == row
            )
        env.memory.forget(
            env.owner, UUID(saved["memory_id"]), expected_version=1, key="replay-denial"
        )
        service.push(env.owner, env.space)
        adapter.omit_denials = True
        failed = sync(config, adapter=adapter, client=client)
        assert (
            not failed["completed"]
            and failed["scopes"][0]["error_code"] == "journal_incomplete_inventory"
        )
        adapter.omit_denials = False
        assert sync(config, adapter=adapter, client=client)["completed"]
        with env.db.transaction(identities["reviewer"][0]) as conn:
            assert not conn.execute(
                "SELECT FROM mnemion.memories WHERE space_id=%s AND deleted_at IS NULL",
                (source_space,),
            ).fetchone()
