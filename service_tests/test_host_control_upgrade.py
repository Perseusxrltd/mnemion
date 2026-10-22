"""Real authority and signed plans around the existing mocked migration fixture.

These checks exercise authorization/cutover ordering, not native or live backup
acceptance. Encrypted Git/SSH delivery has its own actual transport checks.
"""

import base64
import json

import pytest

from mnemion.host_control import HostControlError, backup, upgrade
from mnemion.host_control.store import Store
from mnemion.service import update_state as state_io
from mnemion.service.update_manifest import ManifestError, sign_manifest
from service_tests.test_host_control_store import operator, request
from service_tests.test_managed_upgrade import upgrade_host as upgrade_host
from service_tests.test_service_updates import managed as managed


@pytest.fixture
def controlled(upgrade_host, tmp_path, monkeypatch):
    host = upgrade_host
    root = state_io.directory(tmp_path / "independent-control")
    store, identity = Store.adopt(
        root / "authority",
        host.managed.state,
        "managed-fixture",
        operator(),
    )
    value = {"host_id": identity["host_id"], "service_state": str(host.managed.state)}
    state_io.write(
        host.managed.root / "releases" / host.candidate["slot"] / "envelope.json",
        {
            "envelope": base64.b64encode(
                sign_manifest(host.managed.value, host.managed.key.private_bytes_raw())
            ).decode()
        },
    )
    monkeypatch.setattr(backup, "fingerprint", lambda _: "a" * 64)

    def fresh(_root, _value, operation_id):
        host.events.append("independent-backup")
        return {
            "operation_id": operation_id,
            "key_id": "a" * 24,
            "verified_at": "2026-10-22T20:00:00+00:00",
            "snapshot_at": "fixture-snapshot",
            "ledger_at": "fixture-ledger",
            "remote_readback_verified": True,
            "independent_storage_confirmed": True,
        }

    def verify(_root, _value, receipt):
        host.events.append("independent-readback")
        return {"original_backup": receipt, "reverified_at": "2026-10-22T20:01:00+00:00"}

    monkeypatch.setattr(backup, "fresh", fresh)
    monkeypatch.setattr(backup, "verify_existing", verify)
    return root, value, store, identity, host


def planned(controlled):
    root, value, store, identity, _ = controlled
    spec = request(identity, "upgrade.plan")
    store.enqueue(identity["operator_id"], spec)
    job = store.claim()
    result, context = upgrade.execute(root, value, store, job, spec, before_effect=lambda: None)
    store.finish(job["operation_id"], result=result, context=context)
    return result


def applying(controlled, plan):
    root, value, store, identity, _ = controlled
    spec = request(
        identity,
        "upgrade.apply",
        plan_id=plan["plan_id"],
        plan_sha256=plan["plan_sha256"],
        approve_service_interruption=True,
    )
    store.enqueue(identity["operator_id"], spec)
    job = store.claim()

    def execute():
        return upgrade.execute(
            root,
            value,
            store,
            job,
            spec,
            before_effect=lambda: store.guard(job["operation_id"], record_effect=True),
        )

    return job, execute


def test_reviewed_signed_plan_requires_independent_backup_before_process_changes(controlled):
    _, _, store, identity, host = controlled
    plan = planned(controlled)
    assert plan["target_version"] == host.candidate["version"]
    assert plan["independent_backup_configured"] and plan["service_interruption"]
    assert "fixture-uv" not in json.dumps(plan) and "command" not in plan
    assert host.events == []
    job, execute = applying(controlled, plan)
    result, context = execute()
    store.finish(job["operation_id"], result=result, context=context)
    assert result["status"] == "upgraded" and result["database_restored"] is False
    assert host.events == [
        "backup",
        "independent-backup",
        "updater-stop",
        "stop",
        "migrate",
        "start",
        "updater-start",
    ]
    assert store.operation(identity["operator_id"], identity["host_id"], job["operation_id"])[
        "effect_started_at"
    ]


def test_host_changes_after_review_refuse_before_backup_or_service_effects(controlled):
    _, _, _, _, host = controlled
    plan = planned(controlled)
    config = state_io.read(host.managed.root / "config.json")
    config["enabled"] = not config["enabled"]
    state_io.write(host.managed.root / "config.json", config)
    _, execute = applying(controlled, plan)
    with pytest.raises(HostControlError, match="fresh plan"):
        execute()
    assert host.events == []


def test_retired_authority_during_backup_cannot_cross_the_cutover_boundary(controlled, monkeypatch):
    _, _, store, identity, host = controlled
    first = identity["operator_id"]
    store.grant(
        first,
        request(
            identity,
            "operators.grant",
            expected_revision=1,
            operator=operator("Replacement custodian").model_dump(mode="json"),
        ),
    )
    original = backup.fresh

    def retire(*args):
        result = original(*args)
        store.revoke(
            first, request(identity, "operators.revoke", expected_revision=2, operator_id=first)
        )
        return result

    monkeypatch.setattr(backup, "fresh", retire)
    plan = planned(controlled)
    _, execute = applying(controlled, plan)
    with pytest.raises(HostControlError, match="authority changed"):
        execute()
    assert host.events == ["backup", "independent-backup"]
    assert not (host.managed.root / "upgrade-journal.json").exists()
    assert host.runtime.schema == host.managed.old["migrations"]


def test_forward_recovery_reverifies_without_repeating_backup_or_migration(controlled):
    _, _, store, identity, host = controlled
    initial = planned(controlled)
    job, execute = applying(controlled, initial)
    host.runtime.fail = "readiness"
    with pytest.raises(ManifestError, match="No database backup was restored"):
        execute()
    store.inspection(job["operation_id"])
    host.runtime.fail = None
    recovery_plan = planned(controlled)
    assert recovery_plan["resume"]
    recovering, resume = applying(controlled, recovery_plan)
    result, context = resume()
    store.finish(recovering["operation_id"], result=result, context=context)
    assert host.events.count("independent-backup") == host.events.count("migrate") == 1
    assert host.events.count("independent-readback") == 1
    original = store.operation(identity["operator_id"], identity["host_id"], job["operation_id"])
    assert original["phase"] == "failed" and original["error"] == "operation_uncertain"
    assert original["result"]["recovery_operation"] == recovering["operation_id"]
    assert host.runtime.accepted == ["existing-memory", "accepted-before-readiness-failure"]
