"""Active reconstruction search over the cognitive graph."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .cognitive_graph import CognitiveGraph
from .config import MnemionConfig
from .backends.registry import get_backend


class Reconstructor:
    def __init__(
        self,
        graph: CognitiveGraph,
        collection,
        topic_tunnel_min_count: int = 2,
    ):
        self.graph = graph
        self.collection = collection
        self.topic_tunnel_min_count = max(2, int(topic_tunnel_min_count))

    def reconstruct(self, query: str, budget: int = 10) -> dict[str, Any]:
        units = self.graph.search_units(query, budget=budget)
        drawer_order = []
        evidence: dict[str, list[dict[str, Any]]] = {}

        def add_evidence(unit: dict[str, Any], via_topic_tunnel: str | None = None) -> None:
            drawer_id = unit["drawer_id"]
            if drawer_id not in evidence:
                drawer_order.append(drawer_id)
                evidence[drawer_id] = []
            matched_cues = list(unit.get("matched_cues") or [])
            if via_topic_tunnel and not matched_cues:
                matched_cues = [via_topic_tunnel]
            item = {
                "unit_id": unit["unit_id"],
                "unit_type": unit["unit_type"],
                "text": unit["text"],
                "matched_cues": matched_cues,
            }
            if via_topic_tunnel:
                item["via_topic_tunnel"] = via_topic_tunnel
            evidence[drawer_id].append(item)

        seen_unit_ids = set()
        for unit in units:
            seen_unit_ids.add(unit["unit_id"])
            add_evidence(unit)

        topic_tunnels = self.graph.tunnels_for_query(
            query,
            min_count=self.topic_tunnel_min_count,
        )
        for tunnel in topic_tunnels:
            for unit in tunnel["units"]:
                if unit["unit_id"] in seen_unit_ids:
                    continue
                seen_unit_ids.add(unit["unit_id"])
                add_evidence(unit, via_topic_tunnel=tunnel["cue"])

        if not drawer_order:
            return {"query": query, "results": [], "topic_tunnels": []}

        hydrated = self.collection.get(ids=drawer_order, include=["documents", "metadatas"])
        doc_map = {
            drawer_id: (doc, meta or {})
            for drawer_id, doc, meta in zip(
                hydrated.get("ids") or [],
                hydrated.get("documents") or [],
                hydrated.get("metadatas") or [],
            )
        }
        results = []
        for drawer_id in drawer_order:
            if drawer_id not in doc_map:
                continue
            doc, meta = doc_map[drawer_id]
            results.append(
                {
                    "id": drawer_id,
                    "text": doc,
                    "wing": meta.get("wing", "unknown"),
                    "room": meta.get("room", "unknown"),
                    "source": Path(meta.get("source_file", "?")).name,
                    "evidence_trail": evidence[drawer_id],
                }
            )
        return {"query": query, "results": results, "topic_tunnels": topic_tunnels}


def reconstruct_query(
    query: str,
    anaktoron_path: str | None = None,
    kg_path: str | None = None,
    budget: int = 10,
    collection_name: str | None = None,
) -> dict[str, Any]:
    cfg = MnemionConfig()
    target = anaktoron_path or cfg.anaktoron_path
    kg = kg_path or str(Path(target).parent / "knowledge_graph.sqlite3")
    collection = get_backend(anaktoron_path=target).get_collection(
        collection_name or cfg.collection_name
    )
    return Reconstructor(
        CognitiveGraph(kg),
        collection,
        topic_tunnel_min_count=cfg.topic_tunnel_min_count,
    ).reconstruct(query, budget=budget)
