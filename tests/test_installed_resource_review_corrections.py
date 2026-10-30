"""Changed-behavior checks for the installed resource review corrections."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from deploy.owned_installed_launch import finalize_owned_launch
from deploy.owned_launch_accounting import OwnedLaunchError
from deploy.probe_telemetry_installed import (
    installed_resource_case_completed,
    note_resource_ingress,
    read_resource_profile_store,
    select_owned_observer,
)
from deploy.report_telemetry_renderer import (
    OwnedPhaseCursor,
    apply_owned_marker,
    retain_owned_launch,
)
from deploy.report_telemetry_renderer import absorb_reviewed_chunk
from mnemion.product_telemetry.wire_v3 import PACKET_BYTES


CHECKPOINTS = [
    "before_workspace_connect",
    "workspace_connected",
    "first_memory_cycle_and_delivery",
    "8_memory_cycles",
    "16_memory_cycles",
    "32_memory_cycles",
    "64_memory_cycles",
    "96_memory_cycles",
    "128_memory_cycles",
]


class _Marks:
    def __init__(self, fail=False):
        self.marks = []
        self.fail = fail

    def mark_phase(self, name, *, canonical_operations_completed, active):
        self.marks.append(name)
        if self.fail:
            raise OwnedLaunchError("invalid_phase")


class _Finish:
    def __init__(self):
        self.calls = 0

    def mark_phase(self, name, *, canonical_operations_completed, active):
        raise RuntimeError(r"C:\secret\marker")

    def finish(self, *, canonical_operations_completed=None):
        self.calls += 1
        return {
            "lifetime_cpu_microseconds": 10,
            "cleanup": {"ok": True, "failure": None, "retried": False},
            "canonical_operations_completed": canonical_operations_completed,
        }


def _memory_case(**overrides):
    evidence = {
        "memory_cycles": 128,
        "memory_results_verified": True,
        "checkpoints": CHECKPOINTS,
        "model_calls": 0,
        "resource_acceptance": False,
        "condition": "enabled",
        "memory_api_operations": 384,
        "telemetry_attempts": 1,
        "telemetry_reserved_bytes": 65536,
        "telemetry_events": [{"malformed": False, "body_hex": bytes(PACKET_BYTES).hex()}],
        "memory_successful": 384,
        "inspected_body_hex": None,
    }
    evidence.update(overrides)
    return evidence


def test_os_environ_selects_the_observer(monkeypatch):
    assert type(os.environ) is not dict
    monkeypatch.setenv("MNEMION_OWNED_LAUNCH_PYTHON", r"C:\client\python.exe")
    monkeypatch.setenv("MNEMION_ENGINE_PYTHON", r"C:\engine\python.exe")
    chosen = select_owned_observer(os.environ, platform_name="win32")
    assert chosen == r"C:\client\python.exe"
    try:
        select_owned_observer(["not-a-mapping"], platform_name="linux")
    except RuntimeError as error:
        assert "MNEMION_OWNED_LAUNCH_PYTHON" in str(error)
    else:
        raise AssertionError("a list is not an environment mapping")


def test_overflow_is_visible_and_does_not_clear_none():
    captured, _chunks = absorb_reviewed_chunk(bytearray(), 0, b"x" * (PACKET_BYTES + 1))
    assert captured is None
    counts = {"malformed_body": 0}
    event = note_resource_ingress(captured, [], counts)
    assert event["malformed"] is True
    assert event["body_hex"] is None
    assert counts["malformed_body"] == 1
    short = bytearray(b"abcd")
    rejected = note_resource_ingress(short, [], counts)
    assert rejected["malformed"] is True
    assert short == bytearray()
    body = bytes(PACKET_BYTES)
    assert len(body) == 25
    held = bytearray(body)
    reviewed = []
    kept = note_resource_ingress(held, reviewed, counts)
    assert kept["malformed"] is False
    assert kept["body_hex"] == body.hex()
    assert reviewed == [body.hex()]
    assert held == bytearray()


def test_unknown_progress_is_retained_with_the_lower_bound():
    launch = _Marks()
    cursor = OwnedPhaseCursor()
    apply_owned_marker(launch, {"phase": "96_memory_cycles"}, cursor)
    apply_owned_marker(
        launch,
        {"phase": "finished", "completed": 128, "completed_known": False},
        cursor,
    )
    apply_owned_marker(
        launch,
        {"phase": "closed", "completed": 96, "completed_known": False},
        cursor,
    )
    assert cursor.completed == 96
    assert cursor.completed_known is False
    assert launch.marks == ["96-memory-cycles", "finished", "closed"]
    retained = retain_owned_launch(
        {
            "canonical_operations_completed": cursor.completed,
            "canonical_operations_known": cursor.completed_known,
            "lifetime_cpu_microseconds": None,
        }
    )
    assert retained["canonical_operations_completed"] == 96
    assert retained["canonical_operations_known"] is False
    assert retained["lifetime_cpu_microseconds"] is None
    fresh = OwnedPhaseCursor()
    apply_owned_marker(
        _Marks(),
        {"phase": "failed", "completed": 40, "completed_known": False},
        fresh,
    )
    assert fresh.completed == 40
    assert fresh.completed_known is False


def test_failed_marker_is_not_consumed_and_finish_still_runs_once():
    launch = _Marks(fail=True)
    cursor = OwnedPhaseCursor()
    apply_owned_marker(launch, {"phase": "measuring"}, cursor)
    apply_owned_marker(launch, {"phase": "measuring"}, cursor)
    assert launch.marks == ["measuring"]
    assert cursor.seen is None
    assert cursor.completed == 0
    assert cursor.marker_failed is True
    assert cursor.rejected == "measuring"
    assert cursor.observation_failure == "invalid_phase"
    finish = _Finish()

    def observe():
        apply_owned_marker(finish, {"phase": "starting"}, cursor)
        return True, None, 0

    report = finalize_owned_launch(finish, cursor, observe)
    assert finish.calls == 1
    assert report["marker_applied"] is False
    assert report["observation_error"] == "invalid_phase"
    assert report["canonical_operations_known"] is False
    assert report["lifetime_cpu_microseconds"] == 10


def test_each_enabled_case_needs_one_report_and_quiet_cases_need_none():
    owned = {"canonical_operations_completed": 128, "resource_acceptance": False}
    assert installed_resource_case_completed(_memory_case(), owned) is True
    assert installed_resource_case_completed(_memory_case(telemetry_events=[]), owned) is False
    assert installed_resource_case_completed(_memory_case(memory_successful=0), owned) is False
    quiet = _memory_case(
        condition="opted_out",
        telemetry_attempts=0,
        telemetry_reserved_bytes=0,
        telemetry_events=[],
    )
    assert installed_resource_case_completed(quiet, owned) is True
    noisy = _memory_case(
        condition="unavailable",
        telemetry_attempts=0,
        telemetry_reserved_bytes=0,
        telemetry_events=[{"malformed": False, "body_hex": bytes(PACKET_BYTES).hex()}],
    )
    assert installed_resource_case_completed(noisy, owned) is False
    inspected = bytes(PACKET_BYTES).hex()
    assert installed_resource_case_completed(
        _memory_case(inspected_body_hex=inspected), owned
    ) is True
    assert installed_resource_case_completed(
        _memory_case(inspected_body_hex="ab" * 25), owned
    ) is False


def test_missing_profile_store_is_zero_attempts(tmp_path: Path):
    assert read_resource_profile_store(tmp_path) == {
        "present": False,
        "attempts": 0,
        "reserved_bytes": 0,
        "fixture_content_absent": True,
    }


def test_both_retainers_keep_partial_ram_and_drop_paths():
    report = {
        "qualification": "unqualified",
        "resource_acceptance": True,
        "platform_method": "windows_job_before_resume",
        "lifetime_cpu_microseconds": None,
        "active_cpu_microseconds": None,
        "active_wall_microseconds": None,
        "active_core_fraction": None,
        "canonical_operations_completed": 96,
        "canonical_operations_known": False,
        "observation_error": "RuntimeError",
        "coverage": {
            "platform": "windows",
            "status": "partial",
            "cpu_lifetime_complete": True,
            "rss_high_water": "per_process_kernel_while_alive_partial",
        },
        "unavailable_counters": [
            "unseen_or_unsampled_process_working_set",
            "cgroup_memory_peak_bytes",
        ],
        "cold_start": {
            "kind": "first_observed_absolute",
            "subtracted": False,
            "processes": [{"identity": "40:9", "working_set_bytes": 1000000}],
        },
        "ledger": [
            {
                "pid": 40,
                "creation": "9",
                "identity": "40:9",
                "peak_working_set_bytes": 9000000,
                "first_working_set_bytes": 1000000,
                "last_working_set_bytes": 2000000,
                "kernel_high_water_while_observed": True,
            },
            {
                "pid": 41,
                "creation": "9",
                "identity": "41:9",
                "peak_working_set_bytes": None,
                "first_working_set_bytes": None,
                "last_working_set_bytes": None,
                "kernel_high_water_while_observed": False,
            },
        ],
        "ledger_truncated": False,
        "sampled_peaks": {
            "sum_working_set_bytes": 9000000,
            "sum_double_counts_shared": True,
            "not_a_budget_measurement": True,
            "sampled_pid_cpu_is_complete": False,
        },
        "kernel": {
            "total_user_100ns": 50,
            "total_kernel_100ns": 20,
            "commit_counters_are_working_set": False,
            "private_path": r"C:\secret-trace\kernel.py",
        },
        "cleanup": {
            "ok": False,
            "failure": "finish_failed",
            "retried": False,
            "terminated_owned_group": True,
        },
        "bounds": {
            "lifetime_seconds_cap": 120,
            "timed_out": False,
            "sample_seconds": 0.05,
            "sample_truncated": False,
            "sample_error": "sample_failed",
        },
        "phases": [
            {
                "name": "measuring",
                "active": True,
                "cpu_microseconds": None,
                "canonical_operations_at_end": 96,
            }
        ],
        "trace": r"C:\secret-trace\probe.py",
    }
    script = (
        "import { publicOwnedReport } from './studio/electron/scripts/installed-resource-report.mjs';"
        "const chunks = [];"
        "process.stdin.on('data', chunk => chunks.push(chunk));"
        "process.stdin.on('end', () => {"
        "const report = publicOwnedReport(JSON.parse(Buffer.concat(chunks).toString('utf8')));"
        "process.stdout.write(JSON.stringify(report));"
        "});"
    )
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        input=json.dumps(report),
        text=True,
        capture_output=True,
        check=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    public = json.loads(completed.stdout)
    final = retain_owned_launch(public)
    assert public["ledger"][0]["peak_working_set_bytes"] == 9000000
    assert final["ledger"][0]["peak_working_set_bytes"] == 9000000
    assert final["ledger"][1]["peak_working_set_bytes"] is None
    assert final["cold_start"]["processes"][0]["working_set_bytes"] == 1000000
    assert final["coverage"]["status"] == "partial"
    assert final["coverage"]["rss_high_water"] == "per_process_kernel_while_alive_partial"
    assert "unseen_or_unsampled_process_working_set" in final["unavailable_counters"]
    assert final["sampled_peaks"]["sum_working_set_bytes"] == 9000000
    assert final["kernel"]["total_user_100ns"] == 50
    assert "private_path" not in final["kernel"]
    assert final["bounds"]["sample_error"] == "sample_failed"
    assert final["cleanup"]["failure"] == "finish_failed"
    assert final["cleanup"]["terminated_owned_group"] is True
    assert final["canonical_operations_completed"] == 96
    assert final["canonical_operations_known"] is False
    assert final["observation_error"] == "RuntimeError"
    assert final["lifetime_cpu_microseconds"] is None
    assert final["resource_acceptance"] is False
    assert final["budget"]["status"] == "UNACCEPTED"
    assert final["budget"]["additional_rss_bytes_per_process"] == 8388608
    assert final["budget"]["compared"] is False
    assert "secret-trace" not in json.dumps(final)
    assert "secret-trace" not in completed.stdout
