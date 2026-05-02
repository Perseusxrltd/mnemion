from mnemion.trust_lifecycle import DrawerTrust, STATUS_SUPERSEDED


def test_reconstruct_returns_evidence_trail_and_respects_budget(collection, tmp_path):
    from mnemion.cognitive_graph import CognitiveGraph
    from mnemion.reconstruction import Reconstructor

    kg_path = tmp_path / "kg.sqlite3"
    graph = CognitiveGraph(str(kg_path))
    trust = DrawerTrust(str(kg_path))

    collection.add(
        ids=["drawer_graphql", "drawer_unrelated"],
        documents=[
            "The pricing dashboard moved to GraphQL because REST payloads caused latency.",
            "The frontend uses blue buttons in the settings page.",
        ],
        metadatas=[
            {"wing": "project", "room": "decisions", "source_file": "pricing.md"},
            {"wing": "project", "room": "frontend", "source_file": "ui.md"},
        ],
    )
    trust.bulk_create_default(
        [
            ("drawer_graphql", "project", "decisions"),
            ("drawer_unrelated", "project", "frontend"),
        ]
    )
    graph.consolidate_collection(collection, trust=trust, limit=10)

    result = Reconstructor(graph, collection).reconstruct(
        "Why did the pricing dashboard move to GraphQL?",
        budget=2,
    )

    assert result["query"] == "Why did the pricing dashboard move to GraphQL?"
    assert len(result["results"]) == 1
    assert result["results"][0]["id"] == "drawer_graphql"
    assert result["results"][0]["evidence_trail"]
    assert "pricing" in result["results"][0]["evidence_trail"][0]["matched_cues"]


def test_reconstruct_excludes_superseded_memory(collection, tmp_path):
    from mnemion.cognitive_graph import CognitiveGraph
    from mnemion.reconstruction import Reconstructor

    kg_path = tmp_path / "kg.sqlite3"
    graph = CognitiveGraph(str(kg_path))
    trust = DrawerTrust(str(kg_path))

    collection.add(
        ids=["drawer_current", "drawer_old"],
        documents=[
            "Current fact: the pricing dashboard uses GraphQL.",
            "Old fact: the pricing dashboard uses REST.",
        ],
        metadatas=[
            {"wing": "project", "room": "decisions"},
            {"wing": "project", "room": "decisions"},
        ],
    )
    trust.create("drawer_current", wing="project", room="decisions")
    trust.create("drawer_old", wing="project", room="decisions")
    trust.update_status("drawer_old", STATUS_SUPERSEDED, reason="obsolete")
    graph.consolidate_collection(collection, trust=trust, limit=10)

    result = Reconstructor(graph, collection).reconstruct("pricing dashboard REST", budget=5)

    assert [item["id"] for item in result["results"]] == ["drawer_current"]


def test_reconstruct_expands_through_topic_tunnels(collection, tmp_path):
    from mnemion.cognitive_graph import CognitiveGraph
    from mnemion.reconstruction import Reconstructor

    kg_path = tmp_path / "kg.sqlite3"
    graph = CognitiveGraph(str(kg_path))
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

    result = Reconstructor(graph, collection, topic_tunnel_min_count=2).reconstruct(
        "retrieval",
        budget=1,
    )

    assert [item["id"] for item in result["results"]] == ["drawer_alpha", "drawer_beta"]
    assert result["topic_tunnels"][0]["cue"] == "retrieval"
    tunneled = result["results"][1]["evidence_trail"][0]
    assert tunneled["via_topic_tunnel"] == "retrieval"
