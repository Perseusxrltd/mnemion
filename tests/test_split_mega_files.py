import json

import pytest

from mnemion import split_mega_files as smf


def test_load_known_people_falls_back_when_config_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(smf, "_KNOWN_NAMES_PATH", tmp_path / "missing.json")
    smf._KNOWN_NAMES_CACHE = None

    assert smf._load_known_people() == smf._FALLBACK_KNOWN_PEOPLE
    assert smf._load_username_map() == {}


def test_load_known_people_from_list_config(monkeypatch, tmp_path):
    config_path = tmp_path / "known_names.json"
    config_path.write_text(json.dumps(["Alice", "Ben"]))
    monkeypatch.setattr(smf, "_KNOWN_NAMES_PATH", config_path)
    smf._KNOWN_NAMES_CACHE = None

    assert smf._load_known_people() == ["Alice", "Ben"]
    assert smf._load_username_map() == {}


def test_load_known_people_from_dict_config(monkeypatch, tmp_path):
    config_path = tmp_path / "known_names.json"
    config_path.write_text(json.dumps({"names": ["Alice"], "username_map": {"jdoe": "John"}}))
    monkeypatch.setattr(smf, "_KNOWN_NAMES_PATH", config_path)
    smf._KNOWN_NAMES_CACHE = None

    assert smf._load_known_people() == ["Alice"]
    assert smf._load_username_map() == {"jdoe": "John"}


def test_extract_people_uses_username_map(monkeypatch, tmp_path):
    config_path = tmp_path / "known_names.json"
    config_path.write_text(json.dumps({"names": ["Alice"], "username_map": {"jdoe": "John"}}))
    monkeypatch.setattr(smf, "_KNOWN_NAMES_PATH", config_path)
    monkeypatch.setattr(smf, "KNOWN_PEOPLE", ["Alice"])
    smf._KNOWN_NAMES_CACHE = None

    people = smf.extract_people(["Working in /Users/jdoe/project\n"])
    assert "John" in people


def test_extract_people_detects_names_from_content(monkeypatch):
    monkeypatch.setattr(smf, "KNOWN_PEOPLE", ["Alice", "Ben"])
    people = smf.extract_people(["> Alice reviewed the change with Ben\n"])
    assert people == ["Alice", "Ben"]


def transcript_source(directory, *, timed=True):
    chunks = []
    for label in ("FIRST_FRAGMENT", "SECOND_FRAGMENT"):
        lines = ["Claude Code v1.0\n"]
        if timed:
            lines.append("⏺ 1:02 PM Friday, October 23, 2026\n")
        lines.append("> Repeated synthetic subject\n")
        lines.extend(f"{label} étude 日本語 {number}\n" for number in range(12))
        chunks.append("".join(lines))
    source = directory / "sessions.txt"
    source.write_text("".join(chunks), encoding="utf-8")
    return source, chunks


def test_colliding_session_names_preserve_every_fragment(tmp_path):
    source, chunks = transcript_source(tmp_path)
    paths = smf.split_file(source, tmp_path)
    assert len(paths) == len(set(paths)) == 2
    assert [path.read_text(encoding="utf-8") for path in paths] == chunks


def test_existing_output_is_never_overwritten(tmp_path):
    source, chunks = transcript_source(tmp_path)
    occupied = smf.split_file(source, tmp_path, dry_run=True)[0]
    occupied.write_text("EXISTING_OUTPUT", encoding="utf-8")
    paths = smf.split_file(source, tmp_path)
    assert occupied.read_text(encoding="utf-8") == "EXISTING_OUTPUT"
    assert occupied not in paths and len(set(paths)) == 2
    assert [path.read_text(encoding="utf-8") for path in paths] == chunks


def test_existing_backup_and_new_original_are_both_preserved(tmp_path, monkeypatch):
    source, _ = transcript_source(tmp_path, timed=False)
    original = source.read_bytes()
    older = source.with_suffix(".mega_backup")
    older.write_bytes(b"OLDER_BACKUP")
    monkeypatch.setattr("sys.argv", ["split", "--file", str(source)])
    smf.main()
    assert older.read_bytes() == b"OLDER_BACKUP"
    backups = [path for path in tmp_path.rglob("*.mega_backup") if path != older]
    assert len(backups) == 1 and backups[0].read_bytes() == original
    assert not source.exists()


def test_new_output_directory_is_created_only_when_applying(tmp_path):
    source, chunks = transcript_source(tmp_path, timed=False)
    output = tmp_path / "new" / "sessions"
    preview = smf.split_file(source, output, dry_run=True)
    assert len(set(preview)) == 2 and not output.exists()
    written = smf.split_file(source, output)
    assert written == preview
    assert [path.read_text(encoding="utf-8") for path in written] == chunks


def test_a_racing_output_writer_keeps_its_file(tmp_path, monkeypatch):
    from pathlib import Path

    source, chunks = transcript_source(tmp_path)
    occupied = smf.split_file(source, tmp_path, dry_run=True)[0]
    original_open = Path.open
    raced = False

    def racing_open(path, mode="r", *args, **kwargs):
        nonlocal raced
        if path == occupied and mode == "x" and not raced:
            raced = True
            with original_open(path, "w", encoding="utf-8") as stream:
                stream.write("RACING_WRITER")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", racing_open)
    paths = smf.split_file(source, tmp_path)
    assert raced and occupied.read_text(encoding="utf-8") == "RACING_WRITER"
    assert occupied not in paths
    assert [path.read_text(encoding="utf-8") for path in paths] == chunks


@pytest.mark.parametrize("after_move", [False, True])
def test_archive_failures_never_remove_the_only_original(tmp_path, monkeypatch, after_move):
    from pathlib import Path

    source, _ = transcript_source(tmp_path)
    original = source.read_bytes()
    original_rename = Path.rename

    def interrupted(path, target):
        if path == source:
            if after_move:
                original_rename(path, target)
            raise OSError("synthetic archive failure")
        return original_rename(path, target)

    monkeypatch.setattr(Path, "rename", interrupted)
    monkeypatch.setattr("sys.argv", ["split", "--file", str(source)])
    with pytest.raises(OSError, match="synthetic archive failure"):
        smf.main()
    backups = list(tmp_path.rglob("*.mega_backup"))
    if after_move:
        assert not source.exists()
        assert len(backups) == 1 and backups[0].read_bytes() == original
    else:
        assert source.read_bytes() == original and not backups
        assert not list(tmp_path.glob(".mnemion-split-backup-*"))


def test_output_failure_leaves_the_original_unarchived(tmp_path, monkeypatch):
    from pathlib import Path

    source, chunks = transcript_source(tmp_path)
    original = source.read_bytes()
    preview = smf.split_file(source, tmp_path, dry_run=True)
    original_open = Path.open

    def failing_open(path, mode="r", *args, **kwargs):
        if path == preview[1] and mode == "x":
            raise OSError("synthetic output failure")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)
    monkeypatch.setattr("sys.argv", ["split", "--file", str(source)])
    with pytest.raises(OSError, match="synthetic output failure"):
        smf.main()
    assert source.read_bytes() == original and not list(tmp_path.rglob("*.mega_backup"))
    assert preview[0].read_text(encoding="utf-8") == chunks[0]
    assert not preview[1].exists()


def test_dry_run_leaves_source_backups_and_output_directory_unchanged(tmp_path, monkeypatch):
    source, _ = transcript_source(tmp_path)
    older = source.with_suffix(".mega_backup")
    older.write_bytes(b"OLDER_BACKUP")
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    output = tmp_path / "future-output"
    monkeypatch.setattr(
        "sys.argv", ["split", "--file", str(source), "--output-dir", str(output), "--dry-run"]
    )
    smf.main()
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before
    assert not output.exists()
