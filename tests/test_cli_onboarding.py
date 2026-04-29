import json
from pathlib import Path

from mnemion.corpus_origin import detect_corpus_origin, save_origin_metadata
from mnemion.miner import scan_project


def test_detect_corpus_origin_project_files(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")

    result = detect_corpus_origin(tmp_path)

    assert result["origin_type"] == "project_files"
    assert result["file_count"] == 2


def test_detect_corpus_origin_slack_like(tmp_path):
    (tmp_path / "channel.json").write_text(
        json.dumps([{"type": "message", "user": "U1", "text": "hello"}]),
        encoding="utf-8",
    )

    result = detect_corpus_origin(tmp_path)

    assert result["origin_type"] == "slack_like_chat"


def test_save_origin_metadata(tmp_path):
    target = tmp_path / ".mnemion" / "origin.json"
    result = save_origin_metadata(target, {"origin_type": "mixed"})

    assert target.exists()
    assert json.loads(target.read_text())["origin_type"] == "mixed"
    assert result == target


def test_generated_mnemion_files_are_excluded_from_scan(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hello')\n" * 20, encoding="utf-8")
    (tmp_path / "entities.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".mnemion").mkdir()
    (tmp_path / ".mnemion" / "origin.json").write_text("{}", encoding="utf-8")

    files = [Path(p).relative_to(tmp_path).as_posix() for p in scan_project(str(tmp_path))]

    assert files == ["src/app.py"]
