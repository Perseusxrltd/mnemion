from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from mnemion.service.api import create_app
from mnemion.service.models import (
    GrantInput,
    KeyInput,
    MemoryInput,
    PrincipalInput,
    RevisionInput,
    ReviewInput,
)


def test_change_notes_follow_space_role_revocation_and_erasure(env):
    identities = {}
    for role in ("reader", "contributor", "reviewer", "unscoped-admin"):
        principal = env.identities.create_principal(
            env.owner, PrincipalInput(name=role, administrator=role == "unscoped-admin")
        )
        key = env.identities.create_key(env.owner, UUID(principal["id"]), KeyInput(name=role))
        identity = env.db.authenticate(key["api_key"])
        if role != "unscoped-admin":
            env.identities.grant(env.owner, env.space, identity.principal_id, GrantInput(role=role))
        identities[role] = (identity, key["api_key"])
    saved = env.memory.save(env.owner, env.space, MemoryInput(content="Private decision"), "save")
    memory = UUID(saved["memory_id"])
    env.memory.revise(
        identities["contributor"][0],
        memory,
        RevisionInput(
            content="Corrected decision", expected_version=1, reason="PRIVATE_CORRECTION_NOTE"
        ),
        "correct",
    )
    env.memory.review(
        env.owner,
        memory,
        ReviewInput(expected_version=2, state="quarantined", reason="PRIVATE_REVIEW_NOTE"),
    )
    with TestClient(create_app(env.db, env.embedder)) as client:
        path = f"/v1/spaces/{env.space}/activity"
        for role, expected in (
            ("reader", 403),
            ("contributor", 403),
            ("reviewer", 200),
            ("unscoped-admin", 404),
        ):
            identity, key = identities[role]
            result = client.get(path, headers={"Authorization": "Bearer " + key})
            assert result.status_code == expected, result.text
            with env.db.transaction(identity) as conn:
                count = conn.execute(
                    "SELECT count(*) AS n FROM mnemion.memory_change_notes"
                ).fetchone()["n"]
                assert count == (2 if role == "reviewer" else 0)
                audit = conn.execute(
                    "SELECT details FROM mnemion.audit_events WHERE space_id=%s", (env.space,)
                ).fetchall()
                assert all("reason" not in event["details"] for event in audit)
                if role != "reviewer":
                    assert audit == []
        owner = {"Authorization": "Bearer " + env.token}
        notes = client.get(path, headers=owner, params={"memory_id": str(memory)}).json()["items"]
        assert {n["reason"] for n in notes if n["reason"]} == {
            "PRIVATE_CORRECTION_NOTE",
            "PRIVATE_REVIEW_NOTE",
        }
        assert client.get(path, headers=owner, params={"limit": 101}).status_code == 422
        env.identities.revoke_grant(env.owner, env.space, identities["reviewer"][0].principal_id)
        assert (
            client.get(
                path, headers={"Authorization": "Bearer " + identities["reviewer"][1]}
            ).status_code
            == 404
        )
        env.memory.forget(env.owner, memory, expected_version=3, key="erase")
        assert "PRIVATE_" not in client.get(path, headers=owner).text
        with psycopg.connect(env.admin_dsn) as conn:
            assert (
                conn.execute(
                    "SELECT count(*) FROM mnemion.memory_change_notes WHERE memory_id=%s", (memory,)
                ).fetchone()[0]
                == 2
            )
        while env.worker.run_once():
            pass
        with psycopg.connect(env.admin_dsn) as conn:
            assert (
                conn.execute(
                    "SELECT count(*) FROM mnemion.memory_change_notes WHERE memory_id=%s", (memory,)
                ).fetchone()[0]
                == 0
            )
            events = conn.execute(
                "SELECT details FROM mnemion.audit_events WHERE resource_id=%s", (str(memory),)
            ).fetchall()
            assert events and "PRIVATE_" not in str(events)


def test_failed_revision_rolls_back_its_private_note_and_audit(env, monkeypatch):
    from mnemion.service import memory as implementation

    saved = env.memory.save(env.owner, env.space, MemoryInput(content="Original"), "save")
    memory = UUID(saved["memory_id"])
    original_audit = implementation.audit

    def fail_after_audit(*args, **kwargs):
        original_audit(*args, **kwargs)
        raise OSError("Injected failure after note insertion")

    monkeypatch.setattr(implementation, "audit", fail_after_audit)
    with pytest.raises(OSError):
        env.memory.revise(
            env.owner,
            memory,
            RevisionInput(content="Failed", expected_version=1, reason="Never committed"),
            "fail",
        )
    assert env.memory.fetch(env.owner, memory)["version"] == 1
    with env.db.transaction(env.owner) as conn:
        assert (
            conn.execute("SELECT count(*) AS n FROM mnemion.memory_change_notes").fetchone()["n"]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM mnemion.audit_events WHERE action='memory.revised'"
            ).fetchone()["n"]
            == 0
        )
