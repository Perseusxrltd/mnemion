"""Real PostgreSQL authorization and password/session lifecycle regression tests."""

from concurrent.futures import ThreadPoolExecutor
import time
from uuid import UUID, uuid4

import psycopg
import pytest

from mnemion.service.admin import bootstrap_tenant
from mnemion.service.db import token_hash
from mnemion.service.errors import ServiceError
from mnemion.service.models import GrantInput, MemoryInput, PrincipalInput
from mnemion.service.sign_in import (
    InvitationAcceptInput,
    InvitationInput,
    PasswordInput,
    SignInInput,
    SignInService,
)

PASSWORD = "orange compass marble prairie telescope"
NEW_PASSWORD = "harbour comet mitten glacier tapestry"


@pytest.fixture(autouse=True)
def fresh_throttle(env):
    # This test database is disposable. Each case independently exercises the
    # shared limiter instead of consuming another test's server-wide allowance.
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute("DELETE FROM mnemion.sign_in_attempts")


def enroll(env):
    service = SignInService(env.db)
    service.set_password(env.owner, PasswordInput(username="owner", password=PASSWORD))
    return service


def sign_in(env, service, *, login="owner", password=PASSWORD, transport="native"):
    return service.sign_in(
        SignInInput(
            workspace_id=env.owner.tenant_id,
            username=login,
            password=password,
            device_name="Disposable test device",
            transport=transport,
        )
    )


def assert_unauthorized(env, token):
    with pytest.raises(ServiceError) as rejected:
        env.db.authenticate(token)
    assert rejected.value.status == 401


def finish_committed_memory(env, identity, operation_id):
    # The full suite shares a database across tenant fixtures. A worker may
    # claim another tenant's earlier job before this operation, just as on a
    # real multi-tenant host. Verify this receipt instead of the next queue item.
    deadline = time.monotonic() + 30
    for _ in range(1000):
        with env.db.transaction(identity) as conn:
            state = conn.execute(
                "SELECT state FROM mnemion.operations WHERE id=%s", (operation_id,)
            ).fetchone()["state"]
        if state == "ready":
            return
        assert state in {"accepted", "indexing"}
        if time.monotonic() >= deadline:
            break
        if not env.worker.run_once():
            time.sleep(0.01)
    pytest.fail("The committed memory did not finish indexing within the bounded worker drain")


def test_password_account_separates_session_credentials_and_retains_recovery(env):
    service = enroll(env)
    issued = sign_in(env, service)
    identity = env.db.authenticate(issued["access_token"])
    assert identity.principal_id == env.owner.principal_id
    assert identity.key_id != env.owner.key_id
    assert identity.session_id == UUID(issued["session_id"])
    assert identity.expires_at is not None
    assert len(env.identities.keys(identity)) == 1
    assert env.identities.me(identity)["administrator"]
    with psycopg.connect(env.admin_dsn) as conn:
        verifier = conn.execute(
            "SELECT password_hash FROM mnemion.password_accounts WHERE tenant_id=%s",
            (env.owner.tenant_id,),
        ).fetchone()[0]
        assert verifier.startswith("$argon2id$") and PASSWORD not in verifier
        row = conn.execute(
            "SELECT access_hash,refresh_hash FROM mnemion.sign_in_sessions WHERE id=%s",
            (issued["session_id"],),
        ).fetchone()
        assert row == (token_hash(issued["access_token"]), token_hash(issued["refresh_token"]))
    with env.db.transaction(identity) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT password_hash FROM mnemion.password_accounts")
    with pytest.raises(ServiceError) as last:
        env.identities.revoke_key(identity, env.owner.key_id)
    assert last.value.code == "last_administrator_access"
    service.revoke(identity, identity.session_id)
    assert_unauthorized(env, issued["access_token"])
    assert env.db.authenticate(env.token) == env.owner


def test_refresh_retains_job_authority_and_replay_revokes_the_family(env):
    env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="An earlier queued memory."),
        "older-before-refresh",
    )
    service = enroll(env)
    issued = sign_in(env, service)
    identity = env.db.authenticate(issued["access_token"])
    saved = env.memory.save(
        identity,
        env.space,
        MemoryInput(content="A pending memory from a device session."),
        "signin-job",
    )
    refreshed = service.refresh(issued["refresh_token"], transport="native")
    updated = env.db.authenticate(refreshed["access_token"])
    assert updated.key_id == identity.key_id and updated.session_id == identity.session_id
    assert_unauthorized(env, issued["access_token"])
    finish_committed_memory(env, updated, saved["operation_id"])
    with env.db.transaction(updated) as conn:
        assert (
            conn.execute(
                "SELECT state FROM mnemion.operations WHERE id=%s", (saved["operation_id"],)
            ).fetchone()["state"]
            == "ready"
        )
    with pytest.raises(ServiceError):
        service.refresh(issued["refresh_token"], transport="native")
    assert_unauthorized(env, refreshed["access_token"])
    assert env.db.authenticate(env.token) == env.owner


def test_wrong_refresh_or_browser_csrf_does_not_revoke_a_valid_session(env):
    service = enroll(env)
    issued = sign_in(env, service, transport="browser")
    for refresh, csrf, transport in [
        ("mnm_r_" + "x" * 43, issued["csrf_token"], "browser"),
        (issued["refresh_token"], None, "browser"),
        (issued["refresh_token"], "mnm_c_" + "x" * 43, "browser"),
        (issued["refresh_token"], issued["csrf_token"], "native"),
    ]:
        with pytest.raises(ServiceError):
            service.refresh(refresh, csrf=csrf, transport=transport)
        assert env.db.authenticate(issued["access_token"])
    refreshed = service.refresh(
        issued["refresh_token"], transport="browser", csrf=issued["csrf_token"]
    )
    assert env.db.authenticate(refreshed["access_token"])


def test_concurrent_refresh_accepts_once_then_revokes_reused_family(env):
    service = enroll(env)
    issued = sign_in(env, service)

    def rotate():
        try:
            return service.refresh(issued["refresh_token"], transport="native")
        except ServiceError as exc:
            return exc.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: rotate(), range(2)))
    assert sum(isinstance(value, dict) for value in results) == 1
    assert 401 in results
    success = next(value for value in results if isinstance(value, dict))
    assert_unauthorized(env, success["access_token"])


def test_password_change_requires_old_password_and_revokes_all_device_sessions(env):
    service = enroll(env)
    first, second = sign_in(env, service), sign_in(env, service)
    identity = env.db.authenticate(first["access_token"])
    with pytest.raises(ServiceError):
        service.set_password(identity, PasswordInput(username="owner", password=NEW_PASSWORD))
    service.set_password(
        identity, PasswordInput(username="owner", password=NEW_PASSWORD, current_password=PASSWORD)
    )
    for issued in (first, second):
        assert_unauthorized(env, issued["access_token"])
        with pytest.raises(ServiceError):
            service.refresh(issued["refresh_token"], transport="native")
    with pytest.raises(ServiceError):
        sign_in(env, service)
    assert env.db.authenticate(sign_in(env, service, password=NEW_PASSWORD)["access_token"])


def test_wrong_tenant_unknown_account_and_wrong_password_share_the_error(env):
    service = enroll(env)
    errors = []
    for workspace, login, password in [
        (env.owner.tenant_id, "missing", PASSWORD),
        (env.owner.tenant_id, "owner", NEW_PASSWORD),
        (uuid4(), "owner", PASSWORD),
    ]:
        with pytest.raises(ServiceError) as rejected:
            service.sign_in(
                SignInInput(
                    workspace_id=workspace,
                    username=login,
                    password=password,
                    device_name="Disposable",
                    transport="native",
                )
            )
        errors.append((rejected.value.status, rejected.value.code, rejected.value.message))
    assert len(set(errors)) == 1


def test_other_organization_cannot_list_or_revoke_a_session(env):
    service = enroll(env)
    issued = sign_in(env, service)
    other = bootstrap_tenant(
        env.admin_dsn,
        tenant_name="Different team",
        administrator_name="Owner",
        generation=env.embedder.generation,
    )
    outsider = env.db.authenticate(other["api_key"])
    assert service.sessions(outsider)["items"] == []
    with pytest.raises(ServiceError) as rejected:
        service.revoke(outsider, UUID(issued["session_id"]))
    assert rejected.value.status == 404
    assert env.db.authenticate(issued["access_token"])


def test_throttle_includes_unknown_accounts_and_is_shared_between_instances(env):
    first, second = SignInService(env.db), SignInService(env.db)
    for attempt in range(10):
        with pytest.raises(ServiceError) as rejected:
            sign_in(env, first if attempt % 2 else second, login="not-enrolled")
        assert rejected.value.status == 401
    with pytest.raises(ServiceError) as rejected:
        sign_in(env, second, login="not-enrolled")
    assert rejected.value.status == 429


def test_application_principals_cannot_become_password_accounts(env):
    service = SignInService(env.db)
    principal = env.identities.create_principal(
        env.owner, PrincipalInput(name="Agent", kind="application")
    )
    from mnemion.service.models import KeyInput

    key = env.identities.create_key(env.owner, UUID(principal["id"]), KeyInput(name="Agent key"))
    identity = env.db.authenticate(key["api_key"])
    with pytest.raises(ServiceError):
        service.set_password(identity, PasswordInput(username="agent", password=PASSWORD))
    assert service.account(identity)["account"] is None


def invite_person(env, *, grant=True):
    service = SignInService(env.db)
    person = env.identities.create_principal(
        env.owner, PrincipalInput(name="Invited person", kind="human")
    )
    if grant:
        env.identities.grant(env.owner, env.space, UUID(person["id"]), GrantInput(role="reader"))
    invitation = service.create_invitation(
        env.owner, InvitationInput(principal_id=UUID(person["id"]))
    )
    return service, person, invitation


def acceptance(invitation, *, login="invited-person", password=PASSWORD):
    return InvitationAcceptInput(
        invitation=invitation["invitation_token"],
        username=login,
        password=password,
        device_name="Invited test device",
        transport="native",
    )


def test_invitation_previews_exact_authority_and_does_not_expand_it(env):
    service, person, invitation = invite_person(env)
    preview = service.preview_invitation(invitation["invitation_token"])
    assert preview["principal_id"] == person["id"]
    assert preview["workspace_id"] == str(env.owner.tenant_id)
    assert not preview["administrator"]
    assert preview["spaces"] == [
        {"space_id": str(env.space), "name": "Private memory", "role": "reader"}
    ]
    issued = service.accept_invitation(acceptance(invitation))
    identity = env.db.authenticate(issued["access_token"])
    assert identity.principal_id == UUID(person["id"])
    assert not env.identities.me(identity)["administrator"]
    with pytest.raises(ServiceError) as denied:
        env.memory.save(
            identity,
            env.space,
            MemoryInput(content="Not allowed for a reader"),
            "read-only-account",
        )
    assert denied.value.status == 403
    with pytest.raises(ServiceError):
        service.accept_invitation(acceptance(invitation))
    with pytest.raises(ServiceError):
        service.invitations(identity)
    assert invitation["invitation_token"] not in str(service.invitations(env.owner))


@pytest.mark.parametrize(
    "change", ["revoke_grant", "grant_more", "disable_target", "disable_issuer", "expire", "revoke"]
)
def test_invitation_rechecks_current_permissions_authority_and_expiry(env, change):
    service, person, invitation = invite_person(env)
    if change == "revoke_grant":
        env.identities.revoke_grant(env.owner, env.space, UUID(person["id"]))
    elif change == "grant_more":
        env.identities.grant(
            env.owner, env.space, UUID(person["id"]), GrantInput(role="contributor")
        )
    elif change == "disable_target":
        env.identities.disable_principal(env.owner, UUID(person["id"]))
    elif change == "disable_issuer":
        with psycopg.connect(env.admin_dsn) as conn:
            conn.execute(
                "UPDATE mnemion.principals SET disabled_at=now() WHERE tenant_id=%s AND id=%s",
                (env.owner.tenant_id, env.owner.principal_id),
            )
    elif change == "expire":
        with psycopg.connect(env.admin_dsn) as conn:
            conn.execute(
                "UPDATE mnemion.sign_in_invitations SET created_at=now()-interval '2 days',expires_at=now()-interval '1 day' WHERE id=%s",
                (invitation["id"],),
            )
    else:
        service.revoke_invitation(env.owner, UUID(invitation["id"]))
    with pytest.raises(ServiceError) as rejected:
        service.accept_invitation(acceptance(invitation))
    assert rejected.value.status == 401
    with psycopg.connect(env.admin_dsn) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM mnemion.password_accounts WHERE tenant_id=%s AND principal_id=%s",
                (env.owner.tenant_id, person["id"]),
            ).fetchone()[0]
            == 0
        )


def test_concurrent_invitation_acceptance_creates_only_one_account_and_session(env):
    service, person, invitation = invite_person(env)

    def accept():
        try:
            return service.accept_invitation(acceptance(invitation))
        except ServiceError as exc:
            return exc.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: accept(), range(2)))
    assert sum(isinstance(value, dict) for value in results) == 1
    assert 401 in results
    with psycopg.connect(env.admin_dsn) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM mnemion.sign_in_sessions WHERE tenant_id=%s AND principal_id=%s",
                (env.owner.tenant_id, person["id"]),
            ).fetchone()[0]
            == 1
        )


def test_reset_invitation_stops_old_sessions_and_password_before_acceptance(env):
    service = enroll(env)
    previous = sign_in(env, service)
    invitation = service.create_invitation(
        env.owner, InvitationInput(principal_id=env.owner.principal_id, purpose="reset")
    )
    assert_unauthorized(env, previous["access_token"])
    with pytest.raises(ServiceError):
        sign_in(env, service)
    issued = service.accept_invitation(acceptance(invitation, login="owner", password=NEW_PASSWORD))
    assert env.db.authenticate(issued["access_token"]).principal_id == env.owner.principal_id
    assert env.db.authenticate(env.token) == env.owner
    with pytest.raises(ServiceError):
        service.refresh(previous["refresh_token"], transport="native")


def test_sign_in_cannot_revive_a_password_invalidated_by_recovery(env):
    service = enroll(env)
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            "UPDATE mnemion.password_accounts SET reset_required=true WHERE tenant_id=%s",
            (env.owner.tenant_id,),
        )
    with pytest.raises(ServiceError):
        sign_in(env, service)
    invitation = service.create_invitation(
        env.owner, InvitationInput(principal_id=env.owner.principal_id, purpose="reset")
    )
    issued = service.accept_invitation(acceptance(invitation, login="owner", password=NEW_PASSWORD))
    assert env.db.authenticate(issued["access_token"])


def test_logout_preserves_committed_memories_and_service_owned_indexing(env):
    env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="An earlier queued memory."),
        "older-before-logout",
    )
    service = enroll(env)
    issued = sign_in(env, service)
    identity = env.db.authenticate(issued["access_token"])
    saved = env.memory.save(
        identity, env.space, MemoryInput(content="Revoked before indexing"), "revoked-session-job"
    )
    service.revoke(env.owner, identity.session_id)
    finish_committed_memory(env, env.owner, saved["operation_id"])
    with env.db.transaction(env.owner) as conn:
        assert (
            conn.execute(
                "SELECT state FROM mnemion.operations WHERE id=%s", (saved["operation_id"],)
            ).fetchone()["state"]
            == "ready"
        )
    assert_unauthorized(env, issued["access_token"])
    assert (
        env.memory.fetch(env.owner, UUID(saved["memory_id"]))["content"]
        == "Revoked before indexing"
    )


def test_refresh_preserves_delegated_evaluation_but_logout_stops_further_work(env):
    from mnemion.service.evaluation_models import DatasetInput, EvaluationInput
    from mnemion.service.evaluation_runner import EvaluationRunner
    from mnemion.service.evaluations import EvaluationService
    from mnemion.service.retrieval import RetrievalService

    service = enroll(env)
    issued = sign_in(env, service)
    identity = env.db.authenticate(issued["access_token"])
    evaluations = EvaluationService(env.db, env.embedder)
    dataset = evaluations.create_dataset(
        identity,
        env.space,
        DatasetInput.model_validate(
            {
                "name": "Session authority fixture",
                "cases": [
                    {"id": "first", "query": "nothing here", "unanswerable": True},
                    {"id": "second", "query": "still nothing", "unanswerable": True},
                ],
            }
        ),
    )
    run = evaluations.create_run(
        identity,
        env.space,
        EvaluationInput(
            dataset_id=UUID(dataset["id"]), modes=["lexical"], cutoffs=[1], context=False
        ),
        "session-evaluation",
    )
    runner = EvaluationRunner(env.db, RetrievalService(env.db, env.embedder))
    service.refresh(issued["refresh_token"], transport="native")
    assert runner.run_once()
    before = evaluations.run(env.owner, env.space, UUID(run["id"]))
    assert before["state"] == "running" and before["progress"] == 1
    service.revoke(env.owner, identity.session_id)
    assert runner.run_once()
    after = evaluations.run(env.owner, env.space, UUID(run["id"]))
    assert after["state"] == "failed" and after["error_code"] == "access_revoked"
    assert after["progress"] == before["progress"]


def test_workers_cannot_use_password_account_or_session_authority_functions(env):
    with env.worker_db.pool.connection() as conn:
        for statement, args in [
            ("SELECT * FROM mnemion.password_login_lookup(%s,%s)", (env.owner.tenant_id, "owner")),
            ("SELECT * FROM mnemion.authenticate_session(%s)", ("a" * 64,)),
            ("SELECT mnemion.admit_sign_in(%s)", ("a" * 64,)),
        ]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction():
                    conn.execute(statement, args)
