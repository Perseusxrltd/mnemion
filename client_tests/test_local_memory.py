from pathlib import Path

import pytest

from mnemion import local_state as state
from mnemion.local_memory import MemoryChange, configure, policy


def test_private_budget_survives_restart_and_rejects_a_stale_agent_write(tmp_path):
    root = state.directory(tmp_path / "workspace")
    state.write(root / "configuration.json", {"format": 1})
    first = configure(root, MemoryChange(mode="manual", limit_mib=1024), initial=True)
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


def configured(tmp_path):
    root = state.directory(tmp_path / "workspace")
    state.write(root / "configuration.json", {"format": 1})
    configure(root, MemoryChange(mode="manual", limit_mib=768), initial=True)
    return root, root / "resource-policy/memory.json"


@pytest.mark.parametrize(
    "content",
    [
        b'{"settings":',
        b"[]",
        b"null",
        b"\xff\xfe",
        b'{"format": 1, "revision": "", "settings": {}}',
    ],
)
def test_explicit_repair_preserves_damage_and_private_permissions(tmp_path, content):
    import os
    from mnemion.local_memory import MemoryRepair, inspection, repair

    root, path = configured(tmp_path)
    path.write_bytes(content)
    before = inspection(root)
    assert before["memory_policy"] is None
    assert before["memory_recovery"]["code"] == "memory_policy_damaged"
    with pytest.raises(state.LocalSetupError):
        configure(root, MemoryChange(mode="auto"))
    assert path.read_bytes() == content
    value = repair(
        root,
        MemoryRepair(
            mode="manual", limit_mib=512, repair_token=before["memory_recovery"]["repair_token"]
        ),
    )
    assert policy(root) == value
    assert value["settings"] == {"mode": "manual", "limit_mib": 512}
    assert inspection(root)["memory_recovery"] is None
    archives = list((path.parent / "recovery").glob("memory-*.bin"))
    assert len(archives) == 1
    assert archives[0].read_bytes() == content
    if os.name != "nt":
        assert path.stat().st_mode & 0o077 == archives[0].stat().st_mode & 0o077 == 0
    else:
        from client_tests.windows_acl import assert_private_acl

        assert_private_acl(path)
        assert_private_acl(archives[0])


@pytest.mark.parametrize(
    "next_content",
    [
        b"new invalid bytes",
        b'{"format":1,"revision":"restored","settings":{"mode":"manual","limit_mib":1024}}',
    ],
)
def test_repair_rejects_changed_damage_and_a_restored_valid_policy(tmp_path, next_content):
    from mnemion.local_memory import MemoryRepair, inspection, repair

    root, path = configured(tmp_path)
    path.write_bytes(b"original damage")
    token = inspection(root)["memory_recovery"]["repair_token"]
    path.write_bytes(next_content)
    with pytest.raises(state.LocalSetupError) as caught:
        repair(root, MemoryRepair(mode="auto", repair_token=token))
    assert caught.value.code == "memory_policy_changed"
    assert path.read_bytes() == next_content
    assert not (path.parent / "recovery").exists()


def test_same_bytes_at_a_different_file_identity_need_new_inspection(tmp_path):
    import os
    from mnemion.local_memory import MemoryRepair, inspection, repair
    from mnemion.private_output import private_output

    root, path = configured(tmp_path)
    path.write_bytes(b"damage")
    token = inspection(root)["memory_recovery"]["repair_token"]
    replacement = path.with_name("replacement")
    with private_output(replacement) as stream:
        stream.write(b"damage")
    os.replace(replacement, path)
    with pytest.raises(state.LocalSetupError) as caught:
        repair(root, MemoryRepair(mode="auto", repair_token=token))
    assert caught.value.code == "memory_policy_changed"
    assert path.read_bytes() == b"damage"


def test_missing_policy_needs_explicit_repair_and_stale_repair_cannot_overwrite_it(tmp_path):
    from mnemion.local_memory import MemoryRepair, inspection, repair

    root, path = configured(tmp_path)
    path.unlink()
    view = inspection(root)
    assert view["memory_recovery"]["code"] == "memory_policy_missing"
    with pytest.raises(state.LocalSetupError) as caught:
        configure(root, MemoryChange(mode="auto", expected_revision="default"))
    assert caught.value.code == "memory_policy_missing"
    change = MemoryRepair(
        mode="manual", limit_mib=384, repair_token=view["memory_recovery"]["repair_token"]
    )
    saved = repair(root, change)
    assert saved["settings"]["limit_mib"] == 384
    with pytest.raises(state.LocalSetupError) as caught:
        repair(root, change)
    assert caught.value.code == "memory_policy_changed"
    assert policy(root) == saved
    assert not (path.parent / "recovery").exists()


def test_repair_refuses_links_oversize_and_nonprivate_records(tmp_path):
    import os
    from mnemion.local_memory import MemoryRepair, inspection, repair

    root, path = configured(tmp_path)
    path.write_bytes(b"damage")
    token = inspection(root)["memory_recovery"]["repair_token"]
    alias = path.with_name("linked")
    os.link(path, alias)
    assert inspection(root)["memory_recovery"]["repair_token"] is None
    with pytest.raises(state.LocalSetupError):
        repair(root, MemoryRepair(mode="auto", repair_token=token))
    alias.unlink()
    path.write_bytes(b"x" * (state.MAX_RECORD_BYTES + 1))
    assert inspection(root)["memory_recovery"]["repair_token"] is None
    with pytest.raises(state.LocalSetupError):
        repair(root, MemoryRepair(mode="auto", repair_token=token))
    if os.name != "nt":
        path.write_bytes(b"damage")
        path.chmod(0o644)
        assert inspection(root)["memory_recovery"]["repair_token"] is None
        with pytest.raises(state.LocalSetupError):
            repair(root, MemoryRepair(mode="auto", repair_token=token))
    assert not (path.parent / "recovery").exists()


def test_failed_repair_keeps_damage_and_preserves_exact_recovery_copy(tmp_path, monkeypatch):
    import os
    from mnemion.local_memory import MemoryRepair, inspection, repair

    root, path = configured(tmp_path)
    path.write_bytes(b"damage to preserve")
    token = inspection(root)["memory_recovery"]["repair_token"]

    def failed_replace(*args):
        raise OSError("simulated interrupted replacement")

    monkeypatch.setattr(os, "replace", failed_replace)
    with pytest.raises(OSError):
        repair(root, MemoryRepair(mode="auto", repair_token=token))
    assert path.read_bytes() == b"damage to preserve"
    assert [copy.read_bytes() for copy in (path.parent / "recovery").iterdir()] == [
        b"damage to preserve"
    ]
    assert not list(path.parent.glob(".local-state-*"))
    assert inspection(root)["memory_recovery"]["repair_token"] == token


def test_repair_cannot_replace_damage_when_archive_cannot_be_preserved(tmp_path, monkeypatch):
    from mnemion.local_memory import MemoryRepair, inspection, repair

    root, path = configured(tmp_path)
    path.write_bytes(b"damage")
    token = inspection(root)["memory_recovery"]["repair_token"]
    original = state.private_output

    def unavailable(destination):
        if destination.parent.name == "recovery":
            raise OSError("simulated disk full")
        return original(destination)

    monkeypatch.setattr(state, "private_output", unavailable)
    with pytest.raises(OSError):
        repair(root, MemoryRepair(mode="auto", repair_token=token))
    assert path.read_bytes() == b"damage"


def test_repair_history_keeps_recent_private_damage_only(tmp_path):
    from mnemion.local_memory import MemoryRepair, inspection, repair

    root, path = configured(tmp_path)
    for index in range(11):
        path.write_bytes(f"damage {index}".encode())
        token = inspection(root)["memory_recovery"]["repair_token"]
        repair(root, MemoryRepair(mode="auto", repair_token=token))
    copies = list((path.parent / "recovery").glob("memory-*.bin"))
    assert len(copies) == 8
    assert {p.read_bytes() for p in copies} == {f"damage {i}".encode() for i in range(3, 11)}


def test_missing_repair_token_is_bound_to_the_inspected_workspace(tmp_path):
    from mnemion.local_memory import MemoryRepair, inspection, repair

    left = state.directory(tmp_path / "left")
    right = state.directory(tmp_path / "right")
    for root in (left, right):
        state.write(root / "configuration.json", {"format": 1})
    token = inspection(left)["memory_recovery"]["repair_token"]
    assert token != inspection(right)["memory_recovery"]["repair_token"]
    with pytest.raises(state.LocalSetupError) as caught:
        repair(right, MemoryRepair(mode="auto", repair_token=token))
    assert caught.value.code == "memory_policy_changed"
    assert not (right / "resource-policy/memory.json").exists()
    assert (
        repair(left, MemoryRepair(mode="manual", limit_mib=512, repair_token=token))["settings"][
            "limit_mib"
        ]
        == 512
    )
