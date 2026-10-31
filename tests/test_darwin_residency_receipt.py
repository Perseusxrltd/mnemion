"""Pure checks for Darwin residency receipts. No Mach calls."""

import json
from pathlib import Path

import deploy.darwin_residency_receipt as receipt

SOURCE = "45883ad89caab4c90d9b18707f5cdeab883a9e00"


def observation(**overrides):
    obs = {
        "allocation_bytes": receipt.ALLOCATION_BYTES,
        "allocation_observed": True,
        "arch": "arm64",
        "baseline_resident_size": 1_000_000,
        "baseline_resident_size_max": 1_000_000,
        "baseline_task_info_count": 20,
        "baseline_task_info_kern_return": 0,
        "child_exit_kind": "exited",
        "child_exit_status": 0,
        "child_pid": 4242,
        "child_reaped": True,
        "child_ru_maxrss": 9_400_000,
        "child_ru_maxrss_unit": "bytes",
        "child_term_signal": None,
        "cleanup_ok": True,
        "detail": "ok",
        "live_resident_size": 9_200_000,
        "live_resident_size_max": 9_400_000,
        "live_task_info_count": 20,
        "live_task_info_kern_return": 0,
        "name_port_is_null": False,
        "name_port_kern_return": 0,
        "os": "Darwin",
        "os_release": "25.0.0",
        "outcome": "live_counter_ok",
        "peaks_nondecreasing": True,
        "port_deallocate_kern_return": 0,
        "post_exit_queried": True,
        "post_exit_resident_size": None,
        "post_exit_resident_size_max": None,
        "post_exit_supported": False,
        "post_exit_task_info_count": 0,
        "post_exit_task_info_kern_return": 5,
        "probe": receipt.PROBE_NAME,
        "resident_size_max_unit": "bytes",
        "resident_size_unit": "bytes",
        "resource_budget_acceptance": False,
        "source": SOURCE,
        "source_rejected": False,
        "telemetry_acceptance": False,
        "timed_out": False,
        "workload_acceptance": False,
    }
    obs.update(overrides)
    return obs


def test_live_capability_allows_post_exit_denial():
    obs = observation()
    assert receipt.classify(obs) == "live_counter_ok"
    assert receipt.demonstrated(
        obs,
        source=SOURCE,
        workflow_arch="arm64",
        probe_returncode=0,
        outer_timeout=False,
    )


def test_name_port_denial_is_not_a_zero_peak():
    obs = observation(
        name_port_kern_return=5,
        name_port_is_null=True,
        baseline_resident_size=0,
        baseline_resident_size_max=0,
        baseline_task_info_kern_return=None,
        baseline_task_info_count=None,
        live_resident_size=0,
        live_resident_size_max=0,
        live_task_info_kern_return=None,
        live_task_info_count=None,
        child_ru_maxrss=None,
        peaks_nondecreasing=None,
        allocation_observed=None,
        post_exit_queried=False,
        post_exit_supported=None,
        post_exit_task_info_kern_return=None,
        post_exit_task_info_count=None,
        port_deallocate_kern_return=None,
        outcome="name_port_denied",
        detail="name_port_rejected",
    )
    assert receipt.classify(obs) == "name_port_denied"
    assert not receipt.demonstrated(
        obs,
        source=SOURCE,
        workflow_arch="arm64",
        probe_returncode=2,
        outer_timeout=False,
    )


def test_success_label_cannot_hide_name_port_denial():
    obs = observation(name_port_kern_return=5, outcome="live_counter_ok")
    assert receipt.classify(obs) == "malformed_observation"


def test_zero_peak_is_not_a_denial_or_a_pass():
    obs = observation(
        baseline_resident_size=0,
        baseline_resident_size_max=0,
        live_resident_size=0,
        live_resident_size_max=0,
        child_ru_maxrss=0,
        peaks_nondecreasing=True,
        allocation_observed=False,
        outcome="zero_peak_rss",
        detail="zero_peak",
    )
    assert receipt.classify(obs) == "zero_peak_rss"


def test_missing_live_counter_is_not_zero():
    obs = observation(
        live_resident_size=None,
        live_resident_size_max=None,
        live_task_info_kern_return=5,
        live_task_info_count=0,
        peaks_nondecreasing=None,
        allocation_observed=None,
        post_exit_queried=False,
        post_exit_supported=None,
        post_exit_task_info_kern_return=None,
        post_exit_task_info_count=None,
        outcome="counter_missing",
        detail="counter_incomplete",
    )
    assert receipt.classify(obs) == "counter_missing"


def test_unreaped_child_is_a_cleanup_failure():
    obs = observation(child_reaped=False, cleanup_ok=False, outcome="child_or_cleanup_failure")
    assert receipt.classify(obs) == "child_or_cleanup_failure"


def test_timeout_is_not_labeled_as_a_name_port_denial():
    obs = observation(
        timed_out=True,
        name_port_kern_return=5,
        name_port_is_null=True,
        child_exit_kind="signaled",
        child_exit_status=None,
        child_term_signal=9,
        outcome="child_or_cleanup_failure",
        detail="timeout",
    )
    assert receipt.classify(obs) == "child_or_cleanup_failure"


def test_timeout_with_confirmed_reap_still_fails():
    obs = observation(
        timed_out=True,
        cleanup_ok=True,
        child_exit_kind="signaled",
        child_exit_status=None,
        child_term_signal=9,
        outcome="child_or_cleanup_failure",
        detail="timeout",
    )
    assert receipt.classify(obs) == "child_or_cleanup_failure"


def test_decreasing_peak_is_not_forced_to_pass():
    obs = observation(
        live_resident_size_max=500_000,
        peaks_nondecreasing=False,
        outcome="peak_or_allocation_check_failed",
        detail="peak_decreased",
    )
    assert receipt.classify(obs) == "peak_or_allocation_check_failed"


def test_true_flags_cannot_hide_a_decreased_peak():
    obs = observation(live_resident_size_max=500_000, peaks_nondecreasing=True)
    assert receipt.classify(obs) == "malformed_observation"


def test_post_exit_zero_sizes_are_not_a_denial_record():
    obs = observation(post_exit_resident_size=0, post_exit_resident_size_max=0)
    assert receipt.classify(obs) == "malformed_observation"


def test_acceptance_flag_cannot_pass():
    obs = observation(telemetry_acceptance=True)
    assert receipt.classify(obs) == "malformed_observation"


def test_truncated_and_missing_stdout_are_rejected():
    assert receipt.extract_observation("")[1] == "missing"
    assert receipt.extract_observation('{"outcome":')[1] == "truncated_or_invalid"
    assert receipt.extract_observation("{}\n")[0] == {}


def test_stop_owned_probe_kills_only_its_verified_group():
    calls = []

    class Proc:
        pid = 4321

        def poll(self):
            return None

    def getpgid(pid):
        assert pid == 4321
        return 4321

    def killpg(pid, sig):
        calls.append(("group", pid, sig))

    def kill(pid, sig):
        calls.append(("pid", pid, sig))

    assert (
        receipt.stop_owned_probe(Proc(), getpgid=getpgid, killpg=killpg, kill=kill)
        == "killed_group"
    )
    assert calls == [("group", 4321, receipt.SIGKILL)]


def test_stop_owned_probe_does_not_kill_a_foreign_group():
    calls = []

    class Proc:
        pid = 4321

        def poll(self):
            return None

    def killpg(pid, sig):
        calls.append(("group", pid, sig))

    def kill(pid, sig):
        calls.append(("pid", pid, sig))

    result = receipt.stop_owned_probe(
        Proc(),
        getpgid=lambda _pid: 99,
        killpg=killpg,
        kill=kill,
    )
    assert result == "signaled_pid_only"
    assert calls == [("pid", 4321, receipt.SIGTERM)]


def test_stop_owned_probe_refuses_a_dead_or_privileged_pid():
    class Dead:
        pid = 4321

        def poll(self):
            return 0

    class Init:
        pid = 1

        def poll(self):
            return None

    def boom(*_args):
        raise AssertionError("must not signal")

    assert (
        receipt.stop_owned_probe(Dead(), getpgid=boom, killpg=boom, kill=boom) == "already_exited"
    )
    assert receipt.stop_owned_probe(Init(), getpgid=boom, killpg=boom, kill=boom) == "refused"


def test_arch_and_source_binding():
    obs = observation(arch="x86_64")
    assert receipt.demonstrated(
        obs,
        source=SOURCE,
        workflow_arch="x64",
        probe_returncode=0,
        outer_timeout=False,
    )
    assert not receipt.demonstrated(
        obs,
        source=SOURCE,
        workflow_arch="arm64",
        probe_returncode=0,
        outer_timeout=False,
    )


def test_probe_source_uses_the_name_port_and_not_a_stronger_port():
    text = (Path(__file__).resolve().parents[1] / "deploy" / "probe_darwin_residency.c").read_text(
        encoding="utf-8"
    )
    assert "task_name_for_pid" in text
    assert "task_for_pid(" not in text
    assert "mach_vm_read" not in text
    assert "sleep(" not in text


def test_workflow_is_manual_two_target_and_does_not_interpolate_source():
    text = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "native-residency-counters.yml"
    ).read_text(encoding="utf-8")
    assert text.count("os: macos-26") == 1
    assert text.count("os: macos-15-intel") == 1
    assert "ubuntu" not in text
    assert "windows" not in text
    assert "fail-fast: false" in text
    assert "persist-credentials: false" in text
    assert "contents: read" in text
    assert "timeout-minutes: 10" in text
    assert "workflow_dispatch" in text
    assert "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803" in text
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in text
    assert "if: always()" in text
    assert "retry" not in text
    run = text.split("        run: |\n", 1)[1].split("      - uses: actions/upload-artifact", 1)[0]
    assert "${{" not in run
    assert "REVIEWED_SOURCE" in text
    assert receipt.extract_observation(json.dumps(observation()))[1] is None
