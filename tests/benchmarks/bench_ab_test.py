#!/usr/bin/env python3
"""
bench_ab_test.py — A/B Benchmark: Raw vs Groomed vs Hybrid Search

Answers the question: Does SIGReg grooming and hybrid search actually
improve retrieval quality compared to raw ChromaDB vector search?

Methodology:
  1. Build a 2,000-drawer Anaktoron with 20 planted "needle" memories
  2. Run the same 20 needle queries through 3 pipelines:
     A) Raw ChromaDB vector search (searcher.py)
     B) Raw ChromaDB with SIGReg-groomed embeddings
     C) Full hybrid search (hybrid_searcher.py) — vector + FTS + trust + KG
  3. Measure Recall@5, Recall@10, MRR, and latency for each

Run:  python tests/benchmarks/bench_ab_test.py
"""

import os
import shutil
import sys
import tempfile
import time

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import chromadb
from tests.benchmarks.data_generator import AnaktoronDataGenerator


def _recall_at_k(results_texts, k):
    """Check if any needle appears in the top-k results."""
    return 1.0 if any("NEEDLE_" in t for t in results_texts[:k]) else 0.0


def _mrr(results_texts):
    """Mean Reciprocal Rank — 1/rank of first needle hit, or 0."""
    for i, t in enumerate(results_texts):
        if "NEEDLE_" in t:
            return 1.0 / (i + 1)
    return 0.0


def run_pipeline_a(anaktoron_path, queries):
    """Pipeline A: Raw ChromaDB vector search (searcher.py)."""
    from mnemion.searcher import search_memories

    col_name = "mnemion_drawers"
    results = {"recall@5": [], "recall@10": [], "mrr": [], "latency_ms": []}
    for q in queries:
        start = time.perf_counter()
        result = search_memories(q["query"], anaktoron_path, n_results=10, collection_name=col_name)
        elapsed = (time.perf_counter() - start) * 1000

        texts = [h["text"] for h in result.get("results", [])]
        results["recall@5"].append(_recall_at_k(texts, 5))
        results["recall@10"].append(_recall_at_k(texts, 10))
        results["mrr"].append(_mrr(texts))
        results["latency_ms"].append(elapsed)

    return results


def run_pipeline_b(anaktoron_path, queries):
    """Pipeline B: SIGReg-groomed embeddings, then raw ChromaDB search."""
    try:
        from mnemion.lewm import groom_embeddings, TORCH_AVAILABLE

        if not TORCH_AVAILABLE:
            return None
    except ImportError:
        return None

    # Groom all embeddings in the collection
    client = chromadb.PersistentClient(path=anaktoron_path)
    col = client.get_collection("mnemion_drawers")

    # Fetch all embeddings
    all_data = col.get(include=["embeddings", "documents", "metadatas"])
    if all_data["embeddings"] is None or len(all_data["embeddings"]) == 0:
        return None

    embeddings = all_data["embeddings"]
    ids = all_data["ids"]

    # Groom with production settings
    groomed = groom_embeddings(
        [e if isinstance(e, list) else e.tolist() for e in embeddings],
        iterations=10,
        lr=0.01,
        sigreg_weight=0.1,
    )

    # Create a parallel groomed collection
    groomed_col_name = "mnemion_drawers_groomed"
    try:
        client.delete_collection(groomed_col_name)
    except Exception:
        pass
    groomed_col = client.create_collection(groomed_col_name, metadata={"hnsw:space": "cosine"})

    # Re-insert with groomed embeddings in batches
    batch_size = 500
    for i in range(0, len(ids), batch_size):
        end = min(i + batch_size, len(ids))
        groomed_col.add(
            ids=ids[i:end],
            documents=all_data["documents"][i:end],
            metadatas=all_data["metadatas"][i:end],
            embeddings=groomed[i:end],
        )

    # Now search the groomed collection
    from mnemion.searcher import search_memories

    results = {"recall@5": [], "recall@10": [], "mrr": [], "latency_ms": []}
    for q in queries:
        start = time.perf_counter()
        result = search_memories(
            q["query"], anaktoron_path, n_results=10, collection_name="mnemion_drawers_groomed"
        )
        elapsed = (time.perf_counter() - start) * 1000

        texts = [h["text"] for h in result.get("results", [])]
        results["recall@5"].append(_recall_at_k(texts, 5))
        results["recall@10"].append(_recall_at_k(texts, 10))
        results["mrr"].append(_mrr(texts))
        results["latency_ms"].append(elapsed)

    return results


def run_pipeline_c(anaktoron_path, queries):
    """Pipeline C: Full hybrid search (vector + FTS + trust + KG)."""
    from mnemion.hybrid_searcher import HybridSearcher

    searcher = HybridSearcher(anaktoron_path=anaktoron_path)
    # Override collection name to match benchmark data (config may point elsewhere)
    searcher.collection_name = "mnemion_drawers"
    try:
        searcher.collection = searcher.chroma_client.get_collection("mnemion_drawers")
    except Exception as e:
        print(f"       Could not load collection: {e}")
        return {
            "recall@5": [0] * len(queries),
            "recall@10": [0] * len(queries),
            "mrr": [0] * len(queries),
            "latency_ms": [0] * len(queries),
        }

    results = {"recall@5": [], "recall@10": [], "mrr": [], "latency_ms": []}
    for q in queries:
        start = time.perf_counter()
        try:
            hits = searcher.search(q["query"], n_results=10)
        except Exception as e:
            print(f"       Hybrid search error: {e}")
            hits = []
        elapsed = (time.perf_counter() - start) * 1000

        texts = [h.get("text", "") for h in hits]
        results["recall@5"].append(_recall_at_k(texts, 5))
        results["recall@10"].append(_recall_at_k(texts, 10))
        results["mrr"].append(_mrr(texts))
        results["latency_ms"].append(elapsed)

    return results


def _avg(lst):
    return sum(lst) / max(len(lst), 1)


def print_results(name, results):
    """Print formatted results for a pipeline."""
    if results is None:
        print(f"  {name:30s}  SKIPPED (torch not available)")
        return
    r5 = _avg(results["recall@5"])
    r10 = _avg(results["recall@10"])
    mrr = _avg(results["mrr"])
    lat = _avg(results["latency_ms"])
    print(f"  {name:30s}  R@5={r5:.3f}  R@10={r10:.3f}  MRR={mrr:.3f}  Latency={lat:.1f}ms")


def main():
    print("=" * 72)
    print("  Mnemion A/B Benchmark: Raw vs Groomed vs Hybrid")
    print("=" * 72)

    # Build test corpus
    tmpdir = tempfile.mkdtemp(prefix="mnemion_ab_bench_")
    anaktoron_path = os.path.join(tmpdir, "anaktoron")

    try:
        print("\n[1/4] Generating 2,000-drawer Anaktoron with 20 needles...")
        gen = AnaktoronDataGenerator(seed=42, scale="small")
        _, _, needle_info = gen.populate_anaktoron_directly(
            anaktoron_path, n_drawers=2000, include_needles=True
        )
        queries = needle_info[:20]
        print(f"       {len(queries)} needle queries ready.")

        # Pipeline A: Raw vector search
        print("\n[2/4] Pipeline A: Raw ChromaDB vector search...")
        results_a = run_pipeline_a(anaktoron_path, queries)

        # Pipeline B: SIGReg groomed search
        print("[3/4] Pipeline B: SIGReg-groomed embeddings...")
        results_b = run_pipeline_b(anaktoron_path, queries)

        # Pipeline C: Full hybrid search
        print("[4/4] Pipeline C: Hybrid search (vector + FTS + trust)...")
        results_c = run_pipeline_c(anaktoron_path, queries)

        # Report
        print("\n" + "=" * 72)
        print("  RESULTS")
        print("=" * 72)
        print()
        print(f"  {'Pipeline':30s}  {'R@5':>6s}  {'R@10':>6s}  {'MRR':>6s}  {'Latency':>10s}")
        print(f"  {'-' * 30}  {'-' * 6}  {'-' * 6}  {'-' * 6}  {'-' * 10}")
        print_results("A) Raw ChromaDB", results_a)
        print_results("B) SIGReg Groomed", results_b)
        print_results("C) Hybrid (V+FTS+Trust)", results_c)

        # Delta analysis
        print()
        print("  ANALYSIS:")
        if results_b:
            delta_r5 = _avg(results_b["recall@5"]) - _avg(results_a["recall@5"])
            print(f"    SIGReg grooming vs raw:  R@5 delta = {delta_r5:+.3f}")
            if abs(delta_r5) < 0.001:
                print("    -> Grooming had NO measurable impact on recall.")
            elif delta_r5 > 0:
                print(f"    -> Grooming IMPROVED recall by {delta_r5 * 100:.1f}%")
            else:
                print(f"    -> Grooming HURT recall by {abs(delta_r5) * 100:.1f}%")

        delta_hybrid = _avg(results_c["recall@5"]) - _avg(results_a["recall@5"])
        print(f"    Hybrid vs raw:           R@5 delta = {delta_hybrid:+.3f}")
        if abs(delta_hybrid) < 0.001:
            print("    -> Hybrid search had NO measurable impact on recall.")
        elif delta_hybrid > 0:
            print(f"    -> Hybrid search IMPROVED recall by {delta_hybrid * 100:.1f}%")
        else:
            print(f"    -> Hybrid search HURT recall by {abs(delta_hybrid) * 100:.1f}%")

        lat_a = _avg(results_a["latency_ms"])
        lat_c = _avg(results_c["latency_ms"])
        print(
            f"    Latency cost of hybrid:  {lat_c:.1f}ms vs {lat_a:.1f}ms ({lat_c / max(lat_a, 0.1):.1f}x)"
        )

        print()
        print("=" * 72)

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
