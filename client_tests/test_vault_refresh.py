import json
from pathlib import Path

import pytest
import yaml

from mnemion import vault_refresh as vault
from mnemion.wiki.obsidian_export import export_compiled_wiki_to_obsidian


MANIFEST = ".mnemion-obsidian-manifest.json"


@pytest.mark.parametrize(
    "name", [".git/config.md", ".mnemion-refresh.lock", "run.exe", ".obsidian/secret.md"]
)
def test_export_bundle_cannot_write_internal_or_executable_files(tmp_path, name):
    import io
    import zipfile

    from mnemion.vault_client import sync_bundle

    output = io.BytesIO()
    text = vault.BEGIN + "\nUntrusted export\n" + vault.END
    manifest = {
        "format_version": 2,
        "completed": True,
        "files": [name],
        "entries": {name: {"file_sha256": vault.digest(text)}},
    }
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(name, text)
        archive.writestr(MANIFEST, json.dumps(manifest))
    target = tmp_path / "uncreated-vault"
    with pytest.raises(vault.VaultRefreshError):
        sync_bundle(output.getvalue(), target)
    assert not target.exists()


def note(text="Original evidence", identity="memory-one"):
    return f"---\nid: {identity}\nmnemion_managed: true\n---\n# A memory\n\n{text}\n"


def test_annotations_yaml_settings_and_stable_links_survive_refresh(tmp_path):
    files = {"Wings/Original/one.md": note(), "Mnemion.md": "[[Wings/Original/one|One]]\n"}
    assert vault.refresh(tmp_path, files, {"synced_at": "first"}, MANIFEST)["completed"]
    path = tmp_path / "Wings/Original/one.md"
    personal = "\r\nMy annotation: café, 漢字, [[My own note]].\r\n"
    path.write_bytes(path.read_bytes() + personal.encode())
    (tmp_path / ".obsidian").mkdir()
    settings = tmp_path / ".obsidian/graph.json"
    settings.write_text('{"custom":true}')
    unmanaged = tmp_path / "My own note.md"
    unmanaged.write_text("Do not replace")
    result = vault.refresh(
        tmp_path,
        {
            "Wings/Renamed/one.md": note("Corrected evidence"),
            "Mnemion.md": "[[Wings/Renamed/one|One]]\n",
        },
        {"synced_at": "second"},
        MANIFEST,
    )
    assert result["completed"]
    rendered = path.read_bytes().decode()
    assert rendered.endswith(personal)
    assert "Corrected evidence" in rendered and "Original evidence" not in rendered
    assert yaml.safe_load(rendered.split("---", 2)[1])["id"] == "memory-one"
    assert "[[Wings/Original/one|One]]" in (tmp_path / "Mnemion.md").read_text()
    assert not (tmp_path / "Wings/Renamed/one.md").exists()
    assert settings.read_text() == '{"custom":true}'
    assert unmanaged.read_text() == "Do not replace"


def test_edited_generated_section_and_unknown_legacy_note_require_conflict_review(tmp_path):
    vault.refresh(tmp_path, {"one.md": note()}, {"synced_at": "first"}, MANIFEST)
    path = tmp_path / "one.md"
    path.write_text(
        path.read_text().replace("Original evidence", "Human correction inside generated text")
    )
    original = path.read_bytes()
    result = vault.refresh(
        tmp_path, {"one.md": note("New canonical evidence")}, {"synced_at": "second"}, MANIFEST
    )
    assert not result["completed"] and result["conflicts"][0]["path"] == "one.md"
    assert path.read_bytes() == original
    manifest = json.loads((tmp_path / MANIFEST).read_text())
    assert manifest["synced_at"] == "first" and manifest["pending_synced_at"] == "second"
    proposed = next((tmp_path / ".mnemion-conflicts").glob("*.proposed.md"))
    assert "New canonical evidence" in proposed.read_text()
    path.write_bytes(proposed.read_bytes())  # Explicitly accepting the proposal.
    assert vault.refresh(
        tmp_path, {"one.md": note("New canonical evidence")}, {"synced_at": "third"}, MANIFEST
    )["completed"]

    legacy = tmp_path / "Legacy.md"
    legacy.write_text("Generated before hashes existed\nMy personal addition\n")
    saved = json.loads((tmp_path / MANIFEST).read_text())
    saved["files"].append("Legacy.md")
    (tmp_path / MANIFEST).write_text(json.dumps(saved))
    result = vault.refresh(tmp_path, {"one.md": note("New canonical evidence")}, {}, MANIFEST)
    assert legacy.exists()
    assert any(c["reason"] == "withdrawal_needs_review" for c in result["conflicts"])


def test_withdrawal_removes_generated_content_and_keeps_personal_text(tmp_path):
    vault.refresh(tmp_path, {"one.md": note(), "two.md": note(identity="two")}, {}, MANIFEST)
    path = tmp_path / "one.md"
    path.write_bytes(path.read_bytes() + b"My personal follow-up.\r\n")
    result = vault.refresh(tmp_path, {}, {}, MANIFEST)
    assert result["completed"] and result["pruned_files"] == 1
    assert result["detached_annotations"] == ["one.md"]
    assert "Original evidence" not in path.read_text()
    assert path.read_bytes().endswith(b"My personal follow-up.\r\n")
    assert not (tmp_path / "two.md").exists()
    assert vault.refresh(tmp_path, {}, {}, MANIFEST)["completed"]
    assert path.exists()


def test_interrupted_refresh_recovers_with_current_content(tmp_path, monkeypatch):
    original = {"first.md": note(identity="first"), "second.md": note(identity="second")}
    vault.refresh(tmp_path, original, {"synced_at": "first"}, MANIFEST)
    first = tmp_path / "first.md"
    first.write_bytes(first.read_bytes() + b"Keep this annotation\n")
    previous_manifest = (tmp_path / MANIFEST).read_bytes()
    replace = vault.os.replace

    def fail_second(source, target):
        if Path(target) == tmp_path / "second.md":
            raise OSError("Injected interruption")
        return replace(source, target)

    monkeypatch.setattr(vault.os, "replace", fail_second)
    with pytest.raises(OSError):
        vault.refresh(
            tmp_path,
            {rel: text.replace("Original", "Intermediate") for rel, text in original.items()},
            {"synced_at": "second"},
            MANIFEST,
        )
    assert (tmp_path / MANIFEST).read_bytes() == previous_manifest
    assert (tmp_path / (MANIFEST + ".pending")).exists()
    monkeypatch.setattr(vault.os, "replace", replace)
    result = vault.refresh(
        tmp_path,
        {rel: text.replace("Original", "Latest") for rel, text in original.items()},
        {"synced_at": "third"},
        MANIFEST,
    )
    assert result["completed"] and first.read_text().endswith("Keep this annotation\n")
    assert "Latest evidence" in first.read_text()
    assert "Latest evidence" in (tmp_path / "second.md").read_text()
    assert not (tmp_path / (MANIFEST + ".pending")).exists()


def test_paths_are_validated_before_any_changes(tmp_path):
    outside = tmp_path.parent / "outside-note.md"
    outside.write_text("Do not touch")
    for invalid in (
        "../outside-note.md",
        "C:/outside-note.md",
        ".obsidian/graph.json",
        "a\\..\\outside-note.md",
        ".OBSIDIAN/app.json",
        "notes/CON.md",
        "notes/COM¹.txt",
        "notes/name.md.",
        "notes/../outside-note.md",
        "notes//one.md",
    ):
        with pytest.raises(vault.VaultRefreshError):
            vault.refresh(tmp_path, {invalid: "bad", "valid.md": "new"}, {}, MANIFEST)
        assert not (tmp_path / "valid.md").exists()
    link = tmp_path / "link.md"
    link.symlink_to(outside)
    with pytest.raises(vault.VaultRefreshError):
        vault.refresh(tmp_path, {"link.md": "bad"}, {}, MANIFEST)
    assert outside.read_text() == "Do not touch"
    with pytest.raises(vault.VaultRefreshError, match="collision"):
        vault.refresh(tmp_path, {"One.md": "a", "one.md": "b"}, {}, MANIFEST)
    with pytest.raises(vault.VaultRefreshError, match="collision"):
        vault.refresh(tmp_path, {"café.md": "a", "cafe\u0301.md": "b"}, {}, MANIFEST)


def test_compiled_wiki_export_preserves_annotations_and_live_withdrawal(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    source = wiki / "one.md"
    source.write_text(note())
    mirror = tmp_path / "mirror"
    export_compiled_wiki_to_obsidian(wiki, mirror)
    output = mirror / "_Mnemion/Compiled Wiki/one.md"
    output.write_bytes(output.read_bytes() + b"My local wiki annotation\n")
    source.write_text(note("New wiki text"))
    assert export_compiled_wiki_to_obsidian(wiki, mirror)["completed"]
    assert "New wiki text" in output.read_text()
    assert "My local wiki annotation" in output.read_text()
    source.write_text("---\ntrust_status: quarantined\n---\nPrivate text\n")
    assert export_compiled_wiki_to_obsidian(wiki, mirror)["completed"]
    assert "New wiki text" not in output.read_text()
    assert "My local wiki annotation" in output.read_text()
