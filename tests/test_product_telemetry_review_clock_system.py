"""Headless clock selection stays local and cannot bypass a failed native probe."""

import os
import sys

import pytest

from mnemion.product_telemetry import review_clock, review_clock_system as system

UUID = b"12345678-90ab-cdef-1234-567890abcdef"


def test_absent_helper_uses_os_clock_without_compiling_or_initializing(tmp_path, monkeypatch):
    calls = []
    expected = {"epoch": UUID.replace(b"-", b"").decode(), "elapsed_ms": 1234}
    monkeypatch.setattr(review_clock, "__file__", str(tmp_path / "review_clock.py"))
    monkeypatch.setattr(review_clock, "_native", None)
    monkeypatch.setattr(
        system, "_reader", lambda: lambda initialize: calls.append(initialize) or expected
    )
    assert review_clock.read_review_clock() == expected
    assert review_clock.read_review_clock(initialize=True) == expected
    assert calls == [False, True]


def test_existing_broken_helper_does_not_fall_back(tmp_path, monkeypatch):
    (tmp_path / "network-state.node").write_bytes(b"invalid")
    monkeypatch.setattr(review_clock, "__file__", str(tmp_path / "review_clock.py"))
    monkeypatch.setattr(review_clock, "_native", None)
    monkeypatch.setattr(
        system, "_reader", lambda: pytest.fail("a broken addon is not an absent addon")
    )
    assert review_clock.read_review_clock() is None
    assert review_clock.read_review_clock(initialize=True) is None


def test_valid_native_probe_unavailability_is_not_overridden(monkeypatch):
    import ctypes

    class Clock(ctypes.Structure):
        _fields_ = [("elapsed_ms", ctypes.c_uint64), ("epoch", ctypes.c_ubyte * 16)]

    monkeypatch.setattr(review_clock, "_native", (object(), lambda *args: 0, Clock))
    monkeypatch.setattr(
        system, "_reader", lambda: pytest.fail("native refusal must remain unavailable")
    )
    assert review_clock.read_review_clock(initialize=True) is None


@pytest.mark.parametrize("value", [0, 1, "true", None, {}, []])
def test_invalid_initialize_never_opens_os_state(value, monkeypatch):
    monkeypatch.setattr(
        system, "_reader", lambda: pytest.fail("invalid input cannot open OS state")
    )
    assert system.read_system_review_clock(initialize=value) is None
    assert review_clock.read_review_clock(initialize=value) is None


@pytest.mark.skipif(sys.platform != "linux", reason="Uses Linux no-follow and CLOCK_BOOTTIME")
@pytest.mark.parametrize(
    "value", [UUID + b"\n", UUID.upper() + b"\n", UUID, UUID + b"\nextra", b"0" * 37, b"x" * 1000]
)
def test_linux_literal_epoch_read_is_bounded_and_strict(value, tmp_path, monkeypatch):
    path = tmp_path / "boot-id"
    path.write_bytes(value)
    opened = os.open
    observed = []

    def open_epoch(name, flags):
        observed.append((name, flags))
        return opened(path, flags)

    monkeypatch.setattr(system.os, "open", open_epoch)
    monkeypatch.setattr(system, "_reader", lambda: system._linux)
    monkeypatch.setattr(
        system.time,
        "clock_gettime_ns",
        lambda source: (
            1234999999 if source == system.time.CLOCK_BOOTTIME else pytest.fail("wrong clock")
        ),
    )
    result = system.read_system_review_clock()
    if value in (UUID + b"\n", UUID.upper() + b"\n"):
        assert result == {"epoch": UUID.replace(b"-", b"").decode(), "elapsed_ms": 1234}
    else:
        assert result is None
    assert len(observed) == 1
    assert observed[0][0] == "/proc/sys/kernel/random/boot_id"
    assert observed[0][1] & os.O_NOFOLLOW
    assert observed[0][1] & os.O_CLOEXEC


@pytest.mark.skipif(sys.platform != "linux", reason="Uses Linux no-follow")
def test_linux_does_not_follow_a_substituted_epoch_symlink(tmp_path, monkeypatch):
    target, link = tmp_path / "target", tmp_path / "link"
    target.write_bytes(UUID + b"\n")
    link.symlink_to(target)
    opened = os.open
    monkeypatch.setattr(system.os, "open", lambda name, flags: opened(link, flags))
    monkeypatch.setattr(system, "_reader", lambda: system._linux)
    assert system.read_system_review_clock() is None


@pytest.mark.parametrize(
    "clock",
    [
        None,
        {"epoch": "0" * 32, "elapsed_ms": 0},
        {"epoch": "a" * 32, "elapsed_ms": -1},
        {"epoch": "a" * 32, "elapsed_ms": 2**53},
    ],
)
def test_unavailable_or_out_of_range_system_clock_stays_unavailable(clock, monkeypatch):
    monkeypatch.setattr(system, "_reader", lambda: lambda initialize: clock)
    assert system.read_system_review_clock() is None
