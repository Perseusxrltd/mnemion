import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path for local imports
sys.path.append(str(Path(__file__).parent.parent))

from mnemion.hybrid_searcher import HybridSearcher


def run_benchmark():
    hybrid_engine = HybridSearcher()

    eval_file = Path(__file__).parent / "gold_standard.json"
    with open(eval_file, "r") as f:
        eval_set = json.load(f)

    results = []

    print(f"Executing formal benchmark against {len(eval_set)} targets...")

    for item in eval_set:
        query = item["query"]
        expected = item["expected_id"]

        # Vector (Raw Chroma Query)
        v_results = hybrid_engine.collection.query(query_texts=[query], n_results=10)
        v_ids = v_results["ids"][0]
        v_rank = v_ids.index(expected) + 1 if expected in v_ids else 0

        # Hybrid (Our Fused Engine)
        h_results = hybrid_engine.search(query, n_results=10)
        h_ids = [r["id"] for r in h_results]
        h_rank = h_ids.index(expected) + 1 if expected in h_ids else 0

        results.append(
            {
                "query": query,
                "category": item["category"],
                "expected_id": expected,
                "vector_rank": v_rank,
                "hybrid_rank": h_rank,
                "vector_rr": 1.0 / v_rank if v_rank > 0 else 0,
                "hybrid_rr": 1.0 / h_rank if h_rank > 0 else 0,
            }
        )

    # Metrics
    v_mrr = sum(r["vector_rr"] for r in results) / len(results)
    h_mrr = sum(r["hybrid_rr"] for r in results) / len(results)
    v_hit1 = sum(1 for r in results if r["vector_rank"] == 1) / len(results)
    h_hit1 = sum(1 for r in results if r["hybrid_rank"] == 1) / len(results)

    # Generate Professional Report
    report = []
    report.append("# Retrieval Fidelity Benchmark Report")
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    report.append("## Overview")
    report.append(
        "This report compares the baseline Semantic Retrieval (ChromaDB) with the Hybrid Retrieval Protocol (FTS5 + RRF)."
    )
    report.append("")
    report.append("## Summary Metrics")
    report.append("| Metric | Vector (Baseline) | Hybrid (Fused) | Improvement |")
    report.append("|---|---|---|---|")
    report.append(
        f"| MRR (Mean Reciprocal Rank) | {v_mrr:.4f} | {h_mrr:.4f} | +{((h_mrr / v_mrr) - 1) * 100 if v_mrr > 0 else 100:.1f}% |"
    )
    report.append(
        f"| Hit@1 Accuracy | {v_hit1 * 100:.1f}% | {h_hit1 * 100:.1f}% | +{(h_hit1 - v_hit1) * 100:.1f}% |"
    )
    report.append("")
    report.append("## Detailed Analysis")
    report.append("| Query | Category | Vector Rank | Hybrid Rank |")
    report.append("|---|---|---|---|")
    for r in results:
        v_str = str(r["vector_rank"]) if r["vector_rank"] > 0 else "MISS"
        h_str = str(r["hybrid_rank"]) if r["hybrid_rank"] > 0 else "MISS"
        report.append(f"| `{r['query']}` | {r['category']} | {v_str} | {h_str} |")

    report_path = Path(__file__).parent / "BENCHMARK_RESULTS.md"
    with open(report_path, "w") as f:
        f.write("\n".join(report))

    print(f"Benchmark complete. Report generated at {report_path}")


if __name__ == "__main__":
    run_benchmark()
