"""Administration races must leave a current credential able to recover access."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event
import time
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from mnemion.service.api import create_app
from mnemion.service.admin import bootstrap_tenant
from mnemion.service.db import Identity
from mnemion.service.errors import ServiceError
from mnemion.service.models import KeyInput, PrincipalInput
from mnemion.service.oauth import OAuthSettings
from mnemion.service.oauth_api import OAuthBindingInput, OAuthBindings


def new_admin(env, name="Independent administrator"):
    person = env.identities.create_principal(
        env.owner, PrincipalInput(name=name, kind="human", administrator=True)
    )
    key = env.identities.create_key(env.owner, UUID(person["id"]), KeyInput(name="Independent key"))
    return env.db.authenticate(key["api_key"]), key


def test_api_refuses_revoking_the_only_admin_key_and_retains_access(env):
    with TestClient(create_app(env.db, env.embedder, mcp_enabled=False)) as api:
        headers = {"Authorization": "Bearer " + env.token}
        response = api.delete(f"/v1/keys/{env.owner.key_id}", headers=headers)
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "last_administrator_access"
        assert api.get("/v1/me", headers=headers).status_code == 200


@pytest.mark.parametrize("unusable", ["no_key", "revoked", "expired", "disabled"])
def test_an_administrator_row_alone_does_not_protect_recovery(env, unusable):
    if unusable == "no_key":
        env.identities.create_principal(
            env.owner, PrincipalInput(name="Not enrolled", administrator=True)
        )
    else:
        other, key = new_admin(env)
        if unusable == "revoked":
            env.identities.revoke_key(env.owner, other.key_id)
        elif unusable == "disabled":
            env.identities.disable_principal(env.owner, other.principal_id)
        else:
            with psycopg.connect(env.admin_dsn) as conn:
                conn.execute(
                    "UPDATE mnemion.api_keys SET expires_at=%s WHERE id=%s",
                    (datetime.now(timezone.utc) - timedelta(seconds=1), other.key_id),
                )
    with pytest.raises(ServiceError) as denied:
        env.identities.revoke_key(env.owner, env.owner.key_id)
    assert denied.value.code == "last_administrator_access"
    assert env.db.authenticate(env.token).key_id == env.owner.key_id


def test_verified_replacement_allows_key_rotation_and_the_final_key_stays_usable(env):
    replacement = env.identities.create_key(
        env.owner, env.owner.principal_id, KeyInput(name="Replacement key")
    )
    current = env.db.authenticate(replacement["api_key"])
    env.identities.revoke_key(current, env.owner.key_id)
    with pytest.raises(ServiceError):
        env.db.authenticate(env.token)
    # Repeating an already completed revocation remains idempotent.
    env.identities.revoke_key(current, env.owner.key_id)
    with pytest.raises(ServiceError) as denied:
        env.identities.revoke_key(current, current.key_id)
    assert denied.value.code == "last_administrator_access"
    assert env.db.authenticate(replacement["api_key"]).key_id == current.key_id


@pytest.mark.parametrize("operation", ["own_keys", "each_others_keys", "each_others_principals"])
def test_concurrent_administration_cannot_lock_out_the_organization(env, monkeypatch, operation):
    other, key = new_admin(env)
    original = env.db.transaction
    both_authenticated = Barrier(2)

    @contextmanager
    def simultaneous(identity, **kwargs):
        with original(identity, **kwargs) as conn:
            # Both requests have authenticated before either changes access.
            both_authenticated.wait(timeout=5)
            yield conn

    def change(identity, target):
        try:
            if operation == "each_others_principals":
                env.identities.disable_principal(identity, target.principal_id)
            else:
                env.identities.revoke_key(identity, target.key_id)
            return "changed"
        except ServiceError as error:
            return error.code

    targets = (env.owner, other) if operation == "own_keys" else (other, env.owner)
    with monkeypatch.context() as patch:
        patch.setattr(env.db, "transaction", simultaneous)
        with ThreadPoolExecutor(max_workers=2) as executor:
            a = executor.submit(change, env.owner, targets[0])
            b = executor.submit(change, other, targets[1])
            outcomes = [a.result(timeout=10), b.result(timeout=10)]
    assert outcomes.count("changed") == 1
    assert any(value in {"last_administrator_access", "unauthorized"} for value in outcomes)
    surviving = 0
    for token in (env.token, key["api_key"]):
        try:
            identity = env.db.authenticate(token)
            assert env.identities.me(identity)["administrator"]
            surviving += 1
        except ServiceError:
            pass
    assert surviving == 1


def test_waiting_administrator_rechecks_real_time_key_expiry(env, monkeypatch):
    other, key = new_admin(env)
    original = env.db.transaction
    authenticated, resume = Event(), Event()

    @contextmanager
    def waiting(identity, **kwargs):
        with original(identity, **kwargs) as conn:
            authenticated.set()
            assert resume.wait(timeout=5)
            yield conn

    with monkeypatch.context() as patch:
        patch.setattr(env.db, "transaction", waiting)
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(
                env.identities.disable_principal, other, env.owner.principal_id
            )
            try:
                assert authenticated.wait(timeout=5)
                # The key expires after transaction-start time, before admission.
                with psycopg.connect(env.admin_dsn) as conn:
                    conn.execute(
                        "UPDATE mnemion.api_keys SET expires_at=clock_timestamp() WHERE id=%s",
                        (other.key_id,),
                    )
            finally:
                resume.set()
            with pytest.raises(ServiceError) as denied:
                pending.result(timeout=10)
    assert denied.value.status == 401
    assert env.identities.me(env.owner)["administrator"]


def oauth_administrator(env):
    settings = OAuthSettings(
        issuer="https://identity.example.test",
        introspection_url="https://identity.example.test/introspection",
        resource="https://memory.example.test/mcp",
        client_id="fixture-server",
        client_secret="fixture-secret",
        tenant_id=env.owner.tenant_id,
    )
    service = OAuthBindings(env.db, settings)
    binding = service.create(
        env.owner,
        OAuthBindingInput(
            principal_id=env.owner.principal_id,
            name="Owner sign-in",
            subject=str(env.owner.principal_id),
            client_id="fixture-client",
        ),
    )
    identity = Identity(
        env.owner.tenant_id, env.owner.principal_id, UUID(binding["key_id"]), time.time() + 300
    )
    return service, identity, UUID(binding["id"])


def test_oauth_self_revocation_cannot_remove_the_last_admin_credential(env):
    service, identity, binding = oauth_administrator(env)
    env.identities.revoke_key(identity, env.owner.key_id)
    with pytest.raises(ServiceError) as denied:
        service.revoke(identity, binding)
    assert denied.value.code == "last_administrator_access"
    assert env.identities.me(identity)["administrator"]
    assert service.list(identity)[0]["revoked_at"] is None
    # Creating a replacement restores the ordinary self-revocation path.
    key = env.identities.create_key(
        identity, identity.principal_id, KeyInput(name="Independent recovery key")
    )
    replacement = env.db.authenticate(key["api_key"])
    service.revoke(identity, binding)
    assert env.identities.me(replacement)["administrator"]


def test_oauth_and_api_key_revocations_share_the_same_concurrency_boundary(env, monkeypatch):
    service, identity, binding = oauth_administrator(env)
    original = env.db.transaction
    both_authenticated = Barrier(2)

    @contextmanager
    def simultaneous(caller, **kwargs):
        with original(caller, **kwargs) as conn:
            both_authenticated.wait(timeout=5)
            yield conn

    def change(oauth):
        try:
            if oauth:
                service.revoke(identity, binding)
            else:
                env.identities.revoke_key(env.owner, env.owner.key_id)
            return "changed"
        except ServiceError as error:
            return error.code

    with monkeypatch.context() as patch:
        patch.setattr(env.db, "transaction", simultaneous)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(change, value) for value in (True, False)]
            outcomes = [future.result(timeout=10) for future in futures]
    assert sorted(outcomes) == ["changed", "last_administrator_access"]
    assert (
        sum(
            row["revoked_at"] is None
            for row in env.identities.keys(identity if outcomes[0] != "changed" else env.owner)
        )
        == 1
    )


def test_another_tenants_administrator_never_counts_as_a_recovery_path(env):
    other = bootstrap_tenant(
        env.admin_dsn,
        tenant_name="Separate organization",
        administrator_name="Separate administrator",
        generation=env.embedder.generation,
    )
    with pytest.raises(ServiceError) as denied:
        env.identities.revoke_key(env.owner, env.owner.key_id)
    assert denied.value.code == "last_administrator_access"
    assert env.db.authenticate(other["api_key"])
