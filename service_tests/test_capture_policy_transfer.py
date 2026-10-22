"""Policy transitions keep immutable evidence and original deletion families."""

import json
from uuid import UUID, uuid4

import pytest

from mnemion.capture_policy import CapturePolicy
from mnemion.connectors.live_conversations import ConversationProvider
from mnemion.sdk import Client
from mnemion.service.api import create_app
from mnemion.service.capture_models import CaptureGrantInput, CapturePolicyChange
from mnemion.service.errors import ServiceError
from service_tests.test_capture_custody import custody as custody, page
from service_tests.test_clients import running
from service_tests.test_live_conversations import conversation_source as conversation_source


def approve(service, owner, connector, source, operator, policy):
    review = service.policy_review(owner, connector, source)
    service.change_policy(
        owner,
        connector,
        source,
        uuid4(),
        CapturePolicyChange(
            expected_version=review["source"]["version"],
            review_token=review["review_token"],
            capture_policy=policy,
            previous_grants="revoke",
            confirm=True,
        ),
    )
    grant = uuid4()
    service.grant(owner, source, grant, CaptureGrantInput(device_key_id=operator.key_id))
    return grant


def scan(config, checkpoint=None):
    provider = ConversationProvider(config.provider)
    scope = provider.scopes()[0]
    with provider.snapshot(scope, checkpoint) as snapshot:
        items = [item for item in snapshot.items() if item is not None]
        snapshot.acknowledge()
        return scope, items, snapshot.checkpoint


def encoded(content, **fields):
    return (json.dumps({"role": "user", "content": content, **fields}) + "\n").encode()


@pytest.mark.parametrize("mode", ["complete", "messages"])
def test_reviewed_policy_change_can_deliver_same_prefix_without_restoring_forgotten_family(
    env, conversation_source, custody, mode
):
    service, source_id, _, _, _ = custody
    _, connector, operator, reader, secret, config = conversation_source
    policy = CapturePolicy(
        preset="conversation" if mode == "messages" else "detailed",
        capture_mode=mode,
        retention="until_deleted",
    )
    config.provider.capture_mode = mode
    config.provider.capture_policy = policy
    config.provider.segment_records = 1
    first = encoded("Preserved policy evidence")
    (config.provider.path / "chat.jsonl").write_bytes(first + encoded("Forget this family"))
    original_grant = approve(service, env.owner, connector, source_id, operator, policy)
    scope, before, checkpoint = scan(config)

    with running(create_app(env.db, env.embedder)) as url, Client(url, secret) as client:
        original = client.request(
            "POST",
            f"/v1/capture-grants/{original_grant}/pages",
            body=page(source_id, scope, *before).model_dump(mode="json"),
        )
        forgotten = next(
            receipt["memory_id"]
            for item, receipt in zip(before, original["items"], strict=True)
            if item.memory.metadata["source_byte_start"] == len(first)
        )
        env.memory.forget(reader, UUID(forgotten), expected_version=1, key="policy-family-forget")
        policy = policy.model_copy(update={"exclude": ["unselected/*.jsonl"]})
        current_grant = approve(service, env.owner, connector, source_id, operator, policy)
        config.provider.capture_policy = policy
        same_scope, after, _ = scan(config, checkpoint)
        assert same_scope == scope
        assert all(item.action == "upsert" for item in after)
        assert [item.external_id for item in after] == [item.external_id for item in before]
        assert [item.memory.content for item in after] == [item.memory.content for item in before]
        request = page(source_id, scope, *after)
        accepted = client.request(
            "POST",
            f"/v1/capture-grants/{current_grant}/pages",
            body=request.model_dump(mode="json"),
        )
        for old, item, receipt in zip(before, after, accepted["items"], strict=True):
            assert item.revision != old.revision
            assert item.memory.metadata["capture_policy_revision"] == policy.revision
            assert receipt["outcome"] == (
                "forgotten" if item.memory.metadata["source_byte_start"] == len(first) else "stored"
            )
        assert (
            client.request(
                "POST",
                f"/v1/capture-grants/{current_grant}/pages",
                body=request.model_dump(mode="json"),
            )
            == accepted
        )
        assert service.status(env.owner, original_grant)["revoked_at"] is not None
        with pytest.raises(ServiceError):
            env.memory.fetch(reader, UUID(forgotten))


def test_redacted_source_change_keeps_immutable_raw_provenance_even_when_selected_text_is_equal(
    env, conversation_source, custody
):
    service, source_id, _, _, _ = custody
    _, connector, operator, _, secret, config = conversation_source
    policy = CapturePolicy(
        format="mnemion-capture-policy-v2",
        preset="detailed",
        capture_mode="complete",
        retention="until_deleted",
        exclude_fields=["diagnostic"],
    )
    config.provider.capture_mode = "complete"
    config.provider.capture_policy = policy
    path = config.provider.path / "chat.jsonl"
    path.write_bytes(encoded("Same selected memory", diagnostic="private-one"))
    grant = approve(service, env.owner, connector, source_id, operator, policy)
    scope, before, checkpoint = scan(config)
    with running(create_app(env.db, env.embedder)) as url, Client(url, secret) as client:
        client.request(
            "POST",
            f"/v1/capture-grants/{grant}/pages",
            body=page(source_id, scope, *before).model_dump(mode="json"),
        )
        path.write_bytes(encoded("Same selected memory", diagnostic="private-two"))
        _, after, _ = scan(config, checkpoint)
        assert all(item.action == "upsert" for item in after)
        assert before[0].external_id == after[0].external_id
        assert before[0].memory.content == after[0].memory.content
        assert (
            before[0].memory.metadata["source_segment_sha256"]
            != after[0].memory.metadata["source_segment_sha256"]
        )
        accepted = client.request(
            "POST",
            f"/v1/capture-grants/{grant}/pages",
            body=page(source_id, scope, *after).model_dump(mode="json"),
        )
        assert all(row["outcome"] == "stored" for row in accepted["items"])
        assert before[0].revision != after[0].revision
        assert "private-" not in json.dumps([item.model_dump(mode="json") for item in after])
