"""A complete atomic settings publication must not look like damaged JSON."""

import os

import pytest

from mnemion import local_state as state


@pytest.mark.parametrize("timing", ["before_open", "after_open"])
def test_read_reopens_a_record_replaced_during_open(tmp_path, monkeypatch, timing):
    if os.name == "nt" and timing == "after_open":
        pytest.skip("Windows refuses replacing an open descriptor without delete sharing")
    path, replacement = tmp_path / "configuration.json", tmp_path / "replacement.json"
    state.write(path, {"revision": 1})
    state.write(replacement, {"revision": 2})
    original_open, changed = state.os.open, False

    def publish_during_open(candidate, flags, *args, **kwargs):
        nonlocal changed
        if candidate == path and not changed:
            changed = True
            if timing == "before_open":
                os.replace(replacement, path)
            descriptor = original_open(candidate, flags, *args, **kwargs)
            if timing == "after_open":
                os.replace(replacement, path)
            return descriptor
        return original_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(state.os, "open", publish_during_open)
    assert state.read(path) == {"revision": 2}
    assert changed and state.read(path) == {"revision": 2}


def test_an_unsettled_settings_writer_is_bounded_and_retains_its_records(tmp_path, monkeypatch):
    path = tmp_path / "configuration.json"
    state.write(path, {"revision": 0})
    candidates = []
    for number in range(1, 5):
        candidate = tmp_path / f"replacement-{number}.json"
        state.write(candidate, {"revision": number})
        candidates.append(candidate)
    original_open, publications = state.os.open, []

    def publish_during_open(candidate, flags, *args, **kwargs):
        if candidate == path:
            replacement = candidates[len(publications)]
            publications.append(replacement)
            os.replace(replacement, path)
        return original_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(state.os, "open", publish_during_open)
    with pytest.raises(state.LocalSetupError) as error:
        state.read(path)
    assert error.value.code == "state_changed"
    assert len(publications) == 3
    monkeypatch.setattr(state.os, "open", original_open)
    assert state.read(path) == {"revision": 3}
    assert state.read(candidates[-1]) == {"revision": 4}


def test_reopening_never_accepts_a_permanent_link(tmp_path, monkeypatch):
    path, linked = tmp_path / "configuration.json", tmp_path / "linked.json"
    state.write(path, {"revision": 1})
    state.write(linked, {"revision": 2})
    replacement = tmp_path / "replacement.json"
    os.link(linked, replacement)
    original_open, changed = state.os.open, False

    def replace_with_link(candidate, flags, *args, **kwargs):
        nonlocal changed
        if candidate == path and not changed:
            changed = True
            os.replace(replacement, path)
        return original_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(state.os, "open", replace_with_link)
    with pytest.raises(state.LocalSetupError):
        state.read(path)
    assert path.stat().st_nlink == 2


def test_stable_damaged_json_is_retained_without_repair(tmp_path):
    path = tmp_path / "configuration.json"
    path.write_bytes(b'{"incomplete":')
    path.chmod(0o600)
    with pytest.raises(state.LocalSetupError) as error:
        state.read(path)
    assert error.value.code == "damaged_state"
    assert path.read_bytes() == b'{"incomplete":'
