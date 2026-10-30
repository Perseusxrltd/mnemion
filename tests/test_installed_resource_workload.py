"""Small checks for installed resource finalization, counts, and package choice."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deploy.owned_installed_launch import (
    _annotate,
    delivery_diagnostics_enabled,
    finalize_owned_launch,
    owned_launch_succeeded,
)
from deploy.probe_telemetry_installed import (
    _bounded_error,
    bind_resource_packages,
    installed_resource_case_completed,
    linux_resource_launch_allowed,
    resource_smoke_environment,
    select_owned_observer,
)
from deploy.report_telemetry_renderer import (
    INSTALLED_DESKTOP_ENV,
    OwnedPhaseCursor,
    apply_owned_marker,
    owned_scope_command,
    resource_counterbalance_cases,
)


class _Cursor:
    def __init__(self, completed):
        self.completed = completed


class _FinishLaunch:
    def __init__(self, result):
        self.calls = 0
        self.result = result
        self.backend = type("Backend", (), {"process": None})()

    def finish(self, *, canonical_operations_completed=None):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        report = dict(self.result)
        report["canonical_operations_completed"] = canonical_operations_completed
        return report


class _MarkerLaunch:
    def __init__(self):
        self.phases = []

    def mark_phase(self, name, *, canonical_operations_completed, active):
        self.phases.append((name, canonical_operations_completed, active))


def test_finalize_survives_observation_and_finish_errors():
    launch = _FinishLaunch(RuntimeError("finish broke"))

    def observe():
        raise RuntimeError("marker broke")

    report = finalize_owned_launch(launch, _Cursor(96), observe)
    assert launch.calls == 1
    assert report["cleanup"]["ok"] is False
    assert report["lifetime_cpu_microseconds"] is None
    assert report["lifetime_cpu_microseconds"] != 0
    assert report["observation_error"] == "RuntimeError"
    assert report["missing_recorded_as_zero"] is False
    assert report["canonical_operations_completed"] == 96


def test_finalize_keeps_a_real_finish_report_when_observation_fails():
    launch = _FinishLaunch(
        {
            "lifetime_cpu_microseconds": 10,
            "active_cpu_microseconds": 4,
            "cleanup": {"ok": True, "failure": None, "retried": False},
        }
    )

    def observe():
        raise RuntimeError("exit code unreadable")

    report = finalize_owned_launch(launch, _Cursor(32), observe)
    assert launch.calls == 1
    assert report["lifetime_cpu_microseconds"] == 10
    assert report["cleanup"]["ok"] is True
    assert report["observation_error"] == "RuntimeError"
    assert report["canonical_operations_completed"] == 32


def test_missing_and_still_active_exit_codes_are_not_success():
    assert owned_launch_succeeded(True, None, True, None) is False
    assert owned_launch_succeeded(True, 259, True, None) is False
    assert owned_launch_succeeded(True, 0, True, None) is True
    assert owned_launch_succeeded(False, 0, True, None) is False
    assert owned_launch_succeeded(True, 0, False, None) is False


def _consume(markers):
    launch = _MarkerLaunch()
    cursor = OwnedPhaseCursor()
    for marker in markers:
        apply_owned_marker(launch, marker, cursor)
    return cursor.completed, [row[0] for row in launch.phases]


def test_terminal_markers_keep_verified_counts_and_unknown_progress():
    started, started_names = _consume([{"phase": "starting"}])
    assert started == 0
    assert started_names == ["starting"]
    completed, names = _consume([{"phase": "starting"}, {"phase": "96_memory_cycles"}])
    assert names[0] == "starting"
    assert completed == 96
    assert names.count("96-memory-cycles") == 1
    stayed, _ = _consume(
        [
            {"phase": "96_memory_cycles"},
            {"phase": "96_memory_cycles"},
            {"phase": "finished", "completed": 128, "completed_known": False},
        ]
    )
    assert stayed == 96
    replaced, _ = _consume(
        [
            {"phase": "96_memory_cycles"},
            {"phase": "finished", "completed": 128, "completed_known": True},
            {"phase": "closed", "completed": 128, "completed_known": True},
        ]
    )
    assert replaced == 128
    missing, _ = _consume(
        [{"phase": "96_memory_cycles"}, {"phase": "finished"}, {"phase": "closed"}]
    )
    assert missing == 96
    failed, _ = _consume([{"phase": "failed", "completed": 40, "completed_known": True}])
    assert failed == 40


def test_package_binding_uses_the_six_counterbalanced_conditions(tmp_path: Path):
    inactive = tmp_path / "inactive.exe"
    active = tmp_path / "active.exe"
    inactive.write_bytes(b"inactive-package")
    active.write_bytes(b"active-package")
    source = "a" * 40
    manifest = bind_resource_packages(source=source, active=active, inactive=inactive)
    assert [row["label"] for row in manifest["cases"]] == [
        "r1-unavailable",
        "r1-opted_out",
        "r1-enabled",
        "r2-enabled",
        "r2-opted_out",
        "r2-unavailable",
    ]
    assert [row["package"] for row in manifest["cases"]] == [
        "inactive",
        "active",
        "active",
        "active",
        "active",
        "inactive",
    ]
    assert manifest["packages"]["inactive"]["sha256"] != manifest["packages"]["active"]["sha256"]
    assert "credential" not in manifest
    assert "api_key" not in json.dumps(manifest)
    assert manifest["cases"] == resource_counterbalance_cases()
    with pytest.raises(ValueError):
        bind_resource_packages(source=source, active=active, inactive=active)


def test_windows_arm_observer_is_not_the_engine_python():
    with pytest.raises(RuntimeError):
        select_owned_observer({}, platform_name="win32")
    with pytest.raises(RuntimeError):
        select_owned_observer(
            {
                "MNEMION_OWNED_LAUNCH_PYTHON": r"C:\client\python.exe",
                "MNEMION_ENGINE_PYTHON": r"C:\client\python.exe",
                "RUNNER_ARCH": "ARM64",
            },
            platform_name="win32",
        )
    chosen = select_owned_observer(
        {
            "MNEMION_OWNED_LAUNCH_PYTHON": r"C:\client\python.exe",
            "MNEMION_ENGINE_PYTHON": r"C:\engine\python.exe",
            "PROCESSOR_ARCHITECTURE": "ARM64",
        },
        platform_name="win32",
    )
    assert chosen == r"C:\client\python.exe"


def test_linux_identity_failure_does_not_allow_launch():
    assert (
        linux_resource_launch_allowed(
            mode="systemd_service_delegate",
            probe_mode="direct_service_unavailable",
            returncode=1,
            stdout="",
            euid=1000,
        )
        is False
    )
    assert (
        linux_resource_launch_allowed(
            mode="systemd_service_delegate",
            probe_mode="systemd_service_delegate",
            returncode=0,
            stdout="1000\n",
            euid=1000,
        )
        is True
    )


def test_default_service_environment_does_not_pass_the_fixture_key():
    environ = {
        "PATH": "/usr/bin",
        "HOME": "/home/runner",
        "MNEMION_TELEMETRY_FIXTURE_KEY": "fixture-key-not-for-the-default-service",
    }
    common = dict(
        requested=True,
        systemd="/usr/bin/systemd-run",
        sudo="/usr/bin/sudo",
        euid=1000,
        egid=1000,
        cwd="/work",
        environ=environ,
        probe_accepted=None,
    )
    command, mode = owned_scope_command(["/usr/bin/true"], **common)
    assert mode == "systemd_service_delegate"
    assert all("fixture-key-not-for-the-default-service" not in part for part in command)
    wider, wider_mode = owned_scope_command(
        ["/usr/bin/true"], **common, env_names=INSTALLED_DESKTOP_ENV
    )
    assert wider_mode == "systemd_service_delegate"
    assert any(part.endswith("fixture-key-not-for-the-default-service") for part in wider)


def test_delivery_flag_is_the_only_diagnostic_detector():
    assert delivery_diagnostics_enabled({"MNEMION_TELEMETRY_INSTALLED_DELIVERY": "1"}) is True
    assert delivery_diagnostics_enabled({"MNEMION_WINDOWS_PRODUCER_DIAGNOSTICS": "1"}) is False
    report = _annotate(
        {},
        cursor=_Cursor(0),
        exit_code=None,
        hosting_ready=False,
        failure_stage=None,
        environ={"MNEMION_WINDOWS_PRODUCER_DIAGNOSTICS": "1"},
    )
    assert report["delivery_diagnostics_enabled"] is False


def test_resource_smoke_environment_drops_delivery_mode(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    env = resource_smoke_environment(
        {
            "MNEMION_TELEMETRY_INSTALLED_DELIVERY": "1",
            "MNEMION_ENGINE_PYTHON": "engine-python",
            "PATH": "/usr/bin",
        },
        observer="client-python",
        endpoint="http://127.0.0.1:9",
        space="space",
        fixture_key="fixture-key",
        manifest=manifest,
    )
    assert "MNEMION_TELEMETRY_INSTALLED_DELIVERY" not in env
    assert env["MNEMION_TELEMETRY_INSTALLED_RESOURCE"] == "1"
    assert env["MNEMION_OWNED_LAUNCH_PYTHON"] == "client-python"
    assert env["MNEMION_ENGINE_PYTHON"] == "engine-python"


def test_matching_counts_do_not_grant_resource_acceptance():
    checkpoints = [
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
    evidence = {
        "memory_cycles": 128,
        "memory_results_verified": True,
        "checkpoints": checkpoints,
        "model_calls": 0,
        "resource_acceptance": False,
    }
    assert installed_resource_case_completed(
        evidence, {"canonical_operations_completed": 96, "resource_acceptance": False}
    ) is False
    assert installed_resource_case_completed(
        {**evidence, "resource_acceptance": True},
        {"canonical_operations_completed": 128, "resource_acceptance": False},
    ) is False
    assert installed_resource_case_completed(
        evidence, {"canonical_operations_completed": 128, "resource_acceptance": False}
    ) is False


def test_public_errors_drop_paths_and_fixture_material():
    assert _bounded_error(RuntimeError(r"C:\runner\source\deploy\probe.py failed")) == "RuntimeError"
    assert _bounded_error(RuntimeError("loopback port did not bind")) == "RuntimeError: loopback port did not bind"


def test_resource_workflow_is_optional_and_has_no_target_selector():
    text = Path(".github/workflows/telemetry-installed-delivery.yml").read_text(encoding="utf-8")
    assert "resource_comparison:" in text
    assert "type: boolean" in text
    assert "default: false" in text
    assert "--resource-comparison" in text
    assert "MNEMION_OWNED_LAUNCH_PYTHON" in text
    assert "--targets" not in text
    assert "telemetry-diagnostic-engine-windows-x64-inactive" in text
