"""Statement-scoped RLS observes revoked grants even on the same pooled connection."""

from uuid import UUID

from mnemion.service.models import GrantInput, KeyInput, MemoryInput, PrincipalInput


def test_permission_sets_refresh_between_statements_and_preserve_write_levels(env):
    person = env.identities.create_principal(env.owner, PrincipalInput(name="Changing access"))
    key = env.identities.create_key(env.owner, UUID(person["id"]), KeyInput(name="Scoped access"))
    caller = env.db.authenticate(key["api_key"])
    saved = env.memory.save(env.owner, env.space, MemoryInput(content="Private decision"), "save")
    env.identities.grant(env.owner, env.space, caller.principal_id, GrantInput(role="contributor"))
    with env.db.transaction(caller) as conn:
        assert conn.execute("SELECT id FROM mnemion.memories").fetchall() == [
            {"id": UUID(saved["memory_id"])}
        ]
        assert conn.execute("SELECT mnemion.authorized_spaces(20) AS id").fetchall() == [
            {"id": env.space}
        ]
        env.identities.revoke_grant(env.owner, env.space, caller.principal_id)
        assert conn.execute("SELECT id FROM mnemion.memories").fetchall() == []
        assert conn.execute("SELECT mnemion.authorized_spaces(10) AS id").fetchall() == []
        env.identities.grant(env.owner, env.space, caller.principal_id, GrantInput(role="reader"))
        assert len(conn.execute("SELECT id FROM mnemion.memories").fetchall()) == 1
        assert conn.execute("SELECT mnemion.authorized_spaces(20) AS id").fetchall() == []
        assert (
            conn.execute(
                "UPDATE mnemion.memories SET version=version+1 WHERE id=%s",
                (UUID(saved["memory_id"]),),
            ).rowcount
            == 0
        )
    assert env.memory.fetch(env.owner, UUID(saved["memory_id"]))["version"] == 1
