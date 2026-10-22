"""The agent API and local preview expose the same explicit expiry boundary."""

from types import SimpleNamespace

import pytest

from mnemion import agent_control, desktop_capture_preview
from mnemion.connectors.capture_delivery import verify_grant
from mnemion.connectors.conversation_inbox import InboxError
from mnemion.sdk import Client
from mnemion.service.api import create_app
from service_tests.test_capture_custody import page
from service_tests.test_capture_retention import expiring as expiring, expiring_policy
from service_tests.test_clients import running
from service_tests.test_live_conversations import conversation_source as conversation_source


def test_agent_cleanup_observation_uses_the_same_scope_and_counts(
    env, conversation_source, expiring
):
    service, source_id, grant_id, _, scope, item = expiring
    service.page(conversation_source[2], grant_id, page(source_id, scope, item))
    with running(create_app(env.db, env.embedder)) as url, Client(url, env.token) as client:
        result = agent_control.execute(
            client,
            "capture.retention.status",
            {
                "parameters": {
                    "connector_id": str(conversation_source[1]),
                    "source_id": str(source_id),
                }
            },
        )["result"]
        assert result["pending_families"] == 1 and result["due_families"] == 0
        assert (
            result["semantics"] == "scheduled_cleanup"
            and result["backup_erasure"] == "not_included"
        )


def test_preview_describes_server_expiry_and_older_server_is_refused(tmp_path):
    policy = expiring_policy(7)
    producer, state = tmp_path / "producer", tmp_path / "private-state"
    producer.mkdir()
    state.mkdir()
    preview = desktop_capture_preview.preview(
        state,
        {
            "path": str(producer),
            "capture_mode": "messages",
            "capture_policy": policy.model_dump(mode="json"),
            "keep_accepted": True,
        },
    )
    assert preview["automatic_expiry"] == "server_scheduled" and preview["retention_days"] == 7
    assert preview["content_saved"] is False

    def request(method, path):
        assert (method, path) == ("GET", "/health/live")  # No grant lookup or delivery.
        return {"durable_capture": "v1"}

    with pytest.raises(InboxError, match="capture_server_upgrade_required"):
        verify_grant(
            SimpleNamespace(binding={"capture_policy": policy.model_dump(mode="json")}),
            SimpleNamespace(request=request),
        )
