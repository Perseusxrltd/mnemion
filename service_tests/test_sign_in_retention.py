"""Expired authentication history is bounded without removing active authority."""

import psycopg
import pytest

from mnemion.service.models import PrincipalInput
from mnemion.service.sign_in import InvitationInput, PasswordInput, SignInInput, SignInService
from mnemion.service.sign_in_maintenance import prune_history

PASSWORD = "orange compass marble prairie telescope"


@pytest.fixture
def access(env):
    # Other tenant fixtures share this disposable database. Clear their eligible
    # history with the production routine before checking this batch's counts.
    for _ in range(32):
        if not any(prune_history(env.db).values()):
            break
    else:
        pytest.fail("Existing expired fixture history did not drain within the bounded setup")
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute("DELETE FROM mnemion.sign_in_attempts")
    service = SignInService(env.db)
    service.set_password(env.owner, PasswordInput(username="owner", password=PASSWORD))
    return service


def login(env, service):
    return service.sign_in(
        SignInInput(
            workspace_id=env.owner.tenant_id,
            username="owner",
            password=PASSWORD,
            device_name="Disposable retention fixture",
            transport="native",
        )
    )


def invitation(env, service):
    person = env.identities.create_principal(
        env.owner, PrincipalInput(name="Invited fixture", kind="human")
    )
    return service.create_invitation(env.owner, InvitationInput(principal_id=person["id"]))


def expire(conn, session, days):
    conn.execute(
        """UPDATE mnemion.sign_in_sessions SET created_at=now()-(%s+30)*interval '1 day',
        expires_at=now()-%s*interval '1 day',access_expires_at=now()-%s*interval '1 day'
        WHERE id=%s""",
        (days, days, days, session["session_id"]),
    )


def test_retention_removes_expired_private_metadata_and_preserves_current_access(env, access):
    expired = login(env, access)
    old_identity = env.db.authenticate(expired["access_token"])
    access.refresh(expired["refresh_token"], transport="native")
    recent = login(env, access)
    active = login(env, access)
    old_invitation = invitation(env, access)
    live_invitation = invitation(env, access)
    with psycopg.connect(env.admin_dsn) as conn:
        expire(conn, expired, 32)
        expire(conn, recent, 1)
        conn.execute(
            """UPDATE mnemion.sign_in_invitations SET created_at=now()-interval '33 days',
            expires_at=now()-interval '32 days' WHERE id=%s""",
            (old_invitation["id"],),
        )
    assert prune_history(env.db) == {"spent_tokens": 1, "sessions": 1, "invitations": 1}
    assert env.db.authenticate(active["access_token"]).principal_id == env.owner.principal_id
    assert env.db.authenticate(env.token) == env.owner
    assert access.preview_invitation(live_invitation["invitation_token"])["principal_id"]
    with psycopg.connect(env.admin_dsn) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM mnemion.sign_in_sessions WHERE id=%s", (recent["session_id"],)
            ).fetchone()[0]
            == 1
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM mnemion.api_keys WHERE id=%s", (old_identity.key_id,)
            ).fetchone()[0]
            == 1
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM mnemion.audit_events WHERE resource_id=%s",
                (expired["session_id"],),
            ).fetchone()[0]
            >= 1
        )
    assert (
        access.refresh(active["refresh_token"], transport="native")["session_id"]
        == active["session_id"]
    )


def test_retention_batches_spent_tokens_before_deleting_session_rows(env, access):
    expired = login(env, access)
    live_invitation = invitation(env, access)
    with psycopg.connect(env.admin_dsn) as conn:
        expire(conn, expired, 32)
        conn.execute(
            """INSERT INTO mnemion.spent_refresh_tokens(token_hash,session_id)
            SELECT md5(gen_random_uuid()::text)||md5(gen_random_uuid()::text),%s
            FROM generate_series(1,2050)""",
            (expired["session_id"],),
        )
        conn.execute(
            """INSERT INTO mnemion.sign_in_invitations
            (id,tenant_id,principal_id,issued_by,secret_hash,purpose,permissions,created_at,expires_at)
            SELECT gen_random_uuid(),i.tenant_id,i.principal_id,i.issued_by,
                md5(gen_random_uuid()::text)||md5(gen_random_uuid()::text),i.purpose,i.permissions,
                now()-interval '33 days',now()-interval '32 days'
            FROM mnemion.sign_in_invitations i CROSS JOIN generate_series(1,130) WHERE i.id=%s""",
            (live_invitation["id"],),
        )
    assert prune_history(env.db) == {"spent_tokens": 2048, "sessions": 0, "invitations": 128}
    assert prune_history(env.db) == {"spent_tokens": 2, "sessions": 1, "invitations": 2}
    assert access.preview_invitation(live_invitation["invitation_token"])["principal_id"]
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(591020146006)")
        assert prune_history(env.db) == {"spent_tokens": 0, "sessions": 0, "invitations": 0}
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with psycopg.connect(env.admin_dsn) as conn:
            conn.execute("SET LOCAL ROLE mnemion_worker")
            conn.execute("SELECT * FROM mnemion.prune_sign_in_history()")
