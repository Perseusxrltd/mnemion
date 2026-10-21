"""Actual Codex producer files through the released mirror HTTP protocol."""

import json
from pathlib import Path
from uuid import UUID

import pytest

from mnemion.connectors.runner import sync
from mnemion.sdk import Client
from mnemion.service.api import create_app
from mnemion.service.connector_models import BindingInput
from mnemion.service.errors import ServiceError
from service_tests.test_clients import running as serve
from service_tests.test_live_conversations import (
    conversation_source as conversation_source,
    memories,
)


FIXTURE = Path(__file__).parent / "fixtures/codex-0.163"
MANIFEST = json.loads((FIXTURE / "manifest.json").read_text())


@pytest.mark.parametrize("mode", ["complete", "messages"])
def test_actual_codex_resume_delivers_once_and_respects_current_readers(
    env, conversation_source, mode
):
    service, connector, operator, reader, secret, config = conversation_source
    config.provider.capture_mode = mode
    full = (FIXTURE / "resumed.jsonl").read_bytes()
    selected = config.provider.path / "resumed.jsonl"
    selected.write_bytes(full[: MANIFEST["first_turn_bytes"]])
    (config.provider.path / "independent.jsonl").write_bytes(
        (FIXTURE / "independent.jsonl").read_bytes()
    )

    def current():
        scopes = service.scopes(env.owner, connector)["items"]
        assert len(scopes) == 2
        return [
            row for scope in scopes for row in memories(env, operator, reader, scope["space_id"])
        ]

    def spoken(rows):
        return "\n".join(row["content"] for row in rows if row["metadata"].get("projection"))

    with serve(create_app(env.db, env.embedder)) as url, Client(url, secret) as client:
        assert sync(config, client=client)["completed"]
        before = spoken(current())
        for index in (0, 2):
            for field in ("prompts", "replies"):
                assert before.count(MANIFEST[field][index]) == 1
        assert MANIFEST["prompts"][1] not in before

        with selected.open("ab") as stream:
            stream.write(full[MANIFEST["first_turn_bytes"] :])
        assert sync(config, client=client)["completed"]
        rows = current()
        text = spoken(rows)
        for field in ("prompts", "replies"):
            for message in MANIFEST[field]:
                assert text.count(message) == 1
        if mode == "messages":
            assert all(row["metadata"].get("projection") for row in rows)
            assert "environment_context" not in json.dumps(rows)
        else:
            assert any(not row["metadata"].get("projection") for row in rows)
        versions = {row["memory_id"]: row["version"] for row in rows}
        repeated = sync(config, client=client)
        assert repeated["completed"] and repeated["changed"] == 0
        assert {row["memory_id"]: row["version"] for row in current()} == versions

        service.binding(
            env.owner,
            connector,
            BindingInput(
                external_id="employee:reader",
                principal_id=reader.principal_id,
                role="reviewer",
            ),
            remove=True,
        )
        assert sync(config, client=client)["completed"]
        for identifier in versions:
            with pytest.raises(ServiceError):
                env.memory.fetch(reader, UUID(identifier))
