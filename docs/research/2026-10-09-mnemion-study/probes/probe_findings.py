"""Reproduce Mnemion study findings using synthetic data in temporary storage.

Run with the audited working snapshot's Python environment:
    python probe_findings.py --repo /path/to/mnemion --out observations.json

This is a diagnostic harness, not a retrieval-quality benchmark. Controlled
candidate lists isolate ranking logic; storage cases use real Chroma + SQLite.
All configuration overrides are confined to this process. No live memories,
assistant settings, network LLMs, or sync remotes are used.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import runpy
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    if "MNEMION_HOME" not in (repo / "mnemion" / "config.py").read_text():
        parser.error("This probe requires the audited working version with MNEMION_HOME isolation.")
    sys.path.insert(0, str(repo))
    observations = []

    def record(case, reproduced, **details):
        observations.append({"case": case, "reproduced": bool(reproduced), **details})

    with tempfile.TemporaryDirectory(prefix="mnemion-study-probes-") as temp:
        root = Path(temp)
        task_profile = root / "profile"
        task_profile.mkdir()
        (task_profile / "config.json").write_text(
            json.dumps({"embedding_device": "hash", "llm": {"backend": "none"}})
        )
        os.environ.update(
            MNEMION_HOME=str(task_profile),
            MNEMION_ANAKTORON_PATH=str(task_profile / "anaktoron"),
            MNEMION_EMBEDDING_DEVICE="hash",
            MNEMION_SOURCE_PATH=str(task_profile / "sources"),
            MNEMION_WIKI_PATH=str(task_profile / "wiki"),
            MNEMION_OBSIDIAN_VAULT_PATH=str(task_profile / "obsidian"),
            ANONYMIZED_TELEMETRY="False",
        )

        # MCP redirects stdout on import; restore it for this standalone probe.
        output_stream = sys.stdout
        from mnemion import mcp_server as mcp

        sys.stdout = output_stream
        from mnemion.cognitive_graph import CognitiveGraph
        from mnemion.hybrid_searcher import HybridSearcher
        from mnemion.knowledge_graph import KnowledgeGraph
        from mnemion.moat_eval import _EvalCollection, run_moat_eval
        from mnemion.reconstruction import Reconstructor
        from mnemion.trust_lifecycle import DrawerTrust

        with patch.object(mcp._cd, "spawn_detection"):
            before = mcp._hybrid.collection is None
            added = mcp.tool_add_drawer("study", "notes", "quartz onboarding memory")
            existing_search = mcp._hybrid.search("quartz onboarding memory")
            fresh = HybridSearcher(str(task_profile / "anaktoron"), kg_path=mcp.kg_path)
            fresh_search = fresh.search("quartz onboarding memory")
            record(
                "R01_first_write_invisible_to_existing_searcher",
                before and added.get("success") and not existing_search and bool(fresh_search),
                collection_missing_at_start=before,
                write_success=added.get("success"),
                existing_search_hits=len(existing_search),
                newly_constructed_searcher_hits=len(fresh_search),
            )

            # Fail precisely between vector persistence and lexical persistence.
            text = "quartz interrupted write is recoverable only with reconciliation"
            with patch.object(
                mcp,
                "KnowledgeGraph",
                side_effect=sqlite3.OperationalError("injected sidecar outage"),
            ):
                failed = mcp.tool_add_drawer("study", "fault", text)
            retried = mcp.tool_add_drawer("study", "fault", text)
            identifier = retried["drawer_id"]
            with sqlite3.connect(mcp.kg_path) as conn:
                lexical = conn.execute(
                    "SELECT COUNT(*) FROM drawers_fts WHERE drawer_id=?", (identifier,)
                ).fetchone()[0]
            trust = mcp._trust.get(identifier)
            record(
                "R02_retry_acknowledges_incomplete_write",
                failed.get("success") is False
                and retried.get("success")
                and lexical == 0
                and trust is None,
                first_result=failed,
                retry_result=retried,
                vector_records=len(mcp._get_collection().get(ids=[identifier])["ids"]),
                lexical_records=lexical,
                trust_record_present=trust is not None,
            )

        # The sweeper does not call the other ingestion paths.
        from mnemion.sweeper import sweep

        sweep_root = root / "sweep"
        sweep_root.mkdir()
        transcript = sweep_root / "session.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "uuid": "message-1",
                    "session_id": "study",
                    "timestamp": "2026-10-09T00:00:00Z",
                    "role": "user",
                    "content": "quartz sweep exact identifier ALPHA_739",
                }
            )
            + "\n"
        )
        sweep_kg_path = str(sweep_root / "knowledge_graph.sqlite3")
        KnowledgeGraph(sweep_kg_path)
        DrawerTrust(sweep_kg_path)
        sweep_result = sweep(str(transcript), anaktoron_path=str(sweep_root / "anaktoron"))
        with sqlite3.connect(sweep_kg_path) as conn:
            lexical = conn.execute("SELECT COUNT(*) FROM drawers_fts").fetchone()[0]
            trust_count = conn.execute("SELECT COUNT(*) FROM drawer_trust").fetchone()[0]
        record(
            "R03_sweep_skips_lexical_and_trust",
            sweep_result["filed"] == 1 and lexical == 0 and trust_count == 0,
            sweep=sweep_result,
            lexical_records=lexical,
            trust_records=trust_count,
        )

        # A trust transition happens after the cognitive projection is built.
        cognitive_path = str(root / "cognitive.sqlite3")
        collection = _EvalCollection()
        collection.add(
            ids=["stale-claim"],
            documents=["quartz launch deadline is Friday because testing finished."],
            metadatas=[{"wing": "team", "room": "notes"}],
        )
        trust = DrawerTrust(cognitive_path)
        trust.create("stale-claim", wing="team", room="notes")
        graph = CognitiveGraph(cognitive_path)
        graph.consolidate_collection(collection, trust=trust)
        trust.update_status("stale-claim", "quarantined", reason="synthetic study case")
        recon = Reconstructor(graph, collection).reconstruct("quartz launch deadline")
        second_pass = graph.consolidate_collection(collection, trust=trust)
        returned = [h["id"] for h in recon["results"]]
        record(
            "R04_reconstruction_uses_stale_trust",
            "stale-claim" in returned,
            live_status=trust.get("stale-claim")["status"],
            returned_ids=returned,
            second_consolidation_count=second_pass["drawers_consolidated"],
        )

        def controlled_searcher(db, ids, docs, metadatas=None):
            c = _EvalCollection()
            c.add(
                ids=ids,
                documents=docs,
                metadatas=metadatas or [{"wing": "team_a", "room": "notes"} for _ in ids],
            )
            h = HybridSearcher.__new__(HybridSearcher)
            h.k = 60
            h.kg_path = db
            h.collection = c
            h._vector_search = lambda *a, **kw: ids
            h._fts_search = lambda *a, **kw: []
            return h

        scope_path = str(root / "scope.sqlite3")
        kg = KnowledgeGraph(scope_path)
        scoped_trust = DrawerTrust(scope_path)
        scoped_trust.create("team-b-source", wing="team_b", room="notes")
        scoped_trust.update_status("team-b-source", "quarantined", reason="synthetic study case")
        kg.add_triple("Alice", "works_at", "TeamBeta", source_closet="team-b-source")
        h = controlled_searcher(
            scope_path, ["team-a-source"], ["Alice participates in Team Alpha meetings."]
        )
        scoped_hits = h.search("Alice", wing="team_a", n_results=1)
        injected = [v for v in scoped_hits if v["wing"] == "temporal_graph"]
        record(
            "R05_graph_injection_ignores_scope_and_source_trust",
            bool(injected),
            requested_wing="team_a",
            requested_limit=1,
            returned_count=len(scoped_hits),
            quarantined_source_graph_hits=injected,
        )

        ranking_path = str(root / "ranking.sqlite3")
        KnowledgeGraph(ranking_path)
        ranking_trust = DrawerTrust(ranking_path)
        ranking_trust.create("low-confidence", wing="team_a", room="notes", confidence=0.05)
        ranking_trust.create("high-confidence", wing="team_a", room="notes", confidence=1.0)
        h = controlled_searcher(
            ranking_path,
            ["low-confidence", "high-confidence"],
            ["quartz low confidence", "quartz high confidence"],
        )
        ranking_hits = h.search("quartz", n_results=2)
        first = h.search("quartz", n_results=1)
        record(
            "R06_confidence_weight_does_not_rerank",
            ranking_hits[0]["score"] < ranking_hits[1]["score"]
            and first[0]["id"] == "low-confidence",
            ordered_scores=[{"id": hit["id"], "score": hit["score"]} for hit in ranking_hits],
            top_one=first[0]["id"],
        )
        filtered = h.search("quartz", n_results=2, min_similarity=0.5)
        record(
            "R07_similarity_threshold_applied_to_rrf",
            bool(ranking_hits) and not filtered,
            results_without_threshold=len(ranking_hits),
            results_with_threshold_0_5=len(filtered),
            maximum_two_channel_rrf_score_at_k60=2 / 61,
        )

        # FTS5's UNINDEXED column is not a uniqueness constraint.
        from mnemion.miner import add_drawer

        file = task_profile / "editable.txt"
        file.write_text("obsoletequartz detail")
        col = mcp._get_collection(create=True)
        add_drawer(col, "study", "edit", file.read_text(), str(file), 0, "study")
        file.write_text("replacementquartz detail")
        add_drawer(col, "study", "edit", file.read_text(), str(file), 0, "study")
        with sqlite3.connect(mcp.kg_path) as conn:
            lexical_rows = conn.execute(
                "SELECT drawer_id,content FROM drawers_fts WHERE wing='study' AND room='edit'"
            ).fetchall()
        vector_rows = col.get(where={"$and": [{"wing": "study"}, {"room": "edit"}]})
        record(
            "R08_remining_duplicates_fts_rows",
            len(lexical_rows) == 2 and len(vector_rows["ids"]) == 1,
            lexical_rows=lexical_rows,
            vector_documents=vector_rows["documents"],
        )

        # The portable drawer envelope carries neither the sidecar nor its trust.
        from mnemion.cli import cmd_restore, _stream_json_array

        original_id = added["drawer_id"]
        mcp._trust.update_status(original_id, "quarantined", reason="synthetic export study")
        data = col.get(ids=[original_id], include=["documents", "metadatas"])
        envelope = [
            {"id": did, "content": doc, "meta": meta}
            for did, doc, meta in zip(data["ids"], data["documents"], data["metadatas"])
        ]
        export = root / "drawers_export.json"
        export.write_text(json.dumps(envelope))
        restore_target = root / "restore" / "anaktoron"
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_restore(
                SimpleNamespace(
                    palace=str(restore_target),
                    file=str(export),
                    batch_size=50,
                    merge=False,
                    replace=False,
                )
            )
        restore_kg = str(restore_target.parent / "knowledge_graph.sqlite3")
        sidecar_created = Path(restore_kg).exists()
        KnowledgeGraph(restore_kg)
        restored_trust = DrawerTrust(restore_kg)
        restored_search = HybridSearcher(str(restore_target), kg_path=restore_kg).search(
            "quartz onboarding memory"
        )
        record(
            "R09_restore_loses_quarantine_and_sidecar",
            not sidecar_created
            and restored_trust.get(original_id) is None
            and bool(restored_search),
            original_trust="quarantined",
            sidecar_created_by_restore=sidecar_created,
            restored_trust_record=restored_trust.get(original_id),
            restored_search_statuses=[hit["trust_status"] for hit in restored_search],
        )

        truncated = root / "truncated.json"
        truncated.write_text('[{"id":"complete","content":"one","meta":{}},{"id":"unfinished"')
        parsed = list(_stream_json_array(str(truncated)))
        record(
            "R10_restore_parser_accepts_truncation",
            len(parsed) == 1,
            parsed_objects=parsed,
            raised_parse_error=False,
        )

        spec = importlib.util.spec_from_file_location(
            "study_merge_exports", repo / "sync" / "merge_exports.py"
        )
        merge_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(merge_mod)
        ours = root / "local.json"
        theirs = root / "remote.json"
        merged = root / "merged.json"
        ours.write_text("[]")
        theirs.write_text(json.dumps(envelope))
        with contextlib.redirect_stdout(io.StringIO()):
            merge_mod.merge(str(ours), str(theirs), str(merged))
        merged_rows = json.loads(merged.read_text())
        record(
            "R11_sync_resurrects_deleted_memory",
            any(x["id"] == original_id for x in merged_rows),
            local_count_after_delete=0,
            remote_count=1,
            merged_count=len(merged_rows),
        )

        benchmark = runpy.run_path(str(repo / "tests" / "benchmarks" / "bench_ab_test.py"))
        wrong_answer = ["NEEDLE_UNRELATED: an answer to a completely different question"]
        recall = benchmark["_recall_at_k"](wrong_answer, 5)
        mrr = benchmark["_mrr"](wrong_answer)
        record(
            "R12_benchmark_rewards_wrong_needle",
            recall == 1.0 and mrr == 1.0,
            wrong_needle_recall_at_5=recall,
            wrong_needle_mrr=mrr,
        )

        with (
            patch("mnemion.hybrid_searcher.HybridSearcher.search") as hybrid_spy,
            patch("mnemion.searcher.search_memories") as vector_spy,
        ):
            moat = run_moat_eval()
        record(
            "R13_moat_baselines_are_not_executed",
            hybrid_spy.call_count == 0 and vector_spy.call_count == 0,
            hybrid_calls=hybrid_spy.call_count,
            vector_calls=vector_spy.call_count,
            fixture_count=sum(moat["case_counts"].values()),
            mode_scores=moat["scores"],
        )

        record(
            "R14_predictive_retrieval_has_no_search_embeddings",
            all(hit.get("embedding") is None for hit in fresh_search),
            result_count=len(fresh_search),
            embeddings_present=sum(hit.get("embedding") is not None for hit in fresh_search),
        )

        longmem = runpy.run_path(str(repo / "benchmarks" / "longmemeval_bench.py"))
        actual_ndcg = longmem["ndcg"](
            [0, 2], {"relevant-a", "relevant-b"}, ["relevant-a", "relevant-b", "irrelevant"], 2
        )
        correct_ndcg = 1 / (1 + 1 / math.log2(3))
        record(
            "R15_ndcg_normalizes_only_retrieved_relevance",
            actual_ndcg == 1.0,
            returned_relevant_documents=1,
            total_relevant_documents=2,
            reported_ndcg_at_2=actual_ndcg,
            correct_ndcg_at_2=correct_ndcg,
        )

        # Report tool schema size as an observation, not a measured token count.
        listed = mcp.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"][
            "tools"
        ]
        observations.append(
            {
                "case": "tool_surface_inventory",
                "tool_count": len(listed),
                "schema_utf8_bytes": len(json.dumps(listed).encode("utf-8")),
            }
        )

    result = {
        "method": "synthetic regression probes; no retrieval-quality or load benchmark",
        "observations": observations,
    }
    serialized = json.dumps(result, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(serialized + "\n")
    print(serialized)


if __name__ == "__main__":
    main()
