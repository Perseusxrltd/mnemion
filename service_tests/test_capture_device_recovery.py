"""Replacement device delivery preserves old revocation and current forgetting."""

import os
from uuid import UUID, uuid4

import httpx
import pytest

from mnemion import backup_encryption as encryption
from mnemion.connectors.capture_archive import export_archive
from mnemion.connectors.capture_delivery import deliver
from mnemion.connectors.capture_transfer import restore_device_copy
from mnemion.connectors.conversation_capture import capture_available
from mnemion.connectors.conversation_inbox import InboxError, open_inbox
from mnemion.connectors.live_conversations import ConversationProvider
from mnemion.sdk import Client, MnemionError
from mnemion.service.api import create_app
from mnemion.service.capture_models import CaptureGrantInput
from mnemion.service.errors import ServiceError
from mnemion.service.models import KeyInput
from service_tests.test_capture_custody import custody as custody
from service_tests.test_capture_delivery import settings
from service_tests.test_clients import running
from service_tests.test_live_conversations import (
    conversation_source as conversation_source,
    encoded,
)


@pytest.mark.parametrize("forget_after_backup", [False, True])
def test_new_grant_reconciles_unknown_old_delivery_and_new_evidence_without_restoring_access(
    env, custody, conversation_source, tmp_path, forget_after_backup
):
    original = settings(env, custody, conversation_source, tmp_path)
    service, source_id, grant_id, _, _ = custody
    _, _, operator, reader, secret, config = conversation_source
    log = config.provider.path / "chat.jsonl"
    log.write_bytes(
        encoded("Accepted before losing the first device") + encoded("Excluded", "tool")
    )
    with open_inbox(*original, create=True) as inbox:
        capture_available(inbox, ConversationProvider(config.provider))
    committed = []
    with (
        running(create_app(env.db, env.embedder)) as url,
        Client(url, secret, retries=0) as client,
        open_inbox(*original) as inbox,
    ):
        request = client.request

        def lose_reply(method, route, **options):
            response = request(method, route, **options)
            if method == "POST" and route.endswith("/pages"):
                committed.append(response)
                raise httpx.ReadTimeout("Synthetic lost original-device acknowledgement")
            return response

        client.request = lose_reply
        with pytest.raises(httpx.ReadTimeout):
            deliver(inbox, client)
    assert len(committed) == 1
    original_memory = UUID(committed[0]["items"][0]["memory_id"])
    with log.open("ab") as stream:
        stream.write(encoded("Queued locally and never sent by the original device"))
    archive, recovery_key = tmp_path / "device.capture", encryption.new_key()
    with open_inbox(*original) as inbox:
        capture_available(inbox, ConversationProvider(config.provider))
        assert inbox.status()["pending_events"] == 2 and inbox.status()["unknown_pages"] == 1
        inspected = export_archive(
            inbox,
            original[2],
            archive,
            recovery_key,
            staging_root=tmp_path / "staging",
            name="Lost device",
        )
    log.unlink()
    if forget_after_backup:
        env.memory.forget(
            reader, original_memory, expected_version=1, key="forget-after-device-backup"
        )
    service.status(env.owner, grant_id, revoke=True)
    env.identities.revoke_key(env.owner, operator.key_id)
    issued = env.identities.create_key(
        env.owner, operator.principal_id, KeyInput(name="Replacement device")
    )
    replacement = env.db.authenticate(issued["api_key"])
    new_grant = uuid4()
    service.grant(
        env.owner, source_id, new_grant, CaptureGrantInput(device_key_id=replacement.key_id)
    )
    recovered = restore_device_copy(
        archive,
        recovery_key,
        tmp_path / "replacement-inbox",
        staging_root=tmp_path / "staging",
        expected_sha256=inspected["archive_sha256"],
        selected_binding={**original[1], "grant_id": str(new_grant)},
        inbox_key=os.urandom(32),
    )
    with (
        running(create_app(env.db, env.embedder)) as url,
        Client(url, issued["api_key"], retries=0) as client,
        open_inbox(recovered.directory, recovered.binding, recovered.inbox_key) as inbox,
    ):
        observed = deliver(inbox, client)
        assert observed["pending_events"] == observed["unknown_pages"] == 0
        assert observed["stored_events"] == 2 - int(forget_after_backup)
        assert observed["forgotten_events"] == int(forget_after_backup)
        # A subsequent delivery must not invent another revision or page.
        assert deliver(inbox, client)["remote_committed_events"] == 0
        with Client(url, secret, retries=0) as retired, open_inbox(*original) as old:
            with pytest.raises((InboxError, MnemionError)):
                deliver(old, retired)
    with env.db.transaction(replacement) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) AS n FROM mnemion.capture_events WHERE source_id=%s", (source_id,)
            ).fetchone()["n"]
            == 2
        )
    assert service.status(env.owner, grant_id)["revoked_at"] is not None
    if forget_after_backup:
        with pytest.raises(ServiceError):
            env.memory.fetch(reader, original_memory)
    else:
        assert "Accepted before" in env.memory.fetch(reader, original_memory)["content"]
