"""Source checks for diagnostic owned-launch accounting.

The lifecycle case is the adapter's own self-check. It is not resource acceptance.
"""

import json
import sys
from pathlib import Path

import pytest

from deploy.owned_launch_accounting import (
    ADDITIONAL_RSS_BUDGET_BYTES,
    CPU_BUDGET_ONE_CORE_FRACTION,
    OwnedLaunch,
    OwnedLaunchError,
    _Ledger,
    combine_active_cpu,
    installed_journey_boundary,
)
from deploy.owned_launch_self_check import run_self_check


def test_active_cpu_keeps_missing_counters_null_and_keeps_a_measured_zero():
    missing = combine_active_cpu([
        {"active": True, "cpu_start": 10, "cpu_end": None, "start_ns": 0, "end_ns": 1000},
    ])
    assert missing == {"cpu_microseconds": None, "wall_microseconds": None}
    measured = combine_active_cpu([
        {"active": True, "cpu_start": 10, "cpu_end": 10, "start_ns": 0, "end_ns": 0},
        {"active": False, "cpu_start": 10, "cpu_end": 90, "start_ns": 0, "end_ns": 5_000_000},
    ])
    assert measured == {"cpu_microseconds": 0, "wall_microseconds": 0}
    assert combine_active_cpu([
        {"active": False, "cpu_start": 0, "cpu_end": 50, "start_ns": 0, "end_ns": 1000},
    ])["cpu_microseconds"] is None


def test_negative_cpu_delta_is_unavailable_rather_than_clamped():
    assert combine_active_cpu([
        {"active": True, "cpu_start": 20, "cpu_end": 10, "start_ns": 0, "end_ns": 1000},
    ])["cpu_microseconds"] is None


def test_settlement_cannot_be_marked_active():
    backend = _FakeBackend()
    launch = OwnedLaunch(backend, bound_seconds=5, sample_seconds=0.02)
    try:
        with pytest.raises(OwnedLaunchError):
            launch.mark_phase("settlement", canonical_operations_completed=1, active=True)
        with pytest.raises(OwnedLaunchError):
            launch.mark_phase("send-settlement", canonical_operations_completed=1, active=True)
    finally:
        launch.finish()


def test_report_keeps_commit_and_cold_start_out_of_rss_acceptance():
    backend = _FakeBackend()
    launch = OwnedLaunch(backend, bound_seconds=5, sample_seconds=0.02)
    launch.mark_phase("canonical-work", canonical_operations_completed=0, active=True)
    backend.cpu = 8_000
    report = launch.finish(canonical_operations_completed=1)
    assert report["resource_acceptance"] is False
    assert report["budget"]["status"] == "UNACCEPTED"
    assert report["budget"]["compared"] is False
    assert report["budget"]["additional_rss_bytes_per_process"] == ADDITIONAL_RSS_BUDGET_BYTES
    assert report["budget"]["cpu_one_core_fraction"] == CPU_BUDGET_ONE_CORE_FRACTION
    assert report["cold_start"]["subtracted"] is False
    assert report["active_cpu_microseconds"] == 7_000
    assert report["kernel"]["peak_job_commit_bytes"] == 123456789
    assert report["kernel"]["commit_counters_are_working_set"] is False
    encoded = json.dumps(report)
    assert "123456789" not in encoded.split("peak_job_commit_bytes")[0]
    assert report["missing_recorded_as_zero"] is False
    assert "unseen_or_unsampled_process_working_set" in report["unavailable_counters"]
    with pytest.raises(OwnedLaunchError):
        launch.finish()


def test_missing_active_counter_is_not_zero():
    backend = _FakeBackend()
    backend.cpu = None
    launch = OwnedLaunch(backend, bound_seconds=5, sample_seconds=0.02)
    launch.mark_phase("canonical-work", canonical_operations_completed=0, active=True)
    report = launch.finish(canonical_operations_completed=1)
    assert report["active_cpu_microseconds"] is None
    assert report["active_core_fraction"] is None
    assert report["lifetime_cpu_microseconds"] == 5_000


def test_installed_launcher_is_not_wired_and_budget_is_unchanged():
    boundary = installed_journey_boundary()
    assert boundary["wired_into_smoke_installed_hosting"] is False
    launcher = Path("studio/electron/scripts/smoke-installed-hosting.mjs").read_text(encoding="utf-8")
    assert "owned_launch" not in launcher
    assert "start_owned_launch" not in launcher
    disclosure = json.loads(Path("mnemion/product_telemetry/disclosure.json").read_text(encoding="utf-8"))
    assert "owned_launch" not in json.dumps(disclosure)


def test_ledger_does_not_reuse_a_pid_identity_or_invent_rss():
    ledger = _Ledger()
    ledger.add_identity(15, 100)
    ledger.observe(15, 200, current=None, high_water=None)
    assert [row["identity"] for row in ledger.public()] == ["15:100", "15:200"]
    assert ledger.public()[1]["peak_working_set_bytes"] is None


def test_owned_launch_lifecycle_self_check():
    result = run_self_check()
    assert result["held"] is True
    assert result["resource_acceptance"] is False
    assert result["platform"] == sys.platform


class _FakeBackend:
    def __init__(self):
        self.ledger = _Ledger()
        self.ledger.add_identity(4, 10)
        self.cpu = 1_000

    def cpu_microseconds(self):
        return self.cpu

    def sample(self, ledger):
        return None

    def still_active(self):
        return False

    def wait_root(self, _timeout):
        return True

    def terminate(self):
        return True, None

    def snapshot(self):
        return {
            "method": "fake",
            "cpu_microseconds": 5_000,
            "identities_missing": 1,
            "observer_in_measured_group": False,
            "sampled_peaks": {"sampled_pid_cpu_is_complete": False},
            "kernel": {
                "peak_job_commit_bytes": 123456789,
                "commit_counters_are_working_set": False,
            },
            "cpu_complete": True,
            "unavailable": [],
        }

    def coverage(self, _snapshot, _ledger):
        return {
            "platform": "windows",
            "status": "partial",
            "cpu_lifetime_complete": True,
            "cpu_includes_exited_descendants": True,
            "sampled_pid_cpu_is_complete": False,
            "rss_high_water": "unavailable",
            "rss_high_water_covers_unseen_exited_processes": False,
            "cgroup_memory_peak_is_per_process_rss": False,
        }

    def close(self):
        return True, None
