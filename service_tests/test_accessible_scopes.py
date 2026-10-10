import io
import json
import zipfile
from uuid import UUID

import psycopg
import pytest
from pydantic import ValidationError

from mnemion.service.connector_models import ScopeInput, utc_now
from mnemion.service.export import ExportService
from mnemion.service.models import ContextInput, ExportInput, MemoryInput, RecallInput
from mnemion.service.retrieval import RetrievalService
from mnemion.vault_client import sync_bundle
from service_tests.test_connectors import connected as connected
from service_tests.test_connectors import ingest, item


def test_global_recall_and_vault_refresh_use_current_permissions(env, connected, tmp_path):
    service, connection, first, operator, identities = connected
    first_result = ingest(service, operator, first, item(text="PRIVATE_FIRST billing decision"))
    second = UUID(
        service.refresh_scope(
            operator,
            connection,
            ScopeInput(
                external_id="another-file",
                name="Another file",
                members=["U_reader", "U_reviewer"],
                observed_at=utc_now(),
            ),
        )["space_id"]
    )
    ingest(service, operator, second, item(text="Visible billing procedure"))
    env.memory.save(
        env.owner, env.space, MemoryInput(content="OWNER_ONLY billing plan"), "owner-private"
    )
    reader = identities["reader"][0]
    recall = RetrievalService(env.db, env.embedder)
    query = RecallInput(query="billing", all_accessible=True, mode="lexical")
    result = recall.recall(reader, query)
    assert len(result["hits"]) == 2 and result["index"]["eligible_records"] == 2
    assert len(recall.recall(env.owner, query)["hits"]) == 1
    assert recall.recall(identities["outsider"][0], query)["hits"] == []
    exported = ExportService(env.db)
    command = ExportInput(all_accessible=True)
    archive = exported.export(reader, command)
    vault = tmp_path / "Shared readable vault"
    assert sync_bundle(archive, vault)["completed"]
    manifest = json.loads((vault / ".mnemion-obsidian-manifest.json").read_text())
    assert manifest["scope"]["all_accessible"] and manifest["scope"]["principal_id"] == str(
        reader.principal_id
    )
    memory_id = first_result["items"][0]["memory_id"]
    note = next(
        path
        for path in vault.rglob("*.md")
        if memory_id in path.read_text() and "PRIVATE_FIRST" in path.read_text()
    )
    note.write_bytes(note.read_bytes() + b"\nMy retained annotation.\r\n")
    with psycopg.connect(env.admin_dsn) as conn:
        conn.execute(
            "UPDATE mnemion.connector_scopes SET access_valid_until=now()-interval '1 second' WHERE space_id=%s",
            (first,),
        )
    result = recall.recall(reader, query)
    assert len(result["hits"]) == 1 and result["index"]["eligible_records"] == 1
    context = recall.context(
        reader, ContextInput(query="billing", all_accessible=True, mode="lexical")
    )
    assert "PRIVATE_FIRST" not in context["text"] and "OWNER_ONLY" not in context["text"]
    archive = exported.export(reader, command)
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert b"PRIVATE_FIRST" not in b"\n".join(z.read(path) for path in z.namelist())
    assert sync_bundle(archive, vault)["completed"]
    assert note.read_bytes().endswith(b"My retained annotation.\r\n")
    assert all("PRIVATE_FIRST" not in path.read_text() for path in vault.rglob("*.md"))


def test_scope_selection_is_explicit_and_supports_more_than_twenty_sources(env, connected):
    service, connection, first, operator, identities = connected
    spaces = [first]
    for index in range(21):
        spaces.append(
            UUID(
                service.refresh_scope(
                    operator,
                    connection,
                    ScopeInput(
                        external_id=f"file-{index}",
                        name=f"File {index}",
                        members=["U_reader"],
                        observed_at=utc_now(),
                    ),
                )["space_id"]
            )
        )
    result = RetrievalService(env.db, env.embedder).recall(
        identities["reader"][0], RecallInput(query="billing", space_ids=spaces, mode="lexical")
    )
    assert result["hits"] == []
    with pytest.raises(ValidationError):
        RecallInput(query="billing")
    with pytest.raises(ValidationError):
        RecallInput(query="billing", space_ids=[first], all_accessible=True)
