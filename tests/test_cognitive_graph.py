from mnemion.trust_lifecycle import DrawerTrust, STATUS_SUPERSEDED


def test_extracts_structured_units_and_causal_edges(tmp_path):
    from mnemion.cognitive_graph import CognitiveGraph, extract_cognitive_units

    text = (
        "We switched to GraphQL because REST payloads caused dashboard latency. "
        "Always verify memories before answering. "
        "Alice prefers compact pricing dashboards. "
        "Goal: reduce pricing latency."
    )

    units, edges = extract_cognitive_units(
        drawer_id="drawer_a",
        text=text,
        metadata={"source_file": "notes.md", "timestamp": "2026-05-01T00:00:00Z"},
    )

    assert {"cause", "prescription", "preference", "objective"}.issubset(
        {unit.unit_type for unit in units}
    )
    assert edges
    assert edges[0].edge_type == "cause"

    graph = CognitiveGraph(str(tmp_path / "kg.sqlite3"))
    result = graph.upsert_drawer_units("drawer_a", units, edges)

    assert result["units_inserted"] == len(units)
    stored = graph.units_for_drawer("drawer_a")
    assert stored[0]["drawer_id"] == "drawer_a"
    assert graph.edges_for_drawer("drawer_a")[0]["edge_type"] == "cause"


def test_consolidation_is_idempotent_and_respects_trust(collection, tmp_path):
    from mnemion.cognitive_graph import CognitiveGraph

    kg_path = tmp_path / "kg.sqlite3"
    trust = DrawerTrust(str(kg_path))
    graph = CognitiveGraph(str(kg_path))

    collection.add(
        ids=["drawer_current", "drawer_old"],
        documents=[
            "The pricing dashboard uses GraphQL because REST was too slow.",
            "The pricing dashboard uses REST for all data.",
        ],
        metadatas=[
            {"wing": "project", "room": "decisions", "source_file": "a.md"},
            {"wing": "project", "room": "decisions", "source_file": "old.md"},
        ],
    )
    trust.create("drawer_current", wing="project", room="decisions")
    trust.create("drawer_old", wing="project", room="decisions")
    trust.update_status("drawer_old", STATUS_SUPERSEDED, reason="obsolete")

    first = graph.consolidate_collection(collection, trust=trust, limit=10)
    second = graph.consolidate_collection(collection, trust=trust, limit=10)

    assert first["drawers_consolidated"] == 2
    assert first["units_inserted"] > 0
    assert second["drawers_consolidated"] == 0
    old_units = graph.units_for_drawer("drawer_old")
    assert old_units
    assert {unit["trust_status"] for unit in old_units} == {"superseded"}


def test_consolidation_dry_run_does_not_write(collection, tmp_path):
    from mnemion.cognitive_graph import CognitiveGraph

    graph = CognitiveGraph(str(tmp_path / "kg.sqlite3"))
    collection.add(
        ids=["drawer_dry"],
        documents=["We should keep raw drawers as evidence for every proposition."],
        metadatas=[{"wing": "project", "room": "architecture"}],
    )

    result = graph.consolidate_collection(collection, limit=10, dry_run=True)

    assert result["would_consolidate"] == 1
    assert graph.units_for_drawer("drawer_dry") == []


def test_topic_tunnels_find_repeated_current_cues(collection, tmp_path):
    from mnemion.cognitive_graph import CognitiveGraph

    graph = CognitiveGraph(str(tmp_path / "kg.sqlite3"))
    collection.add(
        ids=["drawer_alpha", "drawer_beta", "drawer_gamma"],
        documents=[
            "Retrieval budgets should favor causal evidence.",
            "Retrieval scoring should include trust status.",
            "Renderer settings should keep canvas labels readable.",
        ],
        metadatas=[
            {"wing": "project", "room": "memory"},
            {"wing": "project", "room": "memory"},
            {"wing": "project", "room": "frontend"},
        ],
    )
    graph.consolidate_collection(collection, limit=10)

    tunnels = graph.topic_tunnels(min_count=2)

    retrieval = next(t for t in tunnels if t["cue"] == "retrieval")
    assert retrieval["drawer_count"] == 2
    assert retrieval["drawer_ids"] == ["drawer_alpha", "drawer_beta"]
    assert graph.tunnels_for_query("retrieval evidence", min_count=2)[0]["cue"] == "retrieval"
