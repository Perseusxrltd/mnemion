"""Counterexamples for retrieval metric correctness."""

import math
from pathlib import Path
import runpy

import pytest


def test_ab_metrics_require_the_query_specific_document():
    module = runpy.run_path(str(Path(__file__).parent / "benchmarks/bench_ab_test.py"))
    wrong = ["NEEDLE_UNRELATED"]
    assert module["_recall_at_k"](wrong, 5, "NEEDLE_EXPECTED") == 0.0
    assert module["_mrr"](wrong, "NEEDLE_EXPECTED") == 0.0
    assert module["_mrr"](wrong + ["NEEDLE_EXPECTED"], "NEEDLE_EXPECTED") == 0.5
    assert module["_recall_at_k"](wrong + ["NEEDLE_EXPECTED"], 1, "NEEDLE_EXPECTED") == 0.0


def test_ndcg_accounts_for_unretrieved_relevant_documents_and_duplicate_results():
    module = runpy.run_path(str(Path(__file__).parent.parent / "benchmarks/longmemeval_bench.py"))
    ndcg = module["ndcg"]
    expected = 1 / (1 + 1 / math.log2(3))
    assert ndcg([0, 2], {"a", "b"}, ["a", "b", "irrelevant"], 2) == pytest.approx(expected)
    assert ndcg([0, 0], {"a", "b"}, ["a", "b"], 2) == pytest.approx(expected)
    assert ndcg([0, 1], {"a", "b"}, ["a", "b"], 2) == 1.0
    assert ndcg([], set(), [], 5) == 0.0
    assert ndcg([0], {"a"}, ["a"], 0) == 0.0
