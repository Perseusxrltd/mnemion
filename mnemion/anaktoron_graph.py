"""
anaktoron_graph.py — Graph traversal layer for Mnemion
======================================================

Builds a navigable graph from the Anaktoron structure:
  - Nodes = rooms (named ideas)
  - Edges = shared rooms across wings (tunnels)
  - Edge types = halls (the corridors)

Enables queries like:
  "Start at chromadb-setup in wing_code, walk to wing_myproject"
  "Find all rooms connected to riley-college-apps"
  "What topics bridge wing_hardware and wing_myproject?"

No external graph DB needed — built from ChromaDB metadata.
"""

import json
import os
import tempfile
import uuid
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path
from .config import MnemionConfig
from .chroma_compat import make_persistent_client


def _get_collection(config=None):
    config = config or MnemionConfig()
    try:
        client = make_persistent_client(
            config.anaktoron_path,
            vector_safe=True,
            collection_name=config.collection_name,
        )
        return client.get_collection(config.collection_name)
    except Exception as e:
        print(f"Caught exception: {e}")
        return None


def _tunnels_path(config=None) -> Path:
    config = config or MnemionConfig()
    return Path(config.anaktoron_path).expanduser().parent / "tunnels.json"


def _load_explicit_tunnels(config=None) -> list[dict]:
    path = _tunnels_path(config)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    except Exception:
        pass
    return []


def _save_explicit_tunnels(tunnels: list[dict], config=None) -> None:
    path = _tunnels_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="tunnels-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(tunnels, f, indent=2, sort_keys=True)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def create_tunnel(
    source_wing: str,
    source_room: str,
    target_wing: str,
    target_room: str,
    label: str = "",
    source_drawer_id: str = "",
    target_drawer_id: str = "",
    config=None,
) -> dict:
    tunnels = _load_explicit_tunnels(config)
    tunnel_id = "tun_" + uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc).isoformat()
    tunnel = {
        "tunnel_id": tunnel_id,
        "source_wing": source_wing,
        "source_room": source_room,
        "target_wing": target_wing,
        "target_room": target_room,
        "label": label,
        "source_drawer_id": source_drawer_id,
        "target_drawer_id": target_drawer_id,
        "created_at": now,
    }
    tunnels.append(tunnel)
    _save_explicit_tunnels(tunnels, config)
    return tunnel


def list_explicit_tunnels(wing: str = None, config=None) -> list[dict]:
    tunnels = _load_explicit_tunnels(config)
    if wing:
        tunnels = [
            t for t in tunnels if t.get("source_wing") == wing or t.get("target_wing") == wing
        ]
    return tunnels


def delete_tunnel(tunnel_id: str, config=None) -> dict:
    tunnels = _load_explicit_tunnels(config)
    kept = [t for t in tunnels if t.get("tunnel_id") != tunnel_id]
    if len(kept) == len(tunnels):
        return {"success": False, "error": f"Tunnel not found: {tunnel_id}"}
    _save_explicit_tunnels(kept, config)
    return {"success": True, "tunnel_id": tunnel_id}


def follow_tunnels(wing: str, room: str, config=None) -> dict:
    matches = []
    for tunnel in _load_explicit_tunnels(config):
        if tunnel.get("source_wing") == wing and tunnel.get("source_room") == room:
            matches.append({**tunnel, "direction": "outbound"})
        elif tunnel.get("target_wing") == wing and tunnel.get("target_room") == room:
            matches.append({**tunnel, "direction": "inbound"})
    return {"wing": wing, "room": room, "tunnels": matches}


def build_graph(col=None, config=None):
    """
    Build the Anaktoron graph from ChromaDB metadata.

    Returns:
        nodes: dict of {room: {wings: set, halls: set, count: int}}
        edges: list of {room, wing_a, wing_b, hall} — one per tunnel crossing
    """
    if col is None:
        col = _get_collection(config)
    if not col:
        return {}, []

    total = col.count()
    room_data = defaultdict(lambda: {"wings": set(), "halls": set(), "count": 0, "dates": set()})

    offset = 0
    while offset < total:
        batch = col.get(limit=1000, offset=offset, include=["metadatas"])
        for meta in batch["metadatas"]:
            room = meta.get("room", "")
            wing = meta.get("wing", "")
            hall = meta.get("hall", "")
            date = meta.get("date", "")
            if room and room != "general" and wing:
                room_data[room]["wings"].add(wing)
                if hall:
                    room_data[room]["halls"].add(hall)
                if date:
                    room_data[room]["dates"].add(date)
                room_data[room]["count"] += 1
        if not batch["ids"]:
            break
        offset += len(batch["ids"])

    # Build edges from rooms that span multiple wings
    edges = []
    for room, data in room_data.items():
        wings = sorted(data["wings"])
        if len(wings) >= 2:
            for i, wa in enumerate(wings):
                for wb in wings[i + 1 :]:
                    halls = data["halls"] if data["halls"] else [""]
                    for hall in halls:
                        edges.append(
                            {
                                "room": room,
                                "wing_a": wa,
                                "wing_b": wb,
                                "hall": hall,
                                "count": data["count"],
                            }
                        )

    # Convert sets to lists for JSON serialization
    nodes = {}
    for room, data in room_data.items():
        nodes[room] = {
            "wings": sorted(data["wings"]),
            "halls": sorted(data["halls"]),
            "count": data["count"],
            "dates": sorted(data["dates"])[-5:] if data["dates"] else [],
        }

    return nodes, edges


def traverse(start_room: str, col=None, config=None, max_hops: int = 2):
    """
    Walk the graph from a starting room. Find connected rooms
    through shared wings.

    Returns list of paths: [{room, wing, hall, hop_distance}]
    """
    nodes, edges = build_graph(col, config)

    if start_room not in nodes:
        return {
            "error": f"Room '{start_room}' not found",
            "suggestions": _fuzzy_match(start_room, nodes),
        }

    start = nodes[start_room]
    visited = {start_room}
    results = [
        {
            "room": start_room,
            "wings": start["wings"],
            "halls": start["halls"],
            "count": start["count"],
            "hop": 0,
        }
    ]

    # BFS traversal
    frontier = [(start_room, 0)]
    while frontier:
        current_room, depth = frontier.pop(0)
        if depth >= max_hops:
            continue

        current = nodes.get(current_room, {})
        current_wings = set(current.get("wings", []))

        # Find all rooms that share a wing with current room
        for room, data in nodes.items():
            if room in visited:
                continue
            shared_wings = current_wings & set(data["wings"])
            if shared_wings:
                visited.add(room)
                results.append(
                    {
                        "room": room,
                        "wings": data["wings"],
                        "halls": data["halls"],
                        "count": data["count"],
                        "hop": depth + 1,
                        "connected_via": sorted(shared_wings),
                    }
                )
                if depth + 1 < max_hops:
                    frontier.append((room, depth + 1))

    # Sort by relevance (hop distance, then count)
    results.sort(key=lambda x: (x["hop"], -x["count"]))
    return results[:50]  # cap results


def find_tunnels(wing_a: str = None, wing_b: str = None, col=None, config=None):
    """
    Find rooms that connect two wings (or all tunnel rooms if no wings specified).
    These are the "hallways" — same named idea appearing in multiple domains.
    """
    nodes, edges = build_graph(col, config)

    tunnels = []
    for room, data in nodes.items():
        wings = data["wings"]
        if len(wings) < 2:
            continue

        if wing_a and wing_a not in wings:
            continue
        if wing_b and wing_b not in wings:
            continue

        tunnels.append(
            {
                "room": room,
                "wings": wings,
                "halls": data["halls"],
                "count": data["count"],
                "recent": data["dates"][-1] if data["dates"] else "",
            }
        )

    tunnels.sort(key=lambda x: -x["count"])
    return tunnels[:50]


def graph_stats(col=None, config=None):
    """Summary statistics about the Anaktoron graph."""
    nodes, edges = build_graph(col, config)

    tunnel_rooms = sum(1 for n in nodes.values() if len(n["wings"]) >= 2)
    wing_counts = Counter()
    for data in nodes.values():
        for w in data["wings"]:
            wing_counts[w] += 1

    return {
        "total_rooms": len(nodes),
        "tunnel_rooms": tunnel_rooms,
        "total_edges": len(edges),
        "rooms_per_wing": dict(wing_counts.most_common()),
        "top_tunnels": [
            {"room": r, "wings": d["wings"], "count": d["count"]}
            for r, d in sorted(nodes.items(), key=lambda x: -len(x[1]["wings"]))[:10]
            if len(d["wings"]) >= 2
        ],
    }


def _fuzzy_match(query: str, nodes: dict, n: int = 5):
    """Find rooms that approximately match a query string."""
    query_lower = query.lower()
    scored = []
    for room in nodes:
        # Simple substring matching
        if query_lower in room:
            scored.append((room, 1.0))
        elif any(word in room for word in query_lower.split("-")):
            scored.append((room, 0.5))
    scored.sort(key=lambda x: -x[1])
    return [r for r, _ in scored[:n]]
