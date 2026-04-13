#!/usr/bin/env python3
"""
hybrid_searcher.py — High-Fidelity Retrieval Engine for Mnemion
================================================================

This module implements a Hybrid Retrieval strategy combining Semantic Search
(Vector-based via ChromaDB) and Lexical Search (Keyword-based via SQLite FTS5).

Results are fused using the Reciprocal Rank Fusion (RRF) algorithm, which
optimizes for both conceptual relevance and exact identifier matching.

Algorithm:
    Score(d) = sum( 1 / (k + rank(d, r)) ) for r in result_sets
    where k is a smoothing constant (default 60).
"""

import hashlib
import logging
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Optional, Any, Set

import chromadb
from .config import MnemionConfig

# Statuses excluded from search by default
_HIDDEN_STATUSES: Set[str] = {"superseded", "historical"}

logger = logging.getLogger("mnemion.hybrid")

# English stop words to strip before building a keyword FTS query.  Short list
# focused on words that add noise to FTS5 token matching without helping rank.
_FTS_STOPWORDS: Set[str] = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "as",
    "is",
    "was",
    "are",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "must",
    "shall",
    "can",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
    "they",
    "them",
    "their",
    "we",
    "our",
    "you",
    "your",
    "i",
    "my",
    "me",
    "he",
    "she",
    "his",
    "her",
    "who",
    "what",
    "when",
    "where",
    "why",
    "how",
    "which",
    "if",
    "then",
    "so",
    "not",
    "no",
    "yes",
    "also",
    "just",
    "very",
    "really",
    "still",
    "even",
    "only",
    "now",
    "here",
    "there",
    "too",
    "up",
    "out",
    "about",
    "like",
    "after",
    "before",
    "next",
    "some",
    "any",
    "all",
    "each",
    "more",
}


def _fts_keyword_tokens(query: str) -> List[str]:
    """
    Split a natural-language query into FTS5-safe tokens suitable for an
    AND-of-terms keyword search.  Strips punctuation, removes stop words, and
    dedups while preserving order.  Returns an empty list when the query
    reduces to nothing useful (e.g. pure stop-word sentence).
    """
    # Strip FTS5-special characters (double-quotes, parentheses, hyphens
    # when used as operators, asterisks) to avoid syntax errors.
    clean = re.sub(r'["\(\)\*\+\-]', " ", query)
    tokens = re.findall(r"\b[A-Za-z0-9_]{2,}\b", clean)
    seen: set = set()
    result = []
    for t in tokens:
        lower = t.lower()
        if lower not in _FTS_STOPWORDS and lower not in seen:
            seen.add(lower)
            result.append(t)
    return result


class HybridSearcher:
    """
    Orchestrates fused retrieval across Vector and Lexical data stores.
    """

    def __init__(
        self, palace_path: Optional[str] = None, kg_path: Optional[str] = None, k: int = 60
    ):
        cfg = MnemionConfig()
        self.palace_path = palace_path or cfg.palace_path
        self.kg_path = kg_path or Path(self.palace_path).parent / "knowledge_graph.sqlite3"
        self.k = k
        self.collection_name = cfg.collection_name

        # Persistent clients
        from .chroma_compat import fix_blob_seq_ids

        fix_blob_seq_ids(self.palace_path)
        self.chroma_client = chromadb.PersistentClient(path=self.palace_path)
        try:
            self.collection = self.chroma_client.get_collection(self.collection_name)
        except Exception:
            # Anaktoron not yet initialized — search will return empty results.
            self.collection = None

    def _fts_run(
        self,
        fts_query: str,
        wing: Optional[str],
        room: Optional[str],
        limit: int,
    ) -> List[str]:
        """Execute a single raw FTS5 MATCH query and return drawer_ids."""
        conn = sqlite3.connect(self.kg_path, timeout=10)
        sql = "SELECT drawer_id FROM drawers_fts WHERE content MATCH ?"
        params: List[Any] = [fts_query]
        if wing:
            sql += " AND wing = ?"
            params.append(wing)
        if room:
            sql += " AND room = ?"
            params.append(room)
        sql += " LIMIT ?"
        params.append(limit)
        results: List[str] = []
        try:
            for row in conn.execute(sql, params).fetchall():
                results.append(row[0])
        except sqlite3.OperationalError as e:
            logger.warning(f"FTS query failed ({fts_query!r}): {e}")
        finally:
            conn.close()
        return results

    def _fts_search(
        self, query: str, wing: Optional[str] = None, room: Optional[str] = None, limit: int = 50
    ) -> List[str]:
        """
        Lexical search against the SQLite FTS5 virtual table.

        Runs two passes and merges results:
        1. Phrase search — the entire query wrapped in double-quotes.  Precise
           but only fires when the literal phrase appears in a document.
        2. Keyword search — significant tokens (stop-words stripped) joined as
           an FTS5 AND-of-terms query.  Fires on natural-language questions and
           conversational queries where phrase match rarely helps.

        Phase-match hits are returned first (higher positional priority in RRF),
        followed by keyword-only hits, deduplicated.
        """
        # Pass 1: phrase match
        escaped = query.replace('"', '""')
        phrase_ids = self._fts_run(f'"{escaped}"', wing, room, limit)

        # Pass 2: keyword match — skip if query is very short (phrase already covers it)
        keyword_ids: List[str] = []
        tokens = _fts_keyword_tokens(query)
        if len(tokens) >= 2:  # need at least 2 tokens for a useful keyword query
            kw_query = " ".join(tokens)
            keyword_ids = self._fts_run(kw_query, wing, room, limit)

        # Merge preserving phrase-first order, dedup
        seen: Set[str] = set()
        merged: List[str] = []
        for doc_id in phrase_ids + keyword_ids:
            if doc_id not in seen:
                seen.add(doc_id)
                merged.append(doc_id)
        return merged[:limit]

    def _vector_search(
        self, query: str, wing: Optional[str] = None, room: Optional[str] = None, limit: int = 50
    ) -> List[str]:
        """
        Executes a semantic search against ChromaDB.
        """
        where = {}
        if wing and room:
            where = {"$and": [{"wing": wing}, {"room": room}]}
        elif wing:
            where = {"wing": wing}
        elif room:
            where = {"room": room}

        if self.collection is None:
            return []
        try:
            # chromadb 1.x: ids are always returned; "ids" is not a valid include item
            results = self.collection.query(
                query_texts=[query],
                n_results=limit,
                where=where if where else None,
                include=[],
            )
            return results["ids"][0] if results.get("ids") else []
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []

    def _get_trust_map(self, drawer_ids: List[str]) -> Dict[str, Dict]:
        """Fetch trust records for a batch of drawer_ids. Returns {drawer_id: {status, confidence}}."""
        if not drawer_ids:
            return {}
        try:
            placeholders = ",".join("?" * len(drawer_ids))
            conn = sqlite3.connect(self.kg_path, timeout=10)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT drawer_id, status, confidence FROM drawer_trust WHERE drawer_id IN ({placeholders})",
                drawer_ids,
            ).fetchall()
            conn.close()
            return {
                r["drawer_id"]: {"status": r["status"], "confidence": r["confidence"]} for r in rows
            }
        except Exception as e:
            logger.warning(f"Trust map fetch failed: {e}")
            return {}

    def search(
        self,
        query: str,
        wing: Optional[str] = None,
        room: Optional[str] = None,
        n_results: int = 5,
        include_superseded: bool = False,
        min_similarity: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Performs a hybrid search and returns fused, hydrated results.
        Superseded and historical drawers are filtered out by default.
        Contested drawers are included but flagged with a warning marker.
        """
        if self.collection is None:
            return []
            
        # -- ACTIVE FIX: Temporal Knowledge Graph Injection --
        kg_hits = []
        try:
            from .knowledge_graph import KnowledgeGraph
            kg = KnowledgeGraph(self.kg_path)
            
            # Simple lightweight heuristic extraction (capitalized terms > 2 chars)
            tokens = re.findall(r'\b[A-Z][a-z]+\b', query)
            distinct_entities = set(t for t in tokens if len(t) > 2)
            
            for ent in distinct_entities:
                triples = kg.query_entity(ent, direction="both")
                
                # Format valid triples into synthetic RAG hits
                for t in triples:
                    if t.get("current", False):
                        fact_str = f"[TEMPORAL GRAPH DATA]: {t['subject']} {t['predicate'].replace('_', ' ')} {t['object']}."
                        if t.get("valid_from"):
                            fact_str += f" (Valid from: {t['valid_from']})"
                        
                        kg_hits.append({
                            "id": f"kg_{hashlib.md5(fact_str.encode()).hexdigest()[:16]}",
                            "text": fact_str,
                            "wing": "temporal_graph",
                            "room": "fact",
                            "source": "knowledge_graph.sqlite3",
                            "score": 1.0,  # Max score for strict graph facts
                            "trust_status": "current",
                            "confidence": t.get("confidence", 1.0),
                            "embedding": None
                        })
        except Exception as e:
            logger.debug(f"KG Injection failed non-fatally: {e}")
            
        kg_hits = kg_hits[:3] # Cap to top 3 pristine facts

        # 1. Gather candidates from both engines (fetch more to allow for trust filtering)
        fetch_limit = max(50, n_results * 10)
        vector_ids = self._vector_search(query, wing, room, limit=fetch_limit)
        lexical_ids = self._fts_search(query, wing, room, limit=fetch_limit)

        # 2. Reciprocal Rank Fusion (RRF)
        fused_scores = defaultdict(float)
        for rank, doc_id in enumerate(vector_ids, 1):
            fused_scores[doc_id] += 1.0 / (self.k + rank)
        for rank, doc_id in enumerate(lexical_ids, 1):
            fused_scores[doc_id] += 1.0 / (self.k + rank)

        # 3. Rank by fused score
        ranked = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
        if not ranked:
            return []

        all_ids = [doc_id for doc_id, _ in ranked]

        # 4. Trust filter — load trust map and remove hidden statuses
        trust_map = self._get_trust_map(all_ids)
        filtered = []
        for doc_id, score in ranked:
            trust = trust_map.get(doc_id)
            if trust:
                status = trust["status"]
                if not include_superseded and status in _HIDDEN_STATUSES:
                    continue
                # Weight score by confidence
                confidence = trust.get("confidence", 1.0)
                filtered.append((doc_id, score * confidence, status, confidence))
            else:
                # No trust record yet (pre-backfill) — treat as current
                filtered.append((doc_id, score, "current", 1.0))

        top_entries = filtered[:n_results]
        if not top_entries:
            return []

        # 5. Hydrate from the verbatim document store
        final_ids = [item[0] for item in top_entries]
        data = self.collection.get(ids=final_ids, include=["documents", "metadatas", "embeddings"])
        _embs = data.get("embeddings")
        embeddings = _embs if _embs is not None else [None] * len(data["ids"])
        doc_map = {
            idx: (doc, meta, emb)
            for idx, doc, meta, emb in zip(data["ids"], data["documents"], data["metadatas"], embeddings)
        }

        hits = []
        for doc_id, score, status, confidence in top_entries:
            if min_similarity > 0.0 and score < min_similarity:
                continue
            if doc_id in doc_map:
                doc, meta, emb = doc_map[doc_id]
                hit = {
                    "id": doc_id,
                    "text": doc,
                    "wing": meta.get("wing", "unknown"),
                    "room": meta.get("room", "unknown"),
                    "source": Path(meta.get("source_file", "?")).name,
                    "score": round(score, 6),
                    "trust_status": status,
                    "confidence": round(confidence, 3),
                    "embedding": emb.tolist() if hasattr(emb, "tolist") else emb,
                }
                if status == "contested":
                    hit["warning"] = "⚠ This memory is contested — accuracy uncertain"
                hits.append(hit)

        return kg_hits + hits
