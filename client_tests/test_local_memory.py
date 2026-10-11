from pathlib import Path

import pytest

from mnemion import local_state as state
from mnemion.local_memory import MemoryChange, configure, policy


def test_private_budget_survives_restart_and_rejects_a_stale_agent_write(tmp_path):
    root = state.directory(tmp_path / "workspace")
    state.write(root / "configuration.json", {"format": 1})
    first = configure(
        root, MemoryChange(mode="manual", limit_mib=1024, expected_revision="default")
    )
    second = configure(
        root, MemoryChange(mode="manual", limit_mib=512, expected_revision=first["revision"])
    )
    assert policy(Path(str(root)))["settings"] == {"mode": "manual", "limit_mib": 512}
    with pytest.raises(state.LocalSetupError) as caught:
        configure(root, MemoryChange(mode="auto", expected_revision=first["revision"]))
    assert caught.value.code == "memory_policy_changed"
    assert policy(root) == second


def test_damaged_policy_never_silently_resets_to_automatic(tmp_path):
    root = state.directory(tmp_path / "workspace")
    state.directory(root / "resource-policy")
    state.write(
        root / "resource-policy/memory.json",
        {"format": 1, "revision": "fixture", "settings": {"mode": "manual", "limit_mib": -1}},
    )
    with pytest.raises(state.LocalSetupError) as caught:
        policy(root)
    assert caught.value.code == "memory_policy_damaged"
