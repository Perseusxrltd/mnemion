"""Clock changes cannot authorize a different process or hide the current one."""

import copy
import os
from types import SimpleNamespace

import psutil
import pytest

from mnemion import process_identity as identity


def test_current_process_matches_and_missing_fields_or_wrong_types_fail_closed():
    process = psutil.Process()
    marker = identity.capture(process)
    assert identity.matches(marker, process)
    for key, value in marker.items():
        missing = {name: item for name, item in marker.items() if name != key}
        assert not identity.matches(missing, process)
        wrong_type = dict(marker, **{key: str(value) if type(value) is not str else 1})
        assert not identity.matches(wrong_type, process)
    assert not identity.matches(dict(marker, format=True), process)
    assert not identity.matches(dict(marker, extra="unexpected"), process)


def test_linux_boot_and_start_counter_are_both_required(monkeypatch):
    monkeypatch.setattr(identity.sys, "platform", "linux")
    pid = os.getpid()
    boot = b"cd37aa06-18fc-46d0-a7b3-73503ec7469b\n"
    start = 123456

    def read(path, maximum):
        if path.name == "boot_id":
            return boot
        return (
            f"{pid} (name with ) parentheses\nand spaces) S ".encode()
            + b"0 " * 18
            + str(start).encode()
            + b" 0\n"
        )

    monkeypatch.setattr(identity, "_read", read)
    process = SimpleNamespace(pid=pid)
    marker = identity.capture(process)
    assert marker["ticks"] == start
    assert identity.matches(marker, process)
    start += 1
    assert not identity.matches(marker, process), "A reused PID cannot inherit readiness"
    start -= 1
    boot = b"bd37aa06-18fc-46d0-a7b3-73503ec7469b\n"
    assert not identity.matches(marker, process), "A different boot cannot inherit readiness"


@pytest.mark.parametrize("raw", [b"", b"7 (short) S 1", b"7 (name) S " + b"0 " * 18 + b"-1"])
def test_invalid_kernel_stat_is_not_a_process_identity(raw):
    with pytest.raises(ValueError):
        identity._start_ticks(raw, 7)


def test_non_linux_creation_time_and_legacy_records_remain_exact(monkeypatch):
    monkeypatch.setattr(identity.sys, "platform", "darwin")
    created = 100.5
    process = SimpleNamespace(pid=42, create_time=lambda: created)
    marker = identity.capture(process)
    record = {"created": created, "process_identity": marker}
    legacy = {"created": created}
    assert identity.matches_record(record, process, legacy_field="created")
    assert identity.matches_record(legacy, process, legacy_field="created")
    created += 0.01
    assert not identity.matches_record(record, process, legacy_field="created")
    assert not identity.matches_record(legacy, process, legacy_field="created")
    corrupted = copy.deepcopy(record)
    corrupted["process_identity"] = None
    corrupted["created"] = created
    assert not identity.matches_record(corrupted, process, legacy_field="created")


def test_kernel_reads_are_bounded(tmp_path):
    path = tmp_path / "stat"
    path.write_bytes(b"x" * 65)
    with pytest.raises(ValueError):
        identity._read(path, 64)


@pytest.mark.parametrize("created", [True, 0, -1, 2**1000, float("nan"), float("inf")])
def test_malformed_legacy_birth_is_rejected(created):
    process = psutil.Process()
    assert not identity.matches_record({"created": created}, process, legacy_field="created")
