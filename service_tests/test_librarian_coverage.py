"""Stored attempts must not become successful coverage or bypass current access."""

from uuid import UUID

import pytest

from mnemion.service.errors import ServiceError
from mnemion.service.librarian import LibrarianService
from mnemion.service.librarian_models import (
    LibrarianCoverage,
    LibrarianRunInput,
    LibrarianSettingsInput,
)
from mnemion.service.librarian_provider import LibrarianRegistry
from mnemion.service.models import GrantInput, MemoryInput, RevisionInput, ReviewInput, SpaceInput
from service_tests.test_librarian import drain, profile, provider_fixture, reviewer, save, setup


def test_empty_and_unconfigured_coverage_does_not_need_a_model(env):
    service = LibrarianService(env.db, LibrarianRegistry({}), env.memory)
    empty = LibrarianCoverage.model_validate(service.coverage(env.owner, env.space))
    assert empty.active_memories == 0 and empty.profile_id is None
    assert len(empty.modes) == 2 and all(item.eligible == 0 for item in empty.modes)
    save(env)
    pending = LibrarianCoverage.model_validate(service.coverage(env.owner, env.space))
    assert pending.active_memories == 1 and pending.recent.calls_reserved == 0
    assert all(item.pending == item.unseen == 1 and item.checked == 0 for item in pending.modes)


def test_coverage_distinguishes_versions_attempts_skips_and_withheld_records(env):
    service, _ = setup(env)
    records = {
        name: UUID(save(env, key=name)["memory_id"])
        for name in (
            "checked",
            "skipped",
            "attempted",
            "changed",
            "unseen",
            "quarantined",
            "deleted",
        )
    }
    fingerprint = service.settings(env.owner, env.space)["profile_fingerprint"]
    with env.db.transaction(env.owner) as conn:
        for name, outcome in [
            ("checked", "completed"),
            ("skipped", "skipped"),
            ("attempted", "attempted"),
            ("changed", "completed"),
        ]:
            conn.execute(
                """INSERT INTO mnemion.librarian_observations
                   (tenant_id,space_id,memory_id,profile_fingerprint,mode,memory_version,outcome)
                   VALUES(%s,%s,%s,%s,'organize',1,%s)""",
                (env.owner.tenant_id, env.space, records[name], fingerprint, outcome),
            )
    env.memory.revise(
        env.owner,
        records["changed"],
        RevisionInput(
            expected_version=1,
            subject="New revision",
            content="The coffee cupboard changed after the earlier observation.",
            reason="Coverage fixture correction",
        ),
        "coverage-revise",
    )
    env.memory.review(
        env.owner,
        records["quarantined"],
        ReviewInput(expected_version=1, state="quarantined", reason="Review fixture"),
    )
    env.memory.forget(env.owner, records["deleted"], expected_version=1, key="coverage-delete")
    other = env.identities.create_space(env.owner, SpaceInput(name="Separate compartment"))
    env.memory.save(
        env.owner, UUID(other["id"]), MemoryInput(content="Other-space private evidence"), "other"
    )
    result = LibrarianCoverage.model_validate(service.coverage(env.owner, env.space))
    organize, review = result.modes
    assert result.active_memories == 6 and result.excluded_memories == 1
    assert (
        organize.eligible == 5 and organize.checked == organize.skipped == organize.attempted == 1
    )
    assert organize.pending == 2 and organize.changed == organize.unseen == 1
    assert organize.oldest_pending_at and organize.last_observed_at
    assert review.eligible == review.pending == review.unseen == 5 and review.checked == 0
    assert "Other-space private evidence" not in result.model_dump_json()
    assert "Coffee is stored" not in result.model_dump_json()
    service.registry.close()


def test_coverage_profile_history_and_usage_are_separate_without_new_model_calls(env):
    provider, calls = provider_fixture()
    service, runner = setup(env, provider=provider)
    save(env)
    service.create_run(env.owner, env.space, LibrarianRunInput(), "coverage-run")
    drain(runner)
    first = service.coverage(env.owner, env.space)
    assert first["modes"][0]["checked"] == 1 and first["recent"]["calls_completed"] == 1
    assert first["recent"]["request_bytes"] > 0 and len(calls) == 1
    replacement, _ = provider_fixture(selected_profile=profile(revision="coverage-v2"))
    service.registry.close()
    service.registry = LibrarianRegistry({"fixture": replacement})
    service.configure(
        env.owner, env.space, LibrarianSettingsInput(expected_version=1, profile_id="fixture")
    )
    changed = service.coverage(env.owner, env.space)
    assert changed["profile_fingerprint"] != first["profile_fingerprint"]
    assert changed["modes"][0]["pending"] == 1 and changed["modes"][0]["checked"] == 0
    assert changed["recent"]["runs"] == 0 and len(calls) == 1
    service.registry.close()


def test_coverage_requires_current_reviewer_authority(env):
    service, _ = setup(env)
    identity, _ = reviewer(env)
    save(env)
    assert service.coverage(identity, env.space)["active_memories"] == 1
    env.identities.grant(env.owner, env.space, identity.principal_id, GrantInput(role="reader"))
    with pytest.raises(ServiceError) as error:
        service.coverage(identity, env.space)
    assert error.value.status in (403, 404)
    env.identities.revoke_grant(env.owner, env.space, identity.principal_id)
    with pytest.raises(ServiceError) as error:
        service.coverage(identity, env.space)
    assert error.value.status in (403, 404)
    service.registry.close()
