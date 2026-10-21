"""Actual producer bytes through offline custody, lost replies and current ACLs."""

import hashlib
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest

from mnemion.connectors.capture_delivery import deliver
from mnemion.connectors.conversation_capture import capture_available
from mnemion.connectors.conversation_inbox import open_inbox
from mnemion.connectors.live_conversations import ConversationProvider
from mnemion.sdk import Client
from mnemion.service.api import create_app
from mnemion.service.capture_custody import CaptureCustody
from mnemion.service.capture_models import CaptureGrantInput, CaptureSourceInput
from mnemion.service.connector_models import BindingInput
from mnemion.service.errors import ServiceError
from service_tests.test_clients import running
from service_tests.test_live_conversations import conversation_source as conversation_source


FIXTURE = Path(__file__).parent / "fixtures/codex-0.163"


@pytest.mark.parametrize("mode", ["complete", "messages"])
def test_codex_resume_offline_delivery_reconciliation_and_current_reader_control(
    env, conversation_source, tmp_path, monkeypatch, mode
):
    manifest = json.loads((FIXTURE / "manifest.json").read_text())
    originals = {}
    for record in manifest["files"]:
        raw = (FIXTURE / record["file"]).read_bytes()
        assert len(raw) == record["bytes"] and hashlib.sha256(raw).hexdigest() == record["sha256"]
        originals[record["file"]] = raw
    legacy, connector, operator, reader, secret, config = conversation_source
    config.provider.capture_mode = mode
    config.provider.segment_records = 256
    custody, source, grant = CaptureCustody(env.memory), uuid4(), uuid4()
    custody.source(
        env.owner,
        connector,
        source,
        CaptureSourceInput(
            namespace="fixture",
            name="Actual Codex fixture",
            members=["employee:reader"],
            capture_mode=mode,
            keep_accepted=True,
        ),
    )
    custody.grant(env.owner, source, grant, CaptureGrantInput(device_key_id=operator.key_id))
    binding = {
        "tenant_id": str(env.owner.tenant_id),
        "connector_id": str(connector),
        "source_id": str(source),
        "grant_id": str(grant),
        "namespace": "fixture",
        "capture_mode": mode,
    }
    private = tmp_path / "private-inbox", binding, os.urandom(32)
    resumed = config.provider.path / "resumed.jsonl"
    raw = originals[resumed.name]
    first = raw[: manifest["first_turn_bytes"]]
    assert hashlib.sha256(first).hexdigest() == manifest["first_turn_sha256"]
    resumed.write_bytes(first)

    def no_network(*args, **kwargs):
        pytest.fail("Offline local acceptance must not contact the service")

    with monkeypatch.context() as offline:
        offline.setattr(Client, "request", no_network)
        with open_inbox(*private, create=True) as inbox:
            initial = capture_available(inbox, ConversationProvider(config.provider))
            assert initial["completed"] and initial["pending_events"] > 0
            first_page = inbox.page()["page"]
            contents = [event["item"]["memory"]["content"] for event in first_page["events"]]
            assert any(manifest["replies"][0] in content for content in contents)
        cut = (
            raw.index(manifest["prompts"][1].encode())
            + len("Fixture user two: Orbit module caf".encode())
            + 1
        )
        assert cut > len(first) and raw[cut - 1 : cut + 1] == "é".encode()
        with resumed.open("ab") as stream:
            stream.write(raw[len(first) : cut])
        with open_inbox(*private) as inbox:
            partial = capture_available(inbox, ConversationProvider(config.provider))
            assert partial["completed"]
            scope = partial["scopes"][0]["external_id"]
            assert inbox.checkpoint(scope)["complete_end"] == raw[:cut].rfind(b"\n") + 1
            assert inbox.page()["page"] == first_page
        with resumed.open("ab") as stream:
            stream.write(raw[cut:])
        (config.provider.path / "independent.jsonl").write_bytes(originals["independent.jsonl"])
        with open_inbox(*private) as inbox:
            complete = capture_available(inbox, ConversationProvider(config.provider))
            assert complete["completed"] and complete["pending_events"] > initial["pending_events"]
            for name, content in originals.items():
                assert (config.provider.path / name).read_bytes() == content
                (config.provider.path / name).unlink()
            missing = capture_available(inbox, ConversationProvider(config.provider))
            assert missing["pending_events"] == complete["pending_events"]
            assert inbox.page()["page"] == first_page

    receipts = {}
    with (
        running(create_app(env.db, env.embedder)) as url,
        Client(url, secret, retries=0) as client,
        open_inbox(*private) as inbox,
    ):
        request = client.request

        def lose_reply(method, path, **kwargs):
            assert not inbox.connection.in_transaction
            value = request(method, path, **kwargs)
            if method == "POST" and path.endswith("/pages"):
                receipts[value["page_id"]] = value
                raise httpx.ReadTimeout("Lost reply after the real PostgreSQL commit")
            return value

        client.request = lose_reply
        with pytest.raises(httpx.ReadTimeout):
            deliver(inbox, client)
        assert inbox.status()["unknown_pages"] == 1
    assert set(receipts) == {first_page["page_id"]}

    with (
        running(create_app(env.db, env.embedder)) as url,
        Client(url, secret, retries=0) as client,
        open_inbox(*private) as inbox,
    ):
        request, posted = client.request, []

        def observe(method, path, **kwargs):
            assert not inbox.connection.in_transaction
            value = request(method, path, **kwargs)
            if method == "POST" and path.endswith("/pages"):
                posted.append(kwargs["body"]["page_id"])
                receipts[value["page_id"]] = value
            return value

        client.request = observe
        for _ in range(10):
            delivered = deliver(inbox, client)
            if delivered["pending_events"] == 0:
                break
        assert delivered["pending_events"] == delivered["unknown_pages"] == 0
        assert first_page["page_id"] not in posted
        assert not list(config.provider.path.iterdir())

    identifiers = {
        UUID(item["memory_id"]) for receipt in receipts.values() for item in receipt["items"]
    }
    memories = [env.memory.fetch(reader, memory) for memory in identifiers]
    projections = [value for value in memories if value["metadata"].get("projection")]
    assert projections
    for turn in range(3):
        for field in ("prompts", "replies"):
            assert any(manifest[field][turn] in value["content"] for value in projections)
    assert all("environment_context" not in value["content"] for value in projections)
    raw_memories = [value for value in memories if not value["metadata"].get("projection")]
    assert bool(raw_memories) == (mode == "complete")
    for value in raw_memories:
        metadata = value["metadata"]
        content = originals[metadata["path"]][
            metadata["source_byte_start"] : metadata["source_byte_end"]
        ]
        assert value["content"].encode() == content
        assert hashlib.sha256(content).hexdigest() == metadata["source_segment_sha256"]

    binding_input = BindingInput(
        external_id="employee:reader", principal_id=reader.principal_id, role="reviewer"
    )
    legacy.binding(env.owner, connector, binding_input, remove=True)
    for memory in identifiers:
        with pytest.raises(ServiceError):
            env.memory.fetch(reader, memory)
    legacy.binding(env.owner, connector, binding_input)
    forgotten = next(value for value in projections if value["metadata"]["path"] == "resumed.jsonl")
    env.memory.forget(
        reader,
        UUID(forgotten["memory_id"]),
        expected_version=forgotten["version"],
        key="actual-codex-forget",
    )
    with (
        running(create_app(env.db, env.embedder)) as url,
        Client(url, secret, retries=0) as client,
        open_inbox(*private) as inbox,
    ):
        reconciled = deliver(inbox, client)
        assert reconciled["forgotten_events"] > 0
        assert reconciled["pending_events"] == 0
    for value in memories:
        if value["metadata"]["path"] == "resumed.jsonl":
            with pytest.raises(ServiceError):
                env.memory.fetch(reader, UUID(value["memory_id"]))
        else:
            assert env.memory.fetch(reader, UUID(value["memory_id"]))
