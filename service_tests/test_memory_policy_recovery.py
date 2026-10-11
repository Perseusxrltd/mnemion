"""Local operator recovery stays usable before startup and while admission is paused."""

import json
from pathlib import Path
import subprocess
import sys

from mnemion import local_memory, local_state as state, local_workspace
from mnemion.service.memory_budget import GIB, MIB, MemoryBudget, MemoryOptions, MemorySample


def fixture(tmp_path):
    root = state.directory(tmp_path / "Workspace Équipe")
    local_workspace.initialize(
        root,
        local_workspace.SetupOptions(
            memory=MemoryOptions(mode="manual", limit_mib=768),
            workspace_name="Recovery workspace",
            owner_name="Owner",
        ),
    )
    return root, root / "resource-policy/memory.json"


def test_monitor_retains_manual_budget_through_damage_missing_and_explicit_repair(tmp_path):
    root, path = fixture(tmp_path)
    budget = MemoryBudget(sample=lambda: MemorySample(8 * GIB, 5 * GIB, 100 * MIB))
    events = []
    monitor = local_memory.MemoryMonitor(root, budget, events.append)
    monitor.tick()
    original = budget.snapshot()
    assert original["requested_limit_mib"] == 768
    assert original["background_paused"] is False
    path.write_bytes(b"{broken")
    monitor.tick()
    view = local_workspace.inspect(root)
    assert view["configured"] is True
    assert view["settings"]["workspace_name"] == "Recovery workspace"
    assert view["memory_policy"] is None
    assert view["memory_recovery"]["repair_token"]
    damaged = budget.snapshot()
    assert damaged["requested_limit_mib"] == 768
    assert damaged["revision"] == original["revision"]
    assert damaged["reason"] == "policy_unavailable"
    assert budget.can_start_background() is False
    path.unlink()
    monitor.tick()
    assert budget.snapshot()["reason"] == "policy_unavailable"
    token = local_workspace.inspect(root)["memory_recovery"]["repair_token"]
    repaired = local_memory.repair(
        root, local_memory.MemoryRepair(mode="manual", limit_mib=512, repair_token=token)
    )
    assert (
        budget.snapshot()["reason"] == "policy_unavailable"
    )  # Acknowledged write is not adoption.
    monitor.tick()
    assert budget.snapshot()["revision"] == repaired["revision"]
    assert budget.snapshot()["requested_limit_mib"] == 512
    assert budget.snapshot()["background_paused"] is False
    monitor.close()


def test_json_operator_status_repair_and_stale_request_without_database_start(tmp_path):
    root, path = fixture(tmp_path)
    path.write_bytes(b"private damaged content must never appear in status")

    def command(action, change=None):
        result = subprocess.run(
            [sys.executable, "-m", "mnemion.service.cli", "local", action, "--root", str(root)],
            cwd=Path(__file__).resolve().parents[1],
            input=json.dumps(change) if change else "",
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert not result.stderr
        assert "private damaged content" not in result.stdout
        return result.returncode, json.loads(result.stdout)

    code, view = command("status")
    assert code == 0
    assert view["configured"] is True
    assert view["memory_policy"] is None
    token = view["memory_recovery"]["repair_token"]
    code, denied = command("memory", {"mode": "auto", "limit_mib": None})
    assert code == 1 and denied["code"] == "memory_policy_damaged"
    change = {"mode": "manual", "limit_mib": 512, "repair_token": token}
    code, saved = command("memory-repair", change)
    assert code == 0 and saved["event"] == "memory_policy"
    assert saved["apply_within_seconds"] == 2
    assert not (root / "database").exists()
    code, stale = command("memory-repair", change)
    assert code == 1 and stale["code"] == "memory_policy_changed"
    code, final = command("status")
    assert code == 0 and final["memory_recovery"] is None
    assert final["memory_policy"]["settings"]["limit_mib"] == 512
