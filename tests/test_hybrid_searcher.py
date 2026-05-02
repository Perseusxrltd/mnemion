from mnemion.hybrid_searcher import HybridSearcher


class _LegacyEmbeddingCollection:
    def get(self, ids, include):
        if "embeddings" in include:
            raise AttributeError("'dict' object has no attribute 'dimensionality'")
        return {
            "ids": ids,
            "documents": ["Memory retrieval should survive legacy HNSW payloads."],
            "metadatas": [{"wing": "sessions", "room": "planning", "source_file": "proof.md"}],
        }


def test_hybrid_search_hydrates_without_embedding_payloads():
    searcher = HybridSearcher.__new__(HybridSearcher)
    searcher.collection = _LegacyEmbeddingCollection()
    searcher.k = 60
    searcher._vector_search = lambda query, wing=None, room=None, limit=50: []
    searcher._fts_search = lambda query, wing=None, room=None, limit=50: ["drawer_legacy"]
    searcher._get_trust_map = lambda drawer_ids: {}

    hits = searcher.search("memory retrieval", n_results=1)

    assert hits == [
        {
            "id": "drawer_legacy",
            "text": "Memory retrieval should survive legacy HNSW payloads.",
            "wing": "sessions",
            "room": "planning",
            "source": "proof.md",
            "score": 0.016393,
            "trust_status": "current",
            "confidence": 1.0,
            "embedding": None,
        }
    ]
