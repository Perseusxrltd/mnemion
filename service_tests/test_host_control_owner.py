"""A machine owner can regain custody without weakening remote host roles."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncssh
import pytest

from mnemion.host_control import HostControlError, installation, owner
from mnemion.host_control.protocol import Operator, canonical, parse
from mnemion.host_control.store import Store
from service_tests.test_host_control_installation import prepared_host as prepared_host


def recovery(connection, *, revision=1, retire=()):
    key = asyncssh.generate_private_key("ssh-ed25519")
    now = datetime.now(timezone.utc)
    request = owner.OwnerRecovery(
        protocol=1,
        action="owner.custodian",
        host_id=connection["host_id"],
        request_id=uuid4(),
        issued_at=now,
        valid_until=now + timedelta(minutes=15),
        expected_revision=revision,
        operator=Operator(
            name="Recovered custodian",
            role="custodian",
            public_key=key.export_public_key().decode().strip(),
        ),
        approve_authority_recovery=True,
        retire_operator_ids=list(retire),
    )
    return request, key


def test_os_owner_recovers_lost_custodian_without_rekeying_host_or_replaying_grants(prepared_host):
    service, control, original, old_key, port = prepared_host
    adopted = installation.adopt(control, service, original, port=port)
    host_key = (control / "host.key").read_bytes()
    before = owner.status(control)
    request, replacement = recovery(
        adopted["connection"], retire=[adopted["connection"]["operator_id"]]
    )
    result = owner.recover(control, request)
    assert result == owner.recover(control, request)
    assert result["connection"]["host_id"] == before["host_id"]
    assert (control / "host.key").read_bytes() == host_key
    store = Store(control / "authority")
    assert (
        store.authenticate(replacement.export_public_key().decode().strip())
        == result["operator_id"]
    )
    with pytest.raises(HostControlError):
        store.authenticate(old_key.export_public_key().decode().strip())
    assert (
        store.authority(result["operator_id"], before["host_id"])["operator"]["role"] == "custodian"
    )
    assert len(owner.status(control)["operators"]) == 2
    with pytest.raises(HostControlError, match="different work"):
        owner.recover(control, request.model_copy(update={"expected_revision": 2}))
    # This command cannot be sent through SSH or the app's remote protocol.
    with pytest.raises(HostControlError, match="schema"):
        parse(canonical(request.model_dump(mode="json")))


def test_wrong_host_stale_authority_and_unapproved_recovery_preserve_all_grants(prepared_host):
    service, control, original, _, port = prepared_host
    connection = installation.adopt(control, service, original, port=port)["connection"]
    before = owner.status(control)
    request, _ = recovery(connection)
    for update in (
        {"expected_revision": 2},
        {"host_id": uuid4()},
        {"retire_operator_ids": [uuid4()]},
    ):
        with pytest.raises(HostControlError):
            owner.recover(control, request.model_copy(update=update))
        assert owner.status(control) == before
    for approval in (False, 1, "true"):
        with pytest.raises(ValueError):
            owner.OwnerRecovery.model_validate(
                {**request.model_dump(), "approve_authority_recovery": approval}
            )


def test_runtime_probe_does_not_accept_boolean_protocol_versions(prepared_host, monkeypatch):
    service, _, _, _, _ = prepared_host
    runtime = installation.updates.resolved_runtime(service)
    monkeypatch.setattr(
        installation.updates,
        "_command",
        lambda *args, **kwargs: '{"host_control_protocol":true,"store_format":1}',
    )
    with pytest.raises(HostControlError, match="cannot maintain"):
        installation.compatible_runtime(service, runtime)
