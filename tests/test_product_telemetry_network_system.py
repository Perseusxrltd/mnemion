"""Source-install metering admission without changing real network settings."""

from __future__ import annotations

import ctypes
from types import SimpleNamespace

import pytest

from mnemion.product_telemetry import network, network_system


@pytest.fixture
def windows_hint(monkeypatch):
    state = {"fields": (3, 1, 0, 0, 0), "result": 0, "reads": 0, "loads": []}

    def hint(pointer):
        structure = hint.argtypes[0]._type_
        assert ctypes.sizeof(structure) == 12
        assert [getattr(structure, name).offset for name, _ in structure._fields_] == [
            0,
            4,
            8,
            9,
            10,
        ]
        # Fill the ABI buffer in Windows SDK field order, independently of the
        # Python names. This would catch a reversed level/cost declaration.
        raw = bytearray(12)
        raw[:4] = state["fields"][0].to_bytes(4, "little")
        raw[4:8] = state["fields"][1].to_bytes(4, "little")
        raw[8:11] = bytes(state["fields"][2:])
        ctypes.memmove(pointer, bytes(raw), len(raw))
        state["reads"] += 1
        return state["result"]

    def load(name, *, winmode):
        state["loads"].append((name, winmode))
        return SimpleNamespace(GetNetworkConnectivityHint=hint)

    monkeypatch.setattr(network_system, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(network_system, "_reader", None)
    monkeypatch.setattr(ctypes, "WinDLL", load, raising=False)
    return state


@pytest.mark.parametrize(
    "fields,expected",
    [
        ((3, 0, 0, 0, 0), 8),  # Unknown cost cannot grant unmetered access.
        ((3, 1, 0, 0, 0), 9),
        ((3, 2, 0, 0, 0), 10),
        ((3, 3, 0, 0, 0), 10),
        ((3, 4, 0, 0, 0), 12),
        ((3, 0xFFFFFFFF, 0, 0, 0), 12),
        ((3, 1, 1, 0, 0), 10),
        ((3, 1, 0, 1, 0), 10),
        ((3, 1, 0, 0, 1), 10),
        ((3, 4, 1, 0, 0), 14),
        ((0, 1, 0, 0, 0), 13),
        ((1, 1, 0, 0, 0), 13),
        ((2, 1, 0, 0, 0), 13),
        ((4, 1, 0, 0, 0), 13),
        ((0xFFFFFFFF, 2, 0, 0, 0), 14),
    ],
)
def test_documented_windows_hint_layout_and_cost_vetoes(windows_hint, fields, expected):
    windows_hint["fields"] = fields
    assert network_system.read_system_network_state() == expected
    assert windows_hint["loads"] == [("iphlpapi.dll", 0x800)]


@pytest.mark.parametrize("result,expected", [(1222, 12), (5, 0), (50, 0), (0xFFFFFFFF, 0)])
def test_os_errors_never_consume_an_unlimited_hint_buffer(windows_hint, result, expected):
    windows_hint["result"] = result
    assert network_system.read_system_network_state() == expected


def test_library_is_cached_but_every_owned_probe_reads_current_policy(windows_hint):
    assert network_system.read_system_network_state() == 9
    windows_hint["fields"] = (3, 2, 0, 0, 0)
    assert network_system.read_system_network_state() == 10
    assert windows_hint["reads"] == 2
    assert len(windows_hint["loads"]) == 1


@pytest.mark.parametrize("error", [OSError("unavailable"), AttributeError("older Windows")])
def test_missing_system_api_stays_unknown_without_a_different_loader(monkeypatch, error):
    calls = []

    def unavailable():
        calls.append(True)
        raise error

    monkeypatch.setattr(network_system, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(network_system, "_reader", None)
    monkeypatch.setattr(network_system, "_windows_reader", unavailable)
    assert network_system.read_system_network_state() == 0
    assert network_system.read_system_network_state() == 0
    assert calls == [True]


def test_unsupported_source_platform_does_not_load_a_windows_library(monkeypatch):
    def unexpected():
        pytest.fail("An unsupported OS must not activate the Windows path")

    monkeypatch.setattr(network_system, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(network_system, "_reader", None)
    monkeypatch.setattr(network_system, "_windows_reader", unexpected)
    assert network_system.read_system_network_state() == 0


def test_missing_package_helper_uses_direct_os_read_without_creating_state(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(network, "__file__", str(tmp_path / "network.py"))
    monkeypatch.setattr(network, "_native", None)
    monkeypatch.setattr(
        network_system, "read_system_network_state", lambda: calls.append(True) or 10
    )
    assert network.native_state() == 10
    assert network.native_state() == 10
    assert calls == [True, True]
    assert list(tmp_path.iterdir()) == []


def test_present_broken_package_helper_cannot_fall_back_to_unmetered(tmp_path, monkeypatch):
    def unexpected():
        pytest.fail("An existing broken helper must not be bypassed")

    (tmp_path / "network-state.node").write_bytes(b"invalid helper")
    monkeypatch.setattr(network, "__file__", str(tmp_path / "network.py"))
    monkeypatch.setattr(network, "_native", None)
    monkeypatch.setattr(network_system, "read_system_network_state", unexpected)
    assert network.native_state() == 0
    assert network.native_state() == 0


def test_package_inspection_denied_cannot_enable_the_direct_reader(tmp_path, monkeypatch):
    def denied(_):
        raise PermissionError("helper inspection denied")

    def unexpected():
        pytest.fail("Failure to inspect a helper is not evidence of its absence")

    monkeypatch.setattr(network, "__file__", str(tmp_path / "network.py"))
    monkeypatch.setattr(network, "_native", None)
    monkeypatch.setattr(network.Path, "lstat", denied)
    monkeypatch.setattr(network_system, "read_system_network_state", unexpected)
    assert network.native_state() == 0
