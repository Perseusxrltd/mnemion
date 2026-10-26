"""Independent host authority and interrupted work use a real private database."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from mnemion.host_control import HostControlError
from mnemion.host_control.protocol import ROLES, Operator, canonical, parse
from mnemion.host_control.receiver import dispatch
from mnemion.host_control.store import Store
from mnemion.host_control import store as store_module

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Managed hosts require Unix")


def operator(name="First custodian", role="custodian", expires_at=None):
    key = (
        Ed25519PrivateKey.generate()
        .public_key()
        .public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
        .decode()
    )
    return Operator(name=name, public_key=key, role=role, expires_at=expires_at)


@pytest.fixture
def adopted(tmp_path):
    service = tmp_path / "managed-service"
    service.mkdir(mode=0o700)
    return Store.adopt(tmp_path / "independent-control", service, "existing-service", operator())


def request(adoption, action, **fields):
    now = datetime.now(timezone.utc)
    lifetime = (
        {}
        if action in {"host.status", "operations.get", "operations.list", "operators.list"}
        else {
            "issued_at": now.isoformat(),
            "valid_until": (now + timedelta(minutes=30)).isoformat(),
        }
    )
    return parse(
        json.dumps(
            {
                "protocol": 1,
                "host_id": adoption["host_id"],
                "request_id": str(uuid4()),
                "action": action,
                **lifetime,
                **fields,
            }
        ).encode()
    )


def grant(adopted, spec):
    store, identity = adopted
    revision = store.authority(identity["operator_id"], identity["host_id"])["revision"]
    return store.grant(
        identity["operator_id"],
        request(
            identity,
            "operators.grant",
            expected_revision=revision,
            operator=spec.model_dump(mode="json"),
        ),
    )["operator_id"]


def test_host_authority_is_independent_of_memory_keys_and_wrong_hosts(adopted):
    store, identity = adopted
    actor, host = identity["operator_id"], identity["host_id"]
    assert "service.start" in store.authority(actor, host)["actions"]
    for wrong_actor, wrong_host in [(str(uuid4()), host), (actor, str(uuid4()))]:
        with pytest.raises(HostControlError, match="Current authority"):
            store.authority(wrong_actor, wrong_host)
    reader = grant(adopted, operator("Observe only", "observer"))
    assert store.authority(reader, host)["actions"] == [
        "host.status",
        "operations.get",
        "operations.list",
    ]
    with pytest.raises(HostControlError, match="not allowed"):
        store.enqueue(reader, request(identity, "service.stop", approve_service_interruption=True))


def test_same_job_survives_lost_reply_and_conflicting_reuse_is_refused(adopted):
    store, identity = adopted
    actor = identity["operator_id"]
    original = request(identity, "service.stop", approve_service_interruption=True)
    queued = store.enqueue(actor, original)
    reopened = Store(store.root)
    assert reopened.enqueue(actor, original) == queued
    other = original.model_copy(update={"action": "service.start"})
    with pytest.raises(HostControlError, match="different work"):
        reopened.enqueue(actor, other)
    claimed = reopened.claim()
    assert claimed["operation_id"] == queued["operation_id"]
    reopened.finish(queued["operation_id"], result={"stopped": True})
    assert reopened.enqueue(actor, original)["phase"] == "succeeded"
    assert reopened.claim() is None


def test_host_reply_disposition_describes_this_intake_without_changing_durable_work(adopted):
    store, identity = adopted
    actor = identity["operator_id"]
    original = request(identity, "service.stop", approve_service_interruption=True)
    raw = canonical(original.model_dump(mode="json"))
    first = json.loads(dispatch(store, actor, raw))
    assert first["result"]["request_disposition"] == "new"
    repeated = json.loads(dispatch(Store(store.root), actor, raw))
    assert repeated["result"]["request_disposition"] == "replayed"
    first["result"].pop("request_disposition")
    repeated["result"].pop("request_disposition")
    assert repeated == first
    assert set(first) == {
        "protocol",
        "host_id",
        "operator_id",
        "request_id",
        "ok",
        "result",
        "error",
    }
    lookup = request(identity, "operations.get", operation_id=str(original.request_id))
    observed = json.loads(dispatch(store, actor, canonical(lookup.model_dump(mode="json"))))
    assert "request_disposition" not in observed["result"]
    with store.transaction() as connection:
        assert connection.execute("SELECT count(*) FROM operations").fetchone()[0] == 1
        saved = connection.execute("SELECT request,result FROM operations").fetchone()
        assert "request_disposition" not in saved["request"]
        assert saved["result"] is None


def test_concurrent_identical_host_intake_has_exactly_one_new_reply(adopted):
    store, identity = adopted
    actor = identity["operator_id"]
    original = request(identity, "service.stop", approve_service_interruption=True)
    raw = canonical(original.model_dump(mode="json"))

    def invoke(_):
        return json.loads(dispatch(Store(store.root), actor, raw))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(invoke, range(2)))
    assert sorted(item["result"]["request_disposition"] for item in results) == ["new", "replayed"]
    with store.transaction() as connection:
        assert connection.execute("SELECT count(*) FROM operations").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT count(*) FROM audit WHERE event='operation_queued'"
            ).fetchone()[0]
            == 1
        )


def test_grant_and_revoke_disposition_never_enters_saved_authority_receipts(adopted):
    store, identity = adopted
    actor = identity["operator_id"]
    enroll = request(
        identity,
        "operators.grant",
        expected_revision=1,
        operator=operator("Secondary operator", "operator").model_dump(mode="json"),
    )
    raw = canonical(enroll.model_dump(mode="json"))
    first = json.loads(dispatch(store, actor, raw))
    assert first["result"]["request_disposition"] == "new"
    assert (
        json.loads(dispatch(Store(store.root), actor, raw))["result"]["request_disposition"]
        == "replayed"
    )
    retire = request(
        identity,
        "operators.revoke",
        expected_revision=2,
        operator_id=first["result"]["operator_id"],
    )
    raw = canonical(retire.model_dump(mode="json"))
    assert json.loads(dispatch(store, actor, raw))["result"]["request_disposition"] == "new"
    assert (
        json.loads(dispatch(Store(store.root), actor, raw))["result"]["request_disposition"]
        == "replayed"
    )
    assert store.authority(actor, identity["host_id"])["revision"] == 3
    with store.transaction() as connection:
        records = connection.execute("SELECT request,result FROM operations").fetchall()
    assert len(records) == 2
    assert all("request_disposition" not in row["request"] + row["result"] for row in records)


def test_refused_and_conflicting_host_intake_never_grant_a_fresh_reply(adopted):
    store, identity = adopted
    actor = identity["operator_id"]
    original = request(identity, "service.stop", approve_service_interruption=True)
    raw = canonical(original.model_dump(mode="json"))
    refused = json.loads(dispatch(store, str(uuid4()), raw))
    assert refused["ok"] is False and refused["result"] is None
    assert json.loads(dispatch(store, actor, raw))["result"]["request_disposition"] == "new"
    changed = original.model_copy(update={"action": "service.start"})
    conflict = json.loads(dispatch(store, actor, canonical(changed.model_dump(mode="json"))))
    assert conflict["ok"] is False and conflict["result"] is None
    assert conflict["error"]["code"] == "operation_conflict"
    for action in ("host.status", "operations.list", "operators.list"):
        lookup = request(identity, action)
        result = json.loads(dispatch(store, actor, canonical(lookup.model_dump(mode="json"))))
        assert result["ok"] and "request_disposition" not in result["result"]


def test_each_typed_host_command_has_owned_selection_or_an_explicit_read_exclusion():
    from pathlib import Path

    origins = json.loads(Path("mnemion/product_telemetry/desktop-origins.json").read_text())
    selected = origins["operations"]["host.request"]
    assert selected["selector"] == "request.action" and selected["fresh_receipt"] is True
    assert selected["completion"] == "accepted"
    assert set(selected["variants"]) | set(selected["variant_exclusions"]) == ROLES["custodian"]
    assert not set(selected["variants"]) & set(selected["variant_exclusions"])
    assert set(selected["variant_exclusions"]) == {
        "host.status",
        "operations.get",
        "operations.list",
        "operators.list",
    }
    assert all(value in origins["exclusions"] for value in selected["variant_exclusions"].values())


def test_lost_grant_and_revocation_replies_do_not_repeat_authority_changes(adopted):
    store, identity = adopted
    actor = identity["operator_id"]
    enroll = request(
        identity,
        "operators.grant",
        expected_revision=1,
        operator=operator("Secondary operator", "operator").model_dump(mode="json"),
    )
    first = store.grant(actor, enroll)
    assert Store(store.root).grant(actor, enroll) == first
    retire = request(
        identity, "operators.revoke", expected_revision=2, operator_id=first["operator_id"]
    )
    second = store.revoke(actor, retire)
    assert Store(store.root).revoke(actor, retire) == second
    assert store.authority(actor, identity["host_id"])["revision"] == 3


def test_revocation_cancels_queued_work_without_claiming_running_work_was_cancelled(adopted):
    store, identity = adopted
    delegated = grant(adopted, operator("On call", "operator"))
    first = store.enqueue(
        delegated, request(identity, "service.start", approve_service_interruption=True)
    )
    second = store.enqueue(
        delegated, request(identity, "service.stop", approve_service_interruption=True)
    )
    assert store.claim()["operation_id"] == first["operation_id"]
    store.revoke(
        identity["operator_id"],
        request(
            identity,
            "operators.revoke",
            expected_revision=2,
            operator_id=delegated,
        ),
    )
    assert (
        store.operation(identity["operator_id"], identity["host_id"], first["operation_id"])[
            "phase"
        ]
        == "running"
    )
    assert (
        store.operation(identity["operator_id"], identity["host_id"], second["operation_id"])[
            "phase"
        ]
        == "cancelled"
    )
    assert store.claim() is None
    with pytest.raises(HostControlError, match="Current authority"):
        store.authority(delegated, identity["host_id"])


def test_expiry_rechecked_at_worker_claim(adopted):
    store, identity = adopted
    delegated = grant(
        adopted,
        operator(
            "Temporary on call", "operator", datetime.now(timezone.utc) + timedelta(minutes=2)
        ),
    )
    queued = store.enqueue(
        delegated, request(identity, "service.stop", approve_service_interruption=True)
    )
    # This models elapsed expiry without a sleeping test or changing authority.
    with store.transaction() as conn:
        conn.execute(
            "UPDATE operators SET expires_at=? WHERE id=?",
            ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), delegated),
        )
    assert store.claim() is None
    assert (
        store.operation(identity["operator_id"], identity["host_id"], queued["operation_id"])[
            "phase"
        ]
        == "cancelled"
    )


def test_final_permanent_custodian_cannot_be_replaced_only_by_an_expiring_key(adopted):
    store, identity = adopted
    temporary = grant(
        adopted,
        operator(
            "Temporary custodian", "custodian", datetime.now(timezone.utc) + timedelta(days=1)
        ),
    )
    with pytest.raises(HostControlError, match="permanent custodian"):
        store.revoke(
            temporary,
            request(
                identity,
                "operators.revoke",
                expected_revision=2,
                operator_id=identity["operator_id"],
            ),
        )
    assert store.authority(identity["operator_id"], identity["host_id"])["revision"] == 2


def test_concurrent_custodian_retirement_keeps_one_current_authority(adopted):
    store, identity = adopted
    second = grant(adopted, operator("Independent custodian"))
    first = identity["operator_id"]

    def retire(actor, target):
        try:
            Store(store.root).revoke(
                actor,
                request(identity, "operators.revoke", expected_revision=2, operator_id=target),
            )
            return True
        except HostControlError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        a = executor.submit(retire, first, second)
        b = executor.submit(retire, second, first)
        assert sorted([a.result(), b.result()]) == [False, True]
    with store.transaction() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM operators WHERE role='custodian' AND revoked_at IS NULL AND expires_at IS NULL"
            ).fetchone()[0]
            == 1
        )


def test_interrupted_work_requires_inspection_instead_of_automatic_replay(adopted):
    store, identity = adopted
    actor = identity["operator_id"]
    original = request(identity, "service.stop", approve_service_interruption=True)
    queued = store.enqueue(actor, original)
    store.claim()
    reopened = Store(store.root)
    assert reopened.interrupted() == 1
    assert reopened.enqueue(actor, original)["phase"] == "inspection_required"
    assert reopened.interrupted() == 0
    assert reopened.claim() is None
    with pytest.raises(HostControlError, match="existing operation"):
        reopened.finish(queued["operation_id"], result={"stopped": True})


def test_existing_host_control_and_public_key_cannot_be_overwritten(adopted, tmp_path):
    store, identity = adopted
    with pytest.raises(FileExistsError):
        Store.adopt(store.root, tmp_path / "managed-service", "other", operator())
    spec = operator("Separate key")
    grant(adopted, spec)
    with pytest.raises(HostControlError, match="new key"):
        grant(adopted, spec)
    assert (
        store.authority(identity["operator_id"], identity["host_id"])["host_id"]
        == identity["host_id"]
    )


def test_expired_completed_receipts_can_be_pruned_without_replaying_old_work(adopted, monkeypatch):
    store, identity = adopted
    actor = identity["operator_id"]
    original = request(identity, "service.stop", approve_service_interruption=True)
    store.enqueue(actor, original)
    store.claim()
    store.finish(original.request_id, result={"stopped": True})
    later = datetime.now(timezone.utc) + timedelta(hours=2)
    monkeypatch.setattr(store_module, "timestamp", lambda: later.isoformat(timespec="microseconds"))
    monkeypatch.setattr(store_module, "MAX_OPERATIONS", 1)
    monkeypatch.setattr(store_module, "RESERVED_AUTHORITY_OPERATIONS", 0)
    fresh = request(
        identity,
        "service.start",
        approve_service_interruption=True,
        issued_at=later.isoformat(),
        valid_until=(later + timedelta(minutes=10)).isoformat(),
    )
    store.enqueue(actor, fresh)
    with pytest.raises(HostControlError) as error:
        store.enqueue(actor, original)
    assert error.value.code == "request_expired"
    assert store.claim()["operation_id"] == str(fresh.request_id)
    assert store.claim() is None
    with store.transaction() as conn:
        assert conn.execute("SELECT count(*) FROM operations").fetchone()[0] == 1


def test_expired_approval_never_starts_queued_work(adopted, monkeypatch):
    store, identity = adopted
    action = request(identity, "service.stop", approve_service_interruption=True)
    store.enqueue(identity["operator_id"], action)
    later = datetime.now(timezone.utc) + timedelta(hours=2)
    monkeypatch.setattr(store_module, "timestamp", lambda: later.isoformat(timespec="microseconds"))
    assert store.claim() is None
    outcome = store.operation(identity["operator_id"], identity["host_id"], action.request_id)
    assert outcome["phase"] == "cancelled" and outcome["error"] == "request_expired"


def test_filled_work_queue_retains_capacity_for_operator_revocation(adopted, monkeypatch):
    store, identity = adopted
    delegated = grant(adopted, operator("On call", "operator"))
    monkeypatch.setattr(store_module, "MAX_OPERATIONS", 8)
    monkeypatch.setattr(store_module, "RESERVED_AUTHORITY_OPERATIONS", 2)
    for _ in range(5):
        store.enqueue(
            delegated, request(identity, "service.stop", approve_service_interruption=True)
        )
    with pytest.raises(HostControlError) as error:
        store.enqueue(
            delegated, request(identity, "service.stop", approve_service_interruption=True)
        )
    assert error.value.code == "operation_limit"
    store.revoke(
        identity["operator_id"],
        request(identity, "operators.revoke", expected_revision=2, operator_id=delegated),
    )
    assert store.claim() is None
    with pytest.raises(HostControlError):
        store.authority(delegated, identity["host_id"])


def test_uncertain_work_is_not_pruned_after_its_approval_expires(adopted, monkeypatch):
    store, identity = adopted
    action = request(identity, "service.stop", approve_service_interruption=True)
    store.enqueue(identity["operator_id"], action)
    store.claim()
    store.interrupted()
    later = datetime.now(timezone.utc) + timedelta(hours=2)
    monkeypatch.setattr(store_module, "timestamp", lambda: later.isoformat(timespec="microseconds"))
    monkeypatch.setattr(store_module, "MAX_OPERATIONS", 1)
    monkeypatch.setattr(store_module, "RESERVED_AUTHORITY_OPERATIONS", 0)
    fresh = request(
        identity,
        "service.start",
        approve_service_interruption=True,
        issued_at=later.isoformat(),
        valid_until=(later + timedelta(minutes=10)).isoformat(),
    )
    with pytest.raises(HostControlError) as error:
        store.enqueue(identity["operator_id"], fresh)
    assert error.value.code == "operation_limit"
    assert (
        store.operation(identity["operator_id"], identity["host_id"], action.request_id)["phase"]
        == "inspection_required"
    )


@pytest.mark.parametrize("issue_delta, expiry_delta", [(0, 0), (0, 61), (60, 30)])
def test_operation_approval_has_a_bounded_lifetime(adopted, issue_delta, expiry_delta):
    _, identity = adopted
    now = datetime.now(timezone.utc)
    with pytest.raises(HostControlError):
        request(
            identity,
            "service.stop",
            approve_service_interruption=True,
            issued_at=(now + timedelta(minutes=issue_delta)).isoformat(),
            valid_until=(now + timedelta(minutes=expiry_delta)).isoformat(),
        )


@pytest.mark.parametrize(
    "fields",
    [
        {"action": "service.stop"},
        {"action": "service.stop", "approve_service_interruption": False},
        {"action": "service.stop", "approve_service_interruption": 1},
        {"action": "host.status", "protocol": True},
        {
            "action": "service.stop",
            "approve_service_interruption": True,
            "command": "unrequested-command",
        },
        {
            "action": "upgrade.apply",
            "plan_id": str(uuid4()),
            "plan_sha256": "unreviewed",
            "approve_service_interruption": True,
        },
    ],
)
def test_protocol_refuses_unapproved_or_untyped_operations(adopted, fields):
    _, identity = adopted
    with pytest.raises(HostControlError, match="published host-operation schema"):
        request(identity, **fields)
