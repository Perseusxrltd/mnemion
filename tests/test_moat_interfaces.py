import json
from argparse import Namespace
from pathlib import Path


def test_cli_reconstruct_prints_json(monkeypatch, capsys, tmp_path):
    from mnemion import cli

    monkeypatch.setattr(
        "mnemion.reconstruction.reconstruct_query",
        lambda **_kwargs: {"query": "pricing", "results": [{"id": "drawer_1"}]},
    )

    cli.cmd_reconstruct(
        Namespace(query="pricing", budget=3, json=True, palace=str(tmp_path / "anaktoron"))
    )

    assert json.loads(capsys.readouterr().out)["results"][0]["id"] == "drawer_1"


def test_cli_reconstruct_human_output_shows_topic_tunnel(monkeypatch, capsys, tmp_path):
    from mnemion import cli

    monkeypatch.setattr(
        "mnemion.reconstruction.reconstruct_query",
        lambda **_kwargs: {
            "query": "retrieval",
            "topic_tunnels": [{"cue": "retrieval", "drawer_count": 2}],
            "results": [
                {
                    "id": "drawer_1",
                    "wing": "project",
                    "room": "memory",
                    "evidence_trail": [
                        {
                            "unit_type": "proposition",
                            "text": "Retrieval scoring includes trust status.",
                            "via_topic_tunnel": "retrieval",
                        }
                    ],
                }
            ],
        },
    )

    cli.cmd_reconstruct(
        Namespace(query="retrieval", budget=1, json=False, palace=str(tmp_path / "anaktoron"))
    )

    out = capsys.readouterr().out
    assert "Topic tunnels: retrieval (2 drawers)" in out
    assert "via tunnel: retrieval" in out


def test_sweep_can_consolidate_after_ingest(monkeypatch, capsys, tmp_path):
    from mnemion import cli

    calls = []
    monkeypatch.setattr(
        "mnemion.sweeper.sweep",
        lambda *_args, **_kwargs: {"filed": 2, "skipped_existing": 0, "files": 1, "seen": 2},
    )
    monkeypatch.setattr(
        cli,
        "_consolidate_anaktoron",
        lambda **kwargs: calls.append(kwargs)
        or {"drawers_consolidated": 2, "units_inserted": 4, "edges_inserted": 1},
    )

    cli.cmd_sweep(
        Namespace(
            path=str(tmp_path / "logs"),
            palace=str(tmp_path / "anaktoron"),
            wing="codex",
            batch_size=8,
            consolidate=True,
            consolidate_limit=25,
        )
    )

    assert calls == [{"anaktoron_path": str(tmp_path / "anaktoron"), "limit": 25}]
    assert "Consolidated: 2 drawers, 4 units, 1 edges" in capsys.readouterr().out


def test_mine_can_consolidate_after_ingest(monkeypatch, tmp_path):
    from mnemion import cli

    calls = []
    monkeypatch.setattr("mnemion.miner.mine", lambda **_kwargs: None)
    monkeypatch.setattr(
        cli,
        "_consolidate_anaktoron",
        lambda **kwargs: calls.append(kwargs) or {},
    )

    cli.cmd_mine(
        Namespace(
            dir=str(tmp_path / "project"),
            palace=str(tmp_path / "anaktoron"),
            mode="projects",
            wing=None,
            agent="mnemion",
            limit=0,
            dry_run=False,
            no_gitignore=False,
            include_ignored=[],
            extract="exchange",
            consolidate=True,
            consolidate_limit=100,
        )
    )

    assert calls == [{"anaktoron_path": str(tmp_path / "anaktoron"), "limit": 100}]


def test_mine_dry_run_does_not_consolidate(monkeypatch, tmp_path):
    from mnemion import cli

    calls = []
    monkeypatch.setattr("mnemion.miner.mine", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "_consolidate_anaktoron", lambda **kwargs: calls.append(kwargs))

    cli.cmd_mine(
        Namespace(
            dir=str(tmp_path / "project"),
            palace=str(tmp_path / "anaktoron"),
            mode="projects",
            wing=None,
            agent="mnemion",
            limit=0,
            dry_run=True,
            no_gitignore=False,
            include_ignored=[],
            extract="exchange",
            consolidate=True,
            consolidate_limit=100,
        )
    )

    assert calls == []


def test_cli_moat_eval_uses_isolated_eval_db_by_default(monkeypatch, capsys, tmp_path):
    from mnemion import cli

    calls = []

    def fake_run_moat_eval(**kwargs):
        calls.append(kwargs)
        return {
            "suite": kwargs["suite"],
            "kg_path": kwargs.get("kg_path"),
            "modes": [],
            "scores": {},
            "case_counts": {},
            "cases": {},
        }

    monkeypatch.setattr("mnemion.moat_eval.run_moat_eval", fake_run_moat_eval)

    cli.cmd_moat_eval(Namespace(suite="all", palace=str(tmp_path / "anaktoron")))

    assert calls == [{"suite": "all"}]
    assert json.loads(capsys.readouterr().out)["kg_path"] is None


def test_mcp_exposes_moat_tools():
    from mnemion.mcp_server import TOOLS

    for name in [
        "mnemion_reconstruct",
        "mnemion_consolidate",
        "mnemion_memory_guard_scan",
        "mnemion_get_evidence_trail",
    ]:
        assert name in TOOLS


def test_help_instructions_include_current_moat_tools():
    text = Path("mnemion/instructions/help.md").read_text(encoding="utf-8")

    assert "MCP Tools (19)" not in text
    assert "mnemion_reconstruct" in text
    assert "mnemion_consolidate" in text
    assert "mnemion_memory_guard_scan" in text
    assert "mnemion_eval" not in text
