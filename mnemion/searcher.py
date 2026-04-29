#!/usr/bin/env python3
"""
searcher.py — Find anything. Exact words.

Semantic search against the Anaktoron.
Returns verbatim text — the actual words, never summaries.

.. deprecated::
    This module performs pure vector search only. For production retrieval
    (hybrid vector+FTS, trust filtering, KG injection), use
    ``hybrid_searcher.HybridSearcher`` instead. This module is retained
    for backward compatibility and legacy tests.
"""

import logging
from pathlib import Path

from .config import MnemionConfig
from .chroma_compat import VectorStoreUnsafe, make_persistent_client

logger = logging.getLogger("mnemion_mcp")


class SearchError(Exception):
    """Raised when search cannot proceed (e.g. no Anaktoron found)."""


def search(
    query: str,
    anaktoron_path: str,
    wing: str = None,
    room: str = None,
    n_results: int = 5,
    min_similarity: float = 0.0,
    collection_name: str = None,
):
    """
    Search the Anaktoron. Returns verbatim drawer content.
    Optionally filter by wing (project) or room (aspect).
    """
    col_name = collection_name or MnemionConfig().collection_name
    try:
        client = make_persistent_client(anaktoron_path, vector_safe=True, collection_name=col_name)
        col = client.get_collection(col_name)
    except VectorStoreUnsafe as exc:
        print("\n  Vector search disabled: HNSW index divergence detected")
        print("  Run: mnemion repair --mode status")
        raise SearchError("Vector store unsafe to open") from exc
    except Exception:
        print(f"\n  No Anaktoron found at {anaktoron_path}")
        print("  Run: mnemion init <dir> then mnemion mine <dir>")
        raise SearchError(f"No Anaktoron found at {anaktoron_path}")

    # Build where filter
    where = {}
    if wing and room:
        where = {"$and": [{"wing": wing}, {"room": room}]}
    elif wing:
        where = {"wing": wing}
    elif room:
        where = {"room": room}

    try:
        kwargs = {
            "query_texts": [query],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = col.query(**kwargs)

    except Exception as e:
        print(f"\n  Search error: {e}")
        raise SearchError(f"Search error: {e}") from e

    # ChromaDB 1.x may return {documents: []}; guard before [0]. Issue #195.
    if not results.get("documents") or not results["documents"][0]:
        print(f'\n  No results found for: "{query}"')
        return

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    print(f"\n{'=' * 60}")
    print(f'  Results for: "{query}"')
    if wing:
        print(f"  Wing: {wing}")
    if room:
        print(f"  Room: {room}")
    print(f"{'=' * 60}\n")

    displayed = 0
    for doc, meta, dist in zip(docs, metas, dists):
        similarity = round(1 - dist, 3)
        if similarity < min_similarity:
            continue
        displayed += 1
        source = Path(meta.get("source_file", "?")).name
        wing_name = meta.get("wing", "?")
        room_name = meta.get("room", "?")

        print(f"  [{displayed}] {wing_name} / {room_name}")
        print(f"      Source: {source}")
        print(f"      Match:  {similarity}")
        print()
        # Print the verbatim text, indented
        for line in doc.strip().split("\n"):
            print(f"      {line}")
        print()
        print(f"  {'─' * 56}")

    if displayed == 0:
        print(f'\n  No results above similarity threshold ({min_similarity}) for: "{query}"')

    print()


def search_memories(
    query: str,
    anaktoron_path: str,
    wing: str = None,
    room: str = None,
    n_results: int = 5,
    min_similarity: float = 0.0,
    collection_name: str = None,
) -> dict:
    """
    Programmatic search — returns a dict instead of printing.
    Used by the MCP server and other callers that need data.
    """
    col_name = collection_name or MnemionConfig().collection_name
    try:
        client = make_persistent_client(anaktoron_path, vector_safe=True, collection_name=col_name)
        col = client.get_collection(col_name)
    except VectorStoreUnsafe as exc:
        return {
            "error": "Vector store unsafe to open",
            "vector_disabled": True,
            "health": exc.health,
            "hint": "Run: mnemion repair --mode status, then rebuild if divergence is confirmed",
        }
    except Exception as e:
        logger.error("No Anaktoron found at %s: %s", anaktoron_path, e)
        return {
            "error": "No Anaktoron found",
            "hint": "Run: mnemion init <dir> && mnemion mine <dir>",
        }

    # Build where filter
    where = {}
    if wing and room:
        where = {"$and": [{"wing": wing}, {"room": room}]}
    elif wing:
        where = {"wing": wing}
    elif room:
        where = {"room": room}

    try:
        kwargs = {
            "query_texts": [query],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = col.query(**kwargs)
    except Exception as e:
        return {"error": f"Search error: {e}"}

    # ChromaDB 1.x may return {documents: []}; guard before [0]. Issue #195.
    if not results.get("documents") or not results["documents"][0]:
        return {
            "query": query,
            "filters": {"wing": wing, "room": room},
            "results": [],
        }

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    hits = []
    for doc, meta, dist in zip(docs, metas, dists):
        similarity = round(1 - dist, 3)
        if similarity < min_similarity:
            continue
        hits.append(
            {
                "text": doc,
                "wing": meta.get("wing", "unknown"),
                "room": meta.get("room", "unknown"),
                "source_file": Path(meta.get("source_file", "?")).name,
                "similarity": similarity,
            }
        )

    return {
        "query": query,
        "filters": {"wing": wing, "room": room},
        "results": hits,
    }
