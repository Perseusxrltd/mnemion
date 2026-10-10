"""Explicit retrieval metrics and bounded uncertainty estimates for real cases."""

from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict

SCORER_VERSION = "mnemion-retrieval-2"


def ranking_metrics(ranked: list[str], relevant: dict[str, int], cutoff: int) -> dict:
    if not relevant:
        return {"recall": None, "precision": None, "ndcg": None, "mrr": None, "complete": None}
    seen, found, dcg, reciprocal = set(), set(), 0.0, 0.0
    for position, key in enumerate(ranked[:cutoff], 1):
        if key in seen:
            continue
        seen.add(key)
        grade = relevant.get(key, 0)
        if grade:
            found.add(key)
            dcg += (2**grade - 1) / math.log2(position + 1)
            if not reciprocal:
                reciprocal = 1 / position
    ideal = sum(
        (2**grade - 1) / math.log2(position + 1)
        for position, grade in enumerate(sorted(relevant.values(), reverse=True)[:cutoff], 1)
    )
    return {
        "recall": len(found) / len(relevant),
        "precision": len(found) / cutoff,
        "ndcg": dcg / ideal,
        "mrr": reciprocal,
        "complete": len(found) == len(relevant),
    }


def wilson(successes: int, total: int) -> list[float] | None:
    if not total:
        return None
    z, p = 1.959963984540054, successes / total
    denominator = 1 + z * z / total
    midpoint = (p + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0, midpoint - radius), min(1, midpoint + radius)]


def bootstrap_mean(values: list[float], *, resamples: int = 500) -> list[float] | None:
    if len(values) < 2:
        return None
    rng = random.Random(20261010)
    if min(values) == max(values):
        return [values[0], values[0]]
    draws = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(resamples))
    return [
        draws[int(0.025 * resamples)],
        draws[min(resamples - 1, math.ceil(0.975 * resamples) - 1)],
    ]


def percentile(values: list[float], quantile: float) -> float | None:
    return sorted(values)[max(0, math.ceil(len(values) * quantile) - 1)] if values else None


def summarize_results(results: list[dict], cutoffs: list[int]) -> dict:
    by_mode, by_category = defaultdict(list), defaultdict(list)
    for row in results:
        by_mode[row["mode"]].append(row)
        by_category[(row["mode"], row["category"])].append(row)

    def describe(rows, *, uncertainty):
        successful = [row for row in rows if row["status"] == "completed"]
        answerable = [row for row in successful if not row["unanswerable"]]
        metrics = {}
        for k in cutoffs:
            values = [row["metrics"][str(k)] for row in answerable]
            complete = sum(value["complete"] for value in values)
            recalls = [value["recall"] for value in values]
            metrics[str(k)] = {
                field: statistics.fmean(value[field] for value in values) if values else None
                for field in ("recall", "precision", "ndcg", "mrr")
            } | {
                "n": len(values),
                "complete": complete,
                "complete_rate": complete / len(values) if values else None,
                "complete_wilson95": wilson(complete, len(values)),
                "recall_bootstrap95": bootstrap_mean(recalls) if uncertainty else None,
            }
        context_rows = [row for row in answerable if row.get("context_recall") is not None]
        checked = sum(row.get("citations_checked", 0) for row in successful)
        invalid = sum(row.get("citations_invalid", 0) for row in successful)
        return {
            "cases": len(rows),
            "successful": len(successful),
            "failed": len(rows) - len(successful),
            "answerable": len(answerable),
            "unanswerable": sum(row["unanswerable"] for row in successful),
            "metrics": metrics,
            "context_recall": statistics.fmean(row["context_recall"] for row in context_rows)
            if context_rows
            else None,
            "context_complete": sum(row["context_complete"] for row in context_rows),
            "context_cases": len(context_rows),
            "citations_checked": checked,
            "citations_invalid": invalid,
            "citation_validity": (checked - invalid) / checked if checked else None,
            "latency_p50_ms": percentile([row["recall_ms"] for row in successful], 0.5),
            "latency_p95_ms": percentile([row["recall_ms"] for row in successful], 0.95),
            "context_tokens": sum(row.get("context_tokens", 0) for row in successful),
            "empty_results": sum(not row["ranking"] for row in successful),
        }

    return {
        "scorer_version": SCORER_VERSION,
        "modes": {mode: describe(rows, uncertainty=True) for mode, rows in sorted(by_mode.items())},
        "categories": [
            {"mode": mode, "category": category, **describe(rows, uncertainty=False)}
            for (mode, category), rows in sorted(by_category.items())
        ],
        "uncertainty": {
            "bootstrap_resamples": 500,
            "seed": 20261010,
            "method": "percentile bootstrap over successful answerable cases; Wilson interval for evidence completeness",
            "note": "Intervals describe this test set. Small samples, failed cases and a degenerate bootstrap do not establish population accuracy.",
        },
        "definitions": {
            "recall": "Fraction of labeled memory revisions retrieved at K.",
            "precision": "Distinct relevant memory revisions divided by K, even when fewer hits return.",
            "ndcg": "Graded gains (2^grade - 1), discounted by log2(rank + 1), normalized to the ideal top K.",
            "mrr": "Reciprocal rank of the first labeled relevant revision.",
            "context_recall": "Fraction of reference revisions cited in the bounded context; not proof that an excerpt answers the query.",
            "citation_validity": "Source hashes and Unicode spans checked against currently authorized evidence.",
            "latency": "End-to-end retrieval elapsed time, including model inference; excludes the optional separate context call.",
            "abstention": "Unanswerable cases have no retrieval-recall denominator. Zero hits alone is not a correct abstention.",
        },
        "answer_quality": "not_automatically_measured",
    }
