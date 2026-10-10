import io
import json
import re
import zipfile
from uuid import UUID

import pytest

from mnemion.service.errors import ServiceError
from mnemion.service.export import ExportService, NotePaths
from mnemion.service.models import (
    ExportInput,
    GrantInput,
    KeyInput,
    MemoryInput,
    PrincipalInput,
    RevisionInput,
    ReviewInput,
    SpaceInput,
)
from mnemion.vault_client import sync_bundle
from mnemion.vault_refresh import VaultRefreshError


def test_export_does_not_return_content_deleted_while_rendering(env, monkeypatch):
    from mnemion.service import export

    saved = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="WITHDRAW_DURING_RENDER", subject="Review"),
        "withdrawn",
    )
    original = export.render

    def withdraw(snapshot):
        files = original(snapshot)
        env.memory.forget(
            env.owner, UUID(saved["memory_id"]), expected_version=1, key="withdraw-during-render"
        )
        return files

    monkeypatch.setattr(export, "render", withdraw)
    with pytest.raises(ServiceError) as exc:
        ExportService(env.db).export(env.owner, ExportInput(space_ids=[env.space]))
    assert exc.value.code == "export_changed"


def unzip(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name).decode() for name in archive.namelist()}


def test_service_obsidian_export_scope_history_links_and_refresh(env, tmp_path):
    exports = ExportService(env.db)
    saved = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="The billing project uses Postgres.", subject="Projet mémoire"),
        "export",
    )
    memory = UUID(saved["memory_id"])
    env.memory.revise(
        env.owner,
        memory,
        RevisionInput(
            content="The billing project now uses two Postgres replicas.",
            subject="Projet mémoire",
            expected_version=1,
            reason="Capacity",
        ),
        "replicas",
    )
    hidden = env.memory.save(
        env.owner,
        env.space,
        MemoryInput(content="QUARANTINED_SECRET", metadata={"entities": ["SECRET_ENTITY"]}),
        "hidden",
    )
    env.memory.review(
        env.owner,
        UUID(hidden["memory_id"]),
        ReviewInput(expected_version=1, state="quarantined", reason="Review"),
    )
    other = env.identities.create_space(env.owner, SpaceInput(name="Other private space"))
    env.memory.save(
        env.owner, UUID(other["id"]), MemoryInput(content="UNSELECTED_SPACE_SECRET"), "other"
    )
    data = exports.export(env.owner, ExportInput(space_ids=[env.space]))
    files = unzip(data)
    content = "\n".join(files.values())
    assert "QUARANTINED_SECRET" not in content and "SECRET_ENTITY" not in content
    assert "UNSELECTED_SPACE_SECRET" not in content
    assert "uses Postgres." in content and "two Postgres replicas" in content
    manifest = json.loads(files[".mnemion-obsidian-manifest.json"])
    main_path = manifest["id_paths"][str(memory)]
    assert main_path.startswith("Wings/") and "/Memories/Projet mémoire-" in main_path
    for text in files.values():
        if not text.startswith("---"):
            continue
        for link in re.findall(r"\[\[([^\]]+)\]\]", text):
            destination = link.split("|", 1)[0].split("#", 1)[0]
            assert destination + ".md" in files, link
    vault = tmp_path / "vault"
    assert sync_bundle(data, vault)["completed"]
    path = vault / main_path
    annotation = b"Personal note: discuss this at the next team meeting.\r\n"
    path.write_bytes(path.read_bytes() + annotation)
    env.memory.revise(
        env.owner,
        memory,
        RevisionInput(
            content="The billing project now uses three Postgres replicas.",
            subject="Renamed project",
            expected_version=2,
            reason="More capacity",
        ),
        "third",
    )
    assert sync_bundle(exports.export(env.owner, ExportInput(space_ids=[env.space])), vault)[
        "completed"
    ]
    assert path.read_bytes().endswith(annotation)
    assert "three Postgres replicas" in path.read_text()
    assert "# Renamed project" in path.read_text()
    refreshed = json.loads((vault / ".mnemion-obsidian-manifest.json").read_text())
    assert refreshed["id_paths"][str(memory)] == main_path
    assert not list((vault / "Wings").rglob("Renamed project-*.md"))
    env.memory.forget(env.owner, memory, expected_version=3, key="withdraw-export")
    result = sync_bundle(exports.export(env.owner, ExportInput(space_ids=[env.space])), vault)
    assert result["completed"] and main_path in result["detached_annotations"]
    assert path.read_bytes().endswith(annotation) and "Postgres replicas" not in path.read_text()
    assert not list((vault / "_Mnemion/Sources").glob("*.md"))


def test_export_requires_each_space_grant_and_review_role(env):
    principal = env.identities.create_principal(env.owner, PrincipalInput(name="Reader"))
    key = env.identities.create_key(env.owner, UUID(principal["id"]), KeyInput(name="Reader"))
    reader = env.db.authenticate(key["api_key"])
    exports = ExportService(env.db)
    with pytest.raises(ServiceError) as error:
        exports.export(reader, ExportInput(space_ids=[env.space]))
    assert error.value.status == 404
    env.identities.grant(env.owner, env.space, reader.principal_id, GrantInput(role="reader"))
    assert exports.export(reader, ExportInput(space_ids=[env.space]))
    with pytest.raises(ServiceError) as error:
        exports.export(reader, ExportInput(space_ids=[env.space], review=True))
    assert error.value.status == 403


def test_truncated_export_fails_before_creating_a_vault(env, tmp_path):
    data = ExportService(env.db).export(env.owner, ExportInput(space_ids=[env.space]))
    with pytest.raises(VaultRefreshError):
        sync_bundle(data[:-50], tmp_path / "vault")
    assert not (tmp_path / "vault").exists()


def test_obsidian_filenames_resolve_identifier_and_windows_case_collisions():
    paths = NotePaths()
    first = paths.path("Memories", "Same title", "12345678-1234-4111-8111-111111111111")
    second = paths.path("Memories", "same title", "12345678-1234-4222-8222-222222222222")
    assert first.casefold() != second.casefold()
    assert paths.path("Memories", "Changed title", "12345678-1234-4111-8111-111111111111") == first
    assert all("/" not in p.removeprefix("Memories/") for p in (first, second))
