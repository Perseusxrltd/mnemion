"""Presence and launch stay aligned for Python and the public JS report.

These checks call the pure serializers. They do not launch the app.
"""

import json
from pathlib import Path
import subprocess

from deploy.report_telemetry_renderer import retain_owned_launch


ROOT = Path(__file__).resolve().parents[1]
LEDGER_ROW = {
    "pid": 40,
    "creation": "9",
    "identity": "40:9",
    "peak_working_set_bytes": 0,
    "first_working_set_bytes": 0,
    "last_working_set_bytes": None,
}


def _js(report) -> dict:
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
        cwd=ROOT,
    )
    return json.loads(completed.stdout)


def _verdict(report) -> dict:
    python = retain_owned_launch(report)
    javascript = _js(report)
    again = retain_owned_launch(javascript)
    assert python["present"] is javascript["present"] is again["present"]
    assert python["launched"] is javascript["launched"] is again["launched"]
    assert python["resource_acceptance"] is False
    assert javascript["resource_acceptance"] is False
    assert again["resource_acceptance"] is False
    assert python["missing_recorded_as_zero"] is False
    assert javascript["missing_recorded_as_zero"] is False
    assert again["launched"] is not True or python["present"] is True
    return {"python": python, "javascript": javascript, "again": again}


def test_absent_empty_and_nonobjects_are_not_a_launched_workload():
    for report in (None, [], {}, "report", 0, 1.5, True, {"hello": 1}, {"launched": "yes"}, {"launched": 1}):
        verdict = _verdict(report)
        assert verdict["python"]["present"] is False
        assert verdict["python"]["launched"] is None
        assert verdict["again"]["present"] is False
        assert verdict["again"]["launched"] is None


def test_withheld_marker_dominates_conflicting_launch_claims():
    report = {
        "private_content_withheld": True,
        "present": True,
        "launched": True,
        "lifetime_cpu_microseconds": 5,
        "platform_method": "windows_job_before_resume",
        "coverage": {"status": "partial", "cpu_lifetime_complete": True},
        "phases": 4,
        "ledger": [LEDGER_ROW],
    }
    verdict = _verdict(report)
    for copy in (verdict["python"], verdict["javascript"], verdict["again"]):
        assert copy["present"] is False
        assert copy["launched"] is None
        assert copy["private_content_withheld"] is True
        assert copy.get("lifetime_cpu_microseconds") is None
        assert copy.get("ledger") in (None, [])


def test_metadata_stays_present_with_unknown_launch():
    cases = (
        {"coverage": {"status": "partial", "cpu_lifetime_complete": False}},
        {"cold_start": {"kind": "first_observed_absolute", "processes": []}},
        {"platform_method": "windows_job_before_resume"},
        {"platform_method": "linux_cgroup_v2_cpu_stat"},
        {"platform_method": "darwin_wait4_and_resident_size"},
        {"phases": [{"name": "measuring", "active": True, "cpu_microseconds": 10}]},
        {
            "canonical_operations_completed": 96,
            "canonical_operations_known": False,
            "lifetime_cpu_microseconds": None,
        },
    )
    for report in cases:
        verdict = _verdict(report)
        assert verdict["python"]["present"] is True
        assert verdict["python"]["launched"] is None
        assert verdict["python"]["lifetime_cpu_microseconds"] is None
        assert verdict["javascript"]["launched"] is None


def test_metadata_fields_remain_when_launch_is_unknown():
    verdict = _verdict(
        {
            "coverage": {"status": "partial", "cpu_lifetime_complete": False},
            "platform_method": "windows_job_before_resume",
            "cold_start": {"kind": "first_observed_absolute", "subtracted": False, "processes": []},
            "phases": [{"name": "starting", "active": False, "cpu_microseconds": None}],
            "lifetime_cpu_microseconds": None,
            "active_cpu_microseconds": None,
        }
    )
    python = verdict["python"]
    assert python["coverage"]["status"] == "partial"
    assert python["cpu_lifetime_complete"] is False
    assert python["platform_method"] == "windows_job_before_resume"
    assert python["cold_start"]["kind"] == "first_observed_absolute"
    assert python["cold_start"]["processes"] == []
    assert python["phases"][0]["name"] == "starting"
    assert python["phases"][0]["cpu_microseconds"] is None
    assert verdict["javascript"]["coverage"]["status"] == "partial"
    assert verdict["javascript"]["platform_method"] == "windows_job_before_resume"
    assert verdict["javascript"]["phases"][0]["cpu_microseconds"] is None


def test_explicit_launch_flags_round_trip_and_malformed_flags_do_not():
    denied = _verdict(
        {
            "launched": False,
            "honest_unsupported": "cgroup_unavailable",
            "lifetime_cpu_microseconds": None,
            "coverage": {"status": "unsupported"},
        }
    )
    assert denied["python"]["present"] is True
    assert denied["python"]["launched"] is False
    assert denied["python"]["honest_unsupported"] == "cgroup_unavailable"
    assert denied["python"]["lifetime_cpu_microseconds"] is None

    started = _verdict(
        {
            "launched": True,
            "lifetime_cpu_microseconds": None,
            "active_cpu_microseconds": None,
            "cleanup": {"ok": False, "failure": "finish_failed", "retried": False},
        }
    )
    assert started["python"]["present"] is True
    assert started["python"]["launched"] is True
    assert started["python"]["lifetime_cpu_microseconds"] is None
    assert started["python"]["cleanup_failure"] == "finish_failed"
    assert started["javascript"]["cleanup"]["failure"] == "finish_failed"

    contradicted = _verdict(
        {
            "launched": True,
            "honest_unsupported": "cgroup_unavailable",
            "lifetime_cpu_microseconds": 12,
        }
    )
    assert contradicted["python"]["launched"] is False
    assert contradicted["python"]["lifetime_cpu_microseconds"] == 12

    noisy = _verdict(
        {
            "launched": "yes",
            "coverage": {"status": "partial"},
            "lifetime_cpu_microseconds": None,
        }
    )
    assert noisy["python"]["present"] is True
    assert noisy["python"]["launched"] is None


def test_validated_process_rows_and_measured_zeros_launch_without_a_flag():
    native = _verdict(
        {
            "platform_method": "windows_job_before_resume",
            "lifetime_cpu_microseconds": None,
            "active_cpu_microseconds": 0,
            "coverage": {"platform": "windows", "status": "partial"},
            "ledger": [LEDGER_ROW],
            "cold_start": {
                "kind": "first_observed_absolute",
                "processes": [{"identity": "40:9", "working_set_bytes": 0}],
            },
            "resource_acceptance": True,
            "qualification": "qualified",
        }
    )
    assert native["python"]["present"] is True
    assert native["python"]["launched"] is True
    assert native["python"]["lifetime_cpu_microseconds"] is None
    assert native["python"]["active_cpu_microseconds"] == 0
    assert native["python"]["ledger"][0]["peak_working_set_bytes"] == 0
    assert native["python"]["cold_start"]["processes"][0]["working_set_bytes"] == 0
    assert native["python"]["qualification"] == "unqualified"
    assert native["python"]["budget"]["status"] == "UNACCEPTED"
    assert native["python"]["budget"]["additional_rss_bytes_per_process"] == 8_388_608
    assert native["python"]["budget"]["cpu_one_core_fraction"] == 0.005
    assert native["python"]["budget"]["compared"] is False
    assert native["javascript"]["budget"]["status"] == "UNACCEPTED"
    assert native["javascript"]["ledger"][0]["peak_working_set_bytes"] == 0

    measured = _verdict(
        {
            "lifetime_cpu_microseconds": 0,
            "active_cpu_microseconds": 0,
            "active_wall_microseconds": None,
            "kernel": {"total_user_100ns": 0, "commit_counters_are_working_set": False},
        }
    )
    assert measured["python"]["launched"] is True
    assert measured["python"]["lifetime_cpu_microseconds"] == 0
    assert measured["python"]["active_cpu_microseconds"] == 0
    assert measured["python"]["active_wall_microseconds"] is None
    assert measured["python"]["kernel"]["total_user_100ns"] == 0
    assert measured["javascript"]["kernel"]["total_user_100ns"] == 0

    from_row = _verdict({"launched": "yes", "ledger": [LEDGER_ROW]})
    assert from_row["python"]["present"] is True
    assert from_row["python"]["launched"] is True
    assert from_row["python"]["ledger"][0]["peak_working_set_bytes"] == 0


def test_malformed_collections_do_not_throw_or_launch():
    report = {
        "phases": 3,
        "ledger": {"pid": 40},
        "cold_start": {"processes": "40:9"},
        "unavailable_counters": "lifetime_cpu_microseconds",
        "coverage": ["partial"],
        "kernel": ["total_user_100ns"],
        "sampled_peaks": 0,
        "bounds": [],
        "cleanup": "no",
    }
    verdict = _verdict(report)
    assert verdict["python"]["present"] is False
    assert verdict["python"]["launched"] is None
    assert verdict["python"]["phases"] == []
    assert verdict["python"]["ledger"] == []
    assert verdict["python"]["cold_start"]["processes"] == []
    assert verdict["python"]["unavailable_counters"] is None
    assert verdict["python"]["kernel"] is None
    assert verdict["python"]["lifetime_cpu_microseconds"] is None


def test_absent_sentinel_and_default_false_fields_stay_absent():
    fat = {
        "present": False,
        "launched": True,
        "qualification": "unqualified",
        "resource_acceptance": False,
        "missing_recorded_as_zero": False,
        "coverage": {
            "platform": None,
            "status": None,
            "cpu_lifetime_complete": None,
        },
        "phases": [],
        "ledger": [],
        "lifetime_cpu_microseconds": None,
        "active_cpu_microseconds": None,
        "cold_start": {"kind": None, "subtracted": None, "processes": []},
        "cleanup": {
            "ok": False,
            "failure": None,
            "retried": False,
            "terminated_owned_group": None,
        },
        "platform_method": None,
        "honest_unsupported": None,
    }
    verdict = _verdict(fat)
    assert verdict["python"]["present"] is False
    assert verdict["python"]["launched"] is None
    assert "lifetime_cpu_microseconds" not in verdict["javascript"]
    assert verdict["again"]["present"] is False
    assert verdict["again"]["launched"] is None

    explicit = retain_owned_launch({"launched": False})
    assert explicit["present"] is True
    assert explicit["launched"] is False
    assert _verdict({"launched": False})["again"]["launched"] is False
