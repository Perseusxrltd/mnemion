import json

from mnemion.corpus_origin import CorpusOriginResult, detect_origin_heuristic, persist_origin
from mnemion.project_scanner import discover_entities, scan


def test_corpus_origin_detects_ai_dialogue_and_persists(tmp_path):
    result = detect_origin_heuristic(
        [
            "User: remind Claude that Mnemion stores memories.",
            "Assistant: I will search the Anaktoron first.",
            "Claude Code session_id=abc123",
        ]
    )

    assert result.likely_ai_dialogue is True
    assert result.primary_platform == "claude"
    assert "Claude" in result.agent_persona_names

    path = persist_origin(tmp_path, result)
    assert path == tmp_path / ".mnemion" / "origin.json"
    assert json.loads(path.read_text())["likely_ai_dialogue"] is True


def test_project_scanner_prefers_manifest_entities(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "mnemion-test-app"\n')

    projects, people = scan(tmp_path)

    assert "mnemion-test-app" in [p.name for p in projects]
    assert people == []


def test_discover_entities_keeps_agent_personas_out_of_people(tmp_path):
    (tmp_path / "notes.md").write_text(("Claude said it would search first. He replied.\n" * 8))
    origin = CorpusOriginResult(
        likely_ai_dialogue=True,
        confidence=0.9,
        primary_platform="claude",
        user_name=None,
        agent_persona_names=["Claude"],
        evidence=[],
    )

    detected = discover_entities(tmp_path, corpus_origin=origin)

    assert "Claude" not in [e["name"] for e in detected["people"]]
    assert "Claude" in [e["name"] for e in detected["agent_personas"]]
