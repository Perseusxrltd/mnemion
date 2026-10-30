"""The compiled-source counterbalance uses the owned-launch adapter.

These checks do not launch the app or run the 128-cycle workload.
"""

import json

from deploy.report_telemetry_renderer import (
    OwnedPhaseCursor,
    apply_owned_marker,
    owned_controller_argv,
    owned_counterbalance,
    owned_delegate_identity_ok,
    owned_phase_from_marker,
    owned_scope_command,
    retain_owned_launch,
    summarize,
)
from pathlib import Path


class _Marks:
    def __init__(self):
        self.marks = []

    def mark_phase(self, name, *, canonical_operations_completed, active):
        self.marks.append((name, canonical_operations_completed, active))


def test_counterbalance_owns_only_the_existing_controller():
    app = Path("studio/electron")
    assert owned_controller_argv(app) == [
        "node",
        str(app / "probe-telemetry-renderer.mjs"),
    ]
    assert owned_counterbalance(False, True) is True
    assert owned_counterbalance(True, False) is True
    assert owned_counterbalance(False, False) is False
    assert owned_counterbalance(True, True) is False


def test_markers_follow_the_existing_interval_and_drop_unknown_labels():
    assert owned_phase_from_marker("starting", 0) == ("starting", False, 0)
    assert owned_phase_from_marker("measuring", 0) == ("measuring", True, 0)
    assert owned_phase_from_marker("before_workspace_connect", 0) == (
        "before-workspace-connect",
        True,
        0,
    )
    assert owned_phase_from_marker("128_memory_cycles", 96) == (
        "128-memory-cycles",
        True,
        128,
    )
    assert owned_phase_from_marker("finished", 1) == ("finished", False, 1)
    assert owned_phase_from_marker("closed", 1) == ("closed", False, 1)
    assert owned_phase_from_marker("warmup", 0) is None
    assert owned_phase_from_marker("idle", 0) is None
    assert owned_phase_from_marker(None, 0) is None

    launch = _Marks()
    cursor = OwnedPhaseCursor()
    apply_owned_marker(launch, {"phase": "starting"}, cursor)
    apply_owned_marker(launch, {"phase": "starting"}, cursor)
    apply_owned_marker(launch, {"phase": "measuring"}, cursor)
    apply_owned_marker(launch, {"phase": "warmup"}, cursor)
    apply_owned_marker(launch, {"phase": "128_memory_cycles"}, cursor)
    assert launch.marks == [
        ("starting", 0, False),
        ("measuring", 0, True),
        ("128-memory-cycles", 128, True),
    ]
    assert cursor.completed == 128


def _identity(**overrides):
    base = dict(
        requested=True,
        systemd="/usr/bin/systemd-run",
        sudo="/usr/bin/sudo",
        euid=1001,
        egid=121,
        cwd="/work/repo",
        environ={
            "PATH": "/work/.venv/bin:/usr/bin",
            "HOME": "/home/runner",
            "USER": "runner",
            "LOGNAME": "runner",
            "LANG": "C.UTF-8",
            "GITHUB_TOKEN": "nope",
            "SECRET_TOKEN": "nope",
        },
        probe_accepted=None,
    )
    base.update(overrides)
    return base


def test_delegated_service_preserves_runner_identity_and_tool_environment():
    command = [
        "/usr/bin/xvfb-run",
        "-a",
        "/work/repo/.venv/bin/python",
        "-m",
        "deploy.probe_telemetry_renderer",
    ]
    same, mode = owned_scope_command(command, **_identity(requested=False))
    assert same == command and mode == "not_requested"

    missing, missing_mode = owned_scope_command(command, **_identity(systemd=None, euid=0))
    assert missing == command and missing_mode == "direct_systemd_missing"

    root, root_mode = owned_scope_command(command, **_identity(euid=0, egid=0))
    assert root == command and root_mode == "direct_non_root_required"

    relative, relative_mode = owned_scope_command(["xvfb-run", "-a", "python"], **_identity())
    assert relative == ["xvfb-run", "-a", "python"] and relative_mode == "direct_tool_path_missing"

    refused, refused_mode = owned_scope_command(command, **_identity(probe_accepted=False))
    assert refused == command and refused_mode == "direct_service_unavailable"
    assert refused[0] != "/usr/bin/sudo"

    wrapped, wrapped_mode = owned_scope_command(command, **_identity())
    assert wrapped_mode == "systemd_service_delegate"
    assert wrapped[:3] == ["/usr/bin/sudo", "-n", "/usr/bin/systemd-run"]
    assert "--scope" not in wrapped
    assert "-E" not in wrapped
    assert "--preserve-env" not in wrapped
    assert "Delegate=yes" in wrapped
    assert "User=1001" in wrapped
    assert "Group=121" in wrapped
    assert "WorkingDirectory=/work/repo" in wrapped
    assert "--setenv=PATH=/work/.venv/bin:/usr/bin" in wrapped
    assert "--setenv=HOME=/home/runner" in wrapped
    assert "--setenv=USER=runner" in wrapped
    assert wrapped[wrapped.index("--") + 1 :] == command
    rendered = " ".join(wrapped)
    assert "nope" not in rendered
    assert "GITHUB_TOKEN" not in rendered
    assert "SECRET_TOKEN" not in rendered
    assert "subtree_control" not in rendered

    probe, probe_mode = owned_scope_command(["/usr/bin/id", "-u"], **_identity())
    assert probe_mode == "systemd_service_delegate"
    assert probe[-2:] == ["/usr/bin/id", "-u"]
    assert "User=1001" in probe and "Group=121" in probe
    assert owned_delegate_identity_ok(0, "1001\n", 1001) is True
    assert owned_delegate_identity_ok(0, "0\n", 0) is False
    assert owned_delegate_identity_ok(0, "0\n", 1001) is False
    assert owned_delegate_identity_ok(1, "1001\n", 1001) is False
    assert (
        owned_scope_command(command, **_identity(environ={"PATH": "/bin/%h"}))[1]
        == "direct_identity_unavailable"
    )


def test_summary_keeps_null_partial_coverage_and_does_not_replace_sample_cpu(tmp_path):
    def rows(last_cpu):
        return [
            {
                "name": name,
                "processes": [
                    {
                        "pid": 10,
                        "type": "Browser",
                        "working_set_bytes": 100,
                        "cpu_ms": cpu,
                    }
                ],
            }
            for name, cpu in (("start", 0), ("middle", 10), ("end", last_cpu))
        ]

    results = [
        {"variant": "unavailable", "samples": rows(20), "elapsed_ms": 100},
        {"variant": "enabled", "samples": rows(70), "elapsed_ms": 120},
    ]
    (tmp_path / "receipt.json").write_text(json.dumps({"results": results}))
    for label in ("unavailable", "enabled"):
        (tmp_path / f"{label}-processes.json").write_text("[]\n")
    (tmp_path / "unavailable-owned-launch.json").write_text(
        json.dumps(
            {
                "qualification": "unqualified",
                "resource_acceptance": True,
                "lifetime_cpu_microseconds": None,
                "active_cpu_microseconds": None,
                "coverage": {"status": "partial", "cpu_lifetime_complete": False},
                "unavailable_counters": ["cgroup_memory_peak_bytes"],
                "identities_missing": None,
                "observer_in_measured_group": False,
                "cleanup": {"ok": False, "failure": "descendants_survived", "retried": False},
                "phases": [
                    {"name": "starting", "active": False, "cpu_microseconds": 10},
                    {"name": "measuring", "active": True, "cpu_microseconds": None},
                ],
                "missing_recorded_as_zero": False,
            }
        )
    )
    (tmp_path / "enabled-owned-launch.json").write_text(
        json.dumps(
            {
                "qualification": "unqualified",
                "resource_acceptance": False,
                "honest_unsupported": "cgroup_unavailable",
                "launched": False,
                "lifetime_cpu_microseconds": None,
                "active_cpu_microseconds": None,
                "coverage": {"status": "unsupported"},
                "cleanup": {"ok": None, "failure": None, "retried": False},
                "phases": [],
            }
        )
    )
    summary = summarize(tmp_path)
    assert summary["resource_acceptance"] is False
    assert any("not app-overhead acceptance" in line for line in summary["limits"])
    unavailable, enabled = summary["observations"]
    assert unavailable["electron_cpu_ms"] == 20
    assert enabled["electron_cpu_ms"] == 70
    assert summary["comparisons"][0]["difference_electron_cpu_ms"] == 50
    partial = unavailable["owned_launch"]
    assert partial["present"] is True
    assert partial["resource_acceptance"] is False
    assert partial["qualification"] == "unqualified"
    assert partial["coverage_status"] == "partial"
    assert partial["cpu_lifetime_complete"] is False
    assert partial["lifetime_cpu_microseconds"] is None
    assert partial["active_cpu_microseconds"] is None
    assert partial["identities_missing"] is None
    assert partial["cleanup_ok"] is False
    assert partial["cleanup_failure"] == "descendants_survived"
    assert partial["phases"][1]["cpu_microseconds"] is None
    assert partial["missing_recorded_as_zero"] is False
    assert enabled["owned_launch"]["launched"] is False
    assert enabled["owned_launch"]["honest_unsupported"] == "cgroup_unavailable"
    assert enabled["owned_launch"]["cleanup_ok"] is None
    assert retain_owned_launch(None)["present"] is False
    measured_zero = retain_owned_launch(
        {
            "lifetime_cpu_microseconds": 0,
            "active_cpu_microseconds": 0,
            "coverage": {"status": "partial", "cpu_lifetime_complete": True},
            "resource_acceptance": True,
            "qualification": "qualified",
        }
    )
    assert measured_zero["lifetime_cpu_microseconds"] == 0
    assert measured_zero["active_cpu_microseconds"] == 0
    assert measured_zero["cpu_lifetime_complete"] is True
    assert measured_zero["resource_acceptance"] is False
    assert measured_zero["qualification"] == "unqualified"
    assert (
        retain_owned_launch({"lifetime_cpu_microseconds": True})["lifetime_cpu_microseconds"]
        is None
    )
