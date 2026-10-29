"""Passage chronology must not rematerialize unrelated authorized memories."""

import psycopg

from mnemion.service.models import MemoryInput, RecallInput
from mnemion.service.retrieval import RetrievalService


def test_passage_ranking_materializes_only_selected_candidates(env, monkeypatch):
    for index in range(32):
        env.memory.save(
            env.owner,
            env.space,
            MemoryInput(content=f"Unrelated garden observation {index}"),
            f"unrelated-{index}",
        )
    answer = env.memory.save(
        env.owner, env.space, MemoryInput(content="Postgres billing procedure"), "answer"
    )
    execute = psycopg.Connection.execute
    materialized = []

    def inspect(connection, query, params=None, *args, **kwargs):
        if isinstance(params, dict) and "selected_memories" in params:
            explained = execute(
                connection, "EXPLAIN (ANALYZE, FORMAT JSON) " + query, params
            ).fetchone()["QUERY PLAN"][0]["Plan"]

            def visit(node):
                if node.get("Subplan Name") == "CTE eligible":
                    materialized.append(
                        (node["Actual Rows"] * node["Actual Loops"], len(params["selected_memories"]))
                    )
                for child in node.get("Plans", []):
                    visit(child)

            visit(explained)
        return execute(connection, query, params, *args, **kwargs)

    monkeypatch.setattr(psycopg.Connection, "execute", inspect)
    result = RetrievalService(env.db, env.embedder).recall(
        env.owner,
        RecallInput(query="Postgres billing", space_ids=[env.space], mode="lexical"),
    )
    assert [hit["memory_id"] for hit in result["hits"]] == [answer["memory_id"]]
    assert result["index"]["eligible_records"] == 33
    assert materialized == [(1, 1)], materialized
