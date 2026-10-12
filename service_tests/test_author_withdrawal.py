"""An author can withdraw their own untouched work without moderation authority."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from mnemion.service.api import create_app
from mnemion.service.errors import ServiceError
from mnemion.service.librarian_models import LibrarianRunInput
from mnemion.service.models import GrantInput, MemoryInput, RevisionInput, ReviewInput
from service_tests.test_librarian import drain, setup
from service_tests.test_transactions import app_identity


def authored(env, identity, key="own", content="An agent's provisional coffee note"):
    saved = env.memory.save(identity, env.space, MemoryInput(content=content), key)
    return UUID(saved["memory_id"])


def test_author_withdrawal_is_idempotent_and_survives_physical_purge(env):
    author, _ = app_identity(env)
    memory = authored(env, author)
    env.memory.revise(
        author,
        memory,
        RevisionInput(content="A corrected coffee note", expected_version=1, reason="Correction"),
        "own-revision",
    )
    removed = env.memory.forget(author, memory, expected_version=2, key="own-withdrawal")
    assert removed["deleted"]
    assert env.memory.forget(author, memory, expected_version=2, key="own-withdrawal") == removed
    with pytest.raises(ServiceError) as error:
        env.memory.fetch(env.owner, memory, review=True)
    assert error.value.status == 404
    while env.worker.run_once():
        pass
    assert env.memory.forget(author, memory, expected_version=2, key="own-withdrawal") == removed
    again = env.memory.forget(author, memory, expected_version=2, key="own-withdrawal-again")
    assert again["operation_id"] == removed["operation_id"] and again["deleted"]
    env.identities.revoke_grant(env.owner, env.space, author.principal_id)
    with pytest.raises(ServiceError) as error:
        env.memory.forget(author, memory, expected_version=2, key="own-withdrawal")
    assert error.value.status == 404


@pytest.mark.parametrize("foreign_first", [False, True])
def test_foreign_authorship_anywhere_in_history_requires_a_reviewer(env, foreign_first):
    author, _ = app_identity(env)
    other, _ = app_identity(env)
    memory = authored(env, other if foreign_first else author)
    env.memory.revise(
        other if not foreign_first else author,
        memory,
        RevisionInput(
            content="Another author's coffee revision", expected_version=1, reason="Edit"
        ),
        "foreign-revision",
    )
    env.memory.revise(
        author,
        memory,
        RevisionInput(content="Author edits again", expected_version=2, reason="Edit"),
        "own-later-revision",
    )
    with pytest.raises(ServiceError) as error:
        env.memory.forget(author, memory, expected_version=3, key="blocked-withdrawal")
    assert error.value.status == 403 and error.value.code == "requires_reviewer"
    assert env.memory.fetch(env.owner, memory)["version"] == 3
    assert env.memory.forget(env.owner, memory, expected_version=3, key="reviewer-withdrawal")[
        "deleted"
    ]


def test_quarantine_reader_access_and_verified_claims_do_not_gain_author_withdrawal(env):
    author, _ = app_identity(env)
    memory = authored(env, author)
    env.memory.review(
        env.owner,
        memory,
        ReviewInput(expected_version=1, state="quarantined", reason="Under review"),
    )
    with pytest.raises(ServiceError) as error:
        env.memory.forget(author, memory, expected_version=2, key="quarantined")
    assert error.value.status == 404
    ordinary = authored(env, author, key="ordinary")
    env.identities.grant(env.owner, env.space, author.principal_id, GrantInput(role="reader"))
    with pytest.raises(ServiceError) as error:
        env.memory.forget(author, ordinary, expected_version=1, key="reader-withdrawal")
    assert error.value.status == 403
    env.identities.grant(env.owner, env.space, author.principal_id, GrantInput(role="reviewer"))
    verified = env.memory.save(
        author,
        env.space,
        MemoryInput(content="Reviewed coffee fact", claim_status="verified"),
        "verified",
    )
    env.identities.grant(env.owner, env.space, author.principal_id, GrantInput(role="contributor"))
    with pytest.raises(ServiceError) as error:
        env.memory.forget(
            author, UUID(verified["memory_id"]), expected_version=1, key="verified-withdrawal"
        )
    assert error.value.status == 403 and error.value.code == "requires_reviewer"


def test_author_withdrawal_erases_reviewer_only_derived_findings_in_the_same_transaction(env):
    author, _ = app_identity(env)
    memory = authored(env, author)
    service, runner = setup(env)
    try:
        service.create_run(env.owner, env.space, LibrarianRunInput(), "author-finding")
        drain(runner)
        finding = service.proposals(env.owner, env.space)["items"][0]
        assert finding["suggestion"] is not None
        # The author cannot read these protected rows. Erasure must not rely on
        # their application connection seeing and cleaning a reviewer's data.
        with env.db.transaction(author) as conn:
            assert not conn.execute("SELECT 1 FROM mnemion.librarian_dependencies").fetchone()
        env.memory.forget(author, memory, expected_version=1, key="erase-derived-data")
        with env.db.transaction(env.owner) as conn:
            row = conn.execute(
                "SELECT state,suggestion FROM mnemion.librarian_proposals WHERE id=%s",
                (finding["id"],),
            ).fetchone()
            assert row == {"state": "invalidated", "suggestion": None}
            assert not conn.execute(
                "SELECT 1 FROM mnemion.librarian_dependencies WHERE proposal_id=%s",
                (finding["id"],),
            ).fetchone()
        # No worker drain occurred between withdrawal and these assertions.
    finally:
        service.registry.close()


def test_a_reviewer_deletion_does_not_become_an_author_deletion_after_purge(env):
    author, _ = app_identity(env)
    memory = authored(env, author)
    env.memory.revise(
        env.owner,
        memory,
        RevisionInput(content="Reviewed and amended", expected_version=1, reason="Review"),
        "reviewer-edited",
    )
    env.memory.forget(env.owner, memory, expected_version=2, key="reviewer-removed")
    while env.worker.run_once():
        pass
    with pytest.raises(ServiceError) as error:
        env.memory.forget(author, memory, expected_version=2, key="author-after-purge")
    assert error.value.code == "requires_reviewer"


@pytest.mark.parametrize(
    "intervention,expected",
    [
        ("revision", "requires_reviewer"),
        ("quarantine", "not_found"),
        ("grant", "not_found"),
        ("key", "unauthorized"),
    ],
)
def test_permissions_are_rechecked_after_waiting_for_the_memory_lock(
    env, monkeypatch, intervention, expected
):
    from mnemion.service import withdrawal

    author, key = app_identity(env)
    memory = authored(env, author)
    waiting = Event()
    original = withdrawal.target

    def observed(*args, **kwargs):
        if kwargs.get("lock"):
            waiting.set()
        return original(*args, **kwargs)

    monkeypatch.setattr(withdrawal, "target", observed)

    def forget():
        try:
            return env.memory.forget(author, memory, expected_version=1, key="waiting-withdrawal")
        except ServiceError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=1) as pool:
        with env.db.transaction(env.owner) as conn:
            conn.execute("SELECT id FROM mnemion.memories WHERE id=%s FOR UPDATE", (memory,))
            result = pool.submit(forget)
            assert waiting.wait(3), "Withdrawal did not reach the locked memory"
            if intervention == "revision":
                env.memory.revise_in_transaction(
                    conn,
                    env.owner,
                    memory,
                    RevisionInput(
                        content="Someone else revised this",
                        expected_version=1,
                        reason="Concurrent edit",
                    ),
                    "concurrent-foreign-revision",
                )
            elif intervention == "quarantine":
                conn.execute(
                    "UPDATE mnemion.memories SET review_state='quarantined', version=version+1 WHERE id=%s",
                    (memory,),
                )
            elif intervention == "grant":
                env.identities.revoke_grant(env.owner, env.space, author.principal_id)
            else:
                env.identities.revoke_key(env.owner, UUID(key["id"]))
        assert result.result(timeout=5) == expected
    with env.db.transaction(env.owner) as conn:
        assert (
            conn.execute(
                "SELECT deleted_at FROM mnemion.memories WHERE id=%s", (memory,)
            ).fetchone()["deleted_at"]
            is None
        )


def test_http_reports_current_capability_and_keeps_other_authors_forbidden(env):
    author, key = app_identity(env)
    own = authored(env, author)
    other = authored(env, env.owner, key="other")
    with TestClient(create_app(env.db, env.embedder)) as client:
        headers = {"Authorization": "Bearer " + key["api_key"]}
        assert client.get(f"/v1/memories/{own}", headers=headers).json()["can_forget"] is True
        assert client.get(f"/v1/memories/{other}", headers=headers).json()["can_forget"] is False
        denied = client.delete(
            f"/v1/memories/{other}?expected_version=1",
            headers={**headers, "Idempotency-Key": "other-http"},
        )
        assert denied.status_code == 403 and denied.json()["error"]["code"] == "requires_reviewer"
        deleted = client.delete(
            f"/v1/memories/{own}?expected_version=1",
            headers={**headers, "Idempotency-Key": "own-http"},
        )
        assert deleted.status_code == 202 and deleted.json()["deleted"]


def test_failed_withdrawal_rolls_back_derived_erasure_and_trigger_is_not_public(env, monkeypatch):
    author, _ = app_identity(env)
    memory = authored(env, author)
    service, runner = setup(env)
    try:
        service.create_run(env.owner, env.space, LibrarianRunInput(), "atomic-finding")
        drain(runner)
        before = service.proposals(env.owner, env.space)["items"][0]

        def fail(*args, **kwargs):
            raise RuntimeError("Injected failure before deletion operation")

        monkeypatch.setattr(env.memory, "_operation", fail)
        with pytest.raises(RuntimeError, match="Injected failure"):
            env.memory.forget(author, memory, expected_version=1, key="atomic-withdrawal")
        assert service.proposals(env.owner, env.space)["items"][0] == before
        assert env.memory.fetch(author, memory)["version"] == 1
        with env.db.transaction(author) as conn:
            assert (
                conn.execute(
                    "SELECT has_function_privilege(current_user,'mnemion.purge_withdrawn_memory_derivatives()','EXECUTE') AS permitted"
                ).fetchone()["permitted"]
                is False
            )
    finally:
        service.registry.close()
