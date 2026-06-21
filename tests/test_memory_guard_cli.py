import json
import sqlite3
from argparse import Namespace

from mnemion.cli import cmd_memory_guard
from mnemion.memory_guard import MemoryGuard
from mnemion.trust_lifecycle import DrawerTrust


def _seed_finding(db_path, drawer_id="drawer_guarded_001"):
    MemoryGuard(str(db_path))
    DrawerTrust(str(db_path)).create(drawer_id, "wing_test", "room_test")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """INSERT INTO memory_guard_findings
               (drawer_id, risk_type, score, reason, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                drawer_id,
                "privacy_exfiltration",
                0.85,
                "matched pattern: secret",
                "2026-05-06T00:00:00+00:00",
            ),
        )
        conn.commit()
    return drawer_id


def _args(anaktoron_path, action, **kwargs):
    base = {
        "palace": str(anaktoron_path),
        "memory_guard_action": action,
        "limit": 20,
        "json": True,
        "drawer_id": None,
        "dry_run": False,
        "apply": False,
    }
    base.update(kwargs)
    return Namespace(**base)


def test_memory_guard_status_and_review_omit_content(capsys, tmp_path):
    anaktoron = tmp_path / "anaktoron"
    anaktoron.mkdir()
    db_path = tmp_path / "knowledge_graph.sqlite3"
    drawer_id = _seed_finding(db_path)

    cmd_memory_guard(_args(anaktoron, "status"))
    status = json.loads(capsys.readouterr().out)
    cmd_memory_guard(_args(anaktoron, "review", limit=5, json=True))
    review = json.loads(capsys.readouterr().out)

    assert status["findings"] == 1
    assert status["by_risk_type"] == {"privacy_exfiltration": 1}
    assert review["findings"][0]["drawer_id"] == drawer_id
    assert set(review["findings"][0]) == {"drawer_id", "risk_type", "score", "created_at"}
    assert "secret" not in json.dumps(review).lower()


def test_memory_guard_quarantine_is_dry_run_unless_apply(capsys, tmp_path):
    anaktoron = tmp_path / "anaktoron"
    anaktoron.mkdir()
    db_path = tmp_path / "knowledge_graph.sqlite3"
    drawer_id = _seed_finding(db_path)
    trust = DrawerTrust(str(db_path))

    cmd_memory_guard(_args(anaktoron, "quarantine", drawer_id=drawer_id))
    dry_run = json.loads(capsys.readouterr().out)
    assert dry_run["status"] == "dry_run"
    assert trust.get(drawer_id)["status"] == "current"

    cmd_memory_guard(_args(anaktoron, "quarantine", drawer_id=drawer_id, apply=True))
    applied = json.loads(capsys.readouterr().out)

    assert applied["status"] == "quarantined"
    assert trust.get(drawer_id)["status"] == "quarantined"
