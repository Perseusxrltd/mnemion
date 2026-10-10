from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from mnemion.service.api import create_app
from mnemion.service import knowledge
from mnemion.service.knowledge import KnowledgeInput, KnowledgeService
from mnemion.service.errors import ServiceError
from mnemion.service.models import MemoryInput, RevisionInput, ReviewInput
from service_tests.test_connectors import connected as connected
from service_tests.test_connectors import ingest, item


def test_wiki_graph_curation_and_citations_use_current_source_revisions(env):
    first = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(
            content="Backups stay for thirty days.",
            subject="Billing",
            metadata={"entities": ["Postgres"]},
        ),
        "first",
    )
    second = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="Backups stay for thirty days.", subject="Billing"),
        "second",
    )
    service = KnowledgeService(env.db)
    command = KnowledgeInput(space_ids=[env.space])
    initial = service.build(env.owner, command)
    assert len(initial["memories"]) == 2 and not initial["truncated"]
    assert any(
        node["kind"] == "entity" and node["label"] == "Postgres" for node in initial["nodes"]
    )
    assert any(finding["kind"] == "exact_duplicate" for finding in initial["findings"])
    assert first["memory_id"] in initial["markdown"]
    env.memory.revise(
        env.owner,
        UUID(first["memory_id"]),
        RevisionInput(
            content="Backups now stay for sixty days.",
            expected_version=1,
            reason="New retention policy",
        ),
        "revised",
    )
    current = service.build(env.owner, command)
    assert current["fingerprint"] != initial["fingerprint"]
    assert "sixty days" in current["markdown"]
    assert not any(finding["kind"] == "exact_duplicate" for finding in current["findings"])
    env.memory.review(
        env.owner,
        UUID(second["memory_id"]),
        ReviewInput(expected_version=1, state="quarantined", reason="Needs review"),
    )
    assert len(service.build(env.owner, command)["memories"]) == 1
    with TestClient(create_app(env.db, env.embedder)) as client:
        response = client.post(
            "/v1/knowledge",
            headers={"Authorization": "Bearer " + env.token},
            json={"all_accessible": True, "subject": "Billing"},
        )
        assert response.status_code == 200
        assert response.json()["memories"][0]["evidence"]["source_revision_id"]


def test_knowledge_rechecks_revocation_after_rendering_and_never_infers_private_entities(
    env, connected, monkeypatch
):
    connector, connection, space, operator, identities = connected
    saved = ingest(connector, operator, space, item(text="Company billing decision"))
    private = env.memory.save(
        env.owner, env.space, MemoryInput(content="OWNER_ONLY", subject="Secret launch"), "private"
    )
    service = KnowledgeService(env.db)
    command = KnowledgeInput(all_accessible=True)
    reader = identities["reader"][0]
    assert "Secret launch" not in str(service.build(reader, command))
    original = knowledge.render

    def revoke(*args):
        result = original(*args)
        connector.suspend(env.owner, space, "operator_paused")
        return result

    monkeypatch.setattr(knowledge, "render", revoke)
    with pytest.raises(ServiceError) as exc:
        service.build(reader, command)
    assert exc.value.code == "knowledge_changed"
    monkeypatch.setattr(knowledge, "render", original)
    assert service.build(reader, command)["nodes"] == []
    assert len(service.build(env.owner, command)["memories"]) == 1
    assert saved["items"][0]["memory_id"] != private["memory_id"]


def test_knowledge_marks_partial_views_and_treats_subject_filters_as_literals(env):
    for i in range(3):
        env.memory.save(
            env.owner,
            env.space,
            MemoryInput(content=f"Evidence {i}", subject="100%_literal"),
            f"note-{i}",
        )
    service = KnowledgeService(env.db)
    limited = service.build(env.owner, KnowledgeInput(space_ids=[env.space], limit=1))
    assert limited["truncated"] and "partial" in limited["markdown"]
    assert (
        len(
            service.build(env.owner, KnowledgeInput(space_ids=[env.space], subject="%_"))[
                "memories"
            ]
        )
        == 3
    )
    assert (
        service.build(env.owner, KnowledgeInput(space_ids=[env.space], subject="absent%"))[
            "memories"
        ]
        == []
    )
