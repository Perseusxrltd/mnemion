"""Evaluation must not award perfect ranking to incomplete evidence or ingest labels."""

import pytest
from types import SimpleNamespace

from benchmarks.service_retrieval import evaluate, retrieval_metrics, session_documents


def test_partial_and_duplicate_evidence_do_not_inflate_retrieval_scores():
    partial = retrieval_metrics(["one", "irrelevant"], {"one", "two"}, 2)
    assert partial["recall"] == 0.5
    assert partial["ndcg"] == pytest.approx(0.6131471927654584)
    assert partial["complete"] is False
    duplicate = retrieval_metrics(["one", "one"], {"one", "two"}, 2)
    assert duplicate == partial
    assert retrieval_metrics(["irrelevant"], set(), 5)["recall"] is None


def test_session_ingestion_keeps_all_speakers_and_bounds_every_part():
    sessions = [
        [
            {"role": "user", "content": "é" * 50000},
            {"role": "assistant", "content": "Source evidence retained."},
        ]
    ]
    parts = session_documents(sessions, ["session-a"], ["2024/01/01"])
    assert len(parts) == 2
    assert all(len(part["content"]) <= 48000 for part in parts)
    text = "".join(part["content"] for part in parts)
    assert "é" * 50000 in text and "[user]" in text and "[assistant]" in text
    assert text.endswith("Source evidence retained.")


def test_abstention_cases_with_related_session_ids_are_excluded_from_recall(tmp_path):
    client = SimpleNamespace(
        search=lambda *a, **k: SimpleNamespace(warnings=[], hits=[]),
        request=lambda *a, **k: {},
    )
    row = {
        "question_id": "related_but_unanswerable_abs",
        "question_type": "knowledge-update",
        "answer_session_ids": ["related-session"],
        "haystack_session_ids": ["related-session"],
        "question": "Which unpublished value did I choose?",
        "question_date": "2024/01/01",
    }
    result = evaluate(client, row, {"receipts": [], "space_id": "fixture"}, tmp_path, 1)
    assert result["unanswerable"] is True
    assert all(metric["recall"] is None for metric in result["metrics"].values())
    row["question_id"] = "answerable"
    row["answer_session_ids"] = ["missing-session"]
    with pytest.raises(ValueError, match="no gold session"):
        evaluate(client, row, {"receipts": []}, tmp_path, 1)
