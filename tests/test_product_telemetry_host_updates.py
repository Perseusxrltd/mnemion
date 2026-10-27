"""Only dedicated automatic updater lifetimes own fixed host observations."""

from contextlib import nullcontext
import json
from types import SimpleNamespace

import pytest

from mnemion.product_telemetry import aggregate, policy, workflow
from mnemion.service import service_updates, supervision, update_measurement as measured


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / "telemetry"
    monkeypatch.setattr(policy, "default_directory", lambda: root)
    monkeypatch.setattr(policy, "company_policy_file", lambda: tmp_path / "company.json")
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", True)
    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://example.invalid/v1/report")
    policy.configure(root, {"enabled": True, "expected_revision": 0, "disclosure_version": 1})
    return root


@pytest.mark.parametrize("entry", ["standalone", "baseline_child", "library", "manual_cli"])
def test_only_dedicated_watcher_entrypoints_own_observations(
    installation, tmp_path, monkeypatch, entry
):
    def work(*args):
        with measured.operation("rollback"):
            pass
        return 0

    monkeypatch.setattr(service_updates, "watch", work)
    monkeypatch.setattr(service_updates, "check", work)
    monkeypatch.setattr(service_updates, "resolved_runtime", lambda _: {"isolated": False})
    monkeypatch.setattr(
        supervision,
        "settings",
        lambda _: (tmp_path, {"managed_updates": True, "environment": {}}),
    )
    monkeypatch.setattr(supervision, "os", SimpleNamespace(environ={}))
    if entry == "baseline_child":
        assert supervision.child(tmp_path, "updater") == 0
    elif entry == "library":
        assert service_updates.watch(tmp_path) == 0
    else:
        action = "watch" if entry == "standalone" else "check"
        assert service_updates.main([action, "--state-dir", str(tmp_path)]) == 0
    rows = aggregate.preview(installation)
    owned = entry in {"standalone", "baseline_child"}
    assert sum(row["count"] for row in rows if row["metric"] == "submissions") == int(owned)
    assert all(row["surface"] == "headless" for row in rows)
    assert measured._owner.get() is None


@pytest.mark.parametrize("ending", ["success", "unconfirmed", "restored", "interrupted"])
def test_operations_keep_only_fixed_outcomes_and_do_not_infer_interrupted_work(
    installation, ending
):
    with measured.automatic_watcher():
        error = (
            service_updates.UpdateInterrupted
            if ending == "interrupted"
            else ValueError
            if ending in {"unconfirmed", "restored"}
            else None
        )
        with pytest.raises(error) if error else nullcontext():
            with measured.operation("apply") as attempt:
                assert attempt is not None
                if ending == "restored":
                    attempt.restored_after_failure()
                if error:
                    raise error("PRIVATE_HOST_PATH_TOKEN_AND_VERSION")
    rows = aggregate.preview(installation)
    outcomes = [row["bucket"] for row in rows if row["metric"] == "outcomes"]
    assert outcomes == (
        [] if ending == "interrupted" else ["failed" if ending == "restored" else ending]
    )
    assert b"PRIVATE" not in (installation / policy.DATABASE_NAME).read_bytes()
    assert not any(row["metric"] in {"rss_bytes", "cpu_millicores"} for row in rows)


@pytest.mark.parametrize("policy_change", ["opt_out", "company_off", "new_generation"])
@pytest.mark.parametrize("action", ["apply", "verify"])
def test_host_observation_rechecks_its_original_authority(
    installation, monkeypatch, policy_change, action
):
    with measured.automatic_watcher():
        with measured.operation(action) as attempt:
            assert attempt is not None
            if policy_change == "opt_out":
                policy.configure(installation, {"enabled": False, "expected_revision": 0})
            elif policy_change == "company_off":
                path = installation.parent / "company.json"
                path.write_text(
                    json.dumps({"schema_version": 1, "enabled": False, "metric_groups": []})
                )
            else:
                (installation / policy.DATABASE_NAME).unlink()
                policy.configure(
                    installation,
                    {"enabled": True, "expected_revision": 0, "disclosure_version": 1},
                )
    assert aggregate.preview(installation) == []


def test_telemetry_errors_cannot_change_update_return_or_original_exception(
    installation, monkeypatch
):
    def unavailable(*args, **kwargs):
        raise OSError("PRIVATE_STORAGE")

    monkeypatch.setattr(workflow, "begin", unavailable)
    with measured.automatic_watcher():
        with measured.operation("stage") as attempt:
            assert attempt is None
        with pytest.raises(ValueError, match="original update error"):
            with measured.operation("apply"):
                raise ValueError("original update error")
    assert aggregate.preview(installation) == []


def clock():
    elapsed, sleeps = [0.0], []

    def sleep(seconds):
        sleeps.append(seconds)
        elapsed[0] += seconds

    return SimpleNamespace(
        monotonic=lambda: elapsed[0], sleep=sleep, elapsed=elapsed, sleeps=sleeps
    )


@pytest.mark.parametrize("owned", [True, False])
def test_unavailable_or_unowned_waits_do_no_telemetry_io(tmp_path, monkeypatch, owned):
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", not owned)
    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://example.invalid/v1/report")
    monkeypatch.setattr(policy, "status", lambda: pytest.fail("No policy I/O permitted"))
    timer = clock()
    with measured.automatic_watcher() if owned else nullcontext():
        with measured.operation("stage") as attempt:
            assert attempt is None
        measured.quiet_wait(10, clock=timer)
    assert timer.sleeps == [10] and timer.elapsed == [10]
    assert not list(tmp_path.iterdir())


def test_existing_wait_opportunities_are_limited_without_new_wakeups(installation, monkeypatch):
    calls = []
    real_status = policy.status

    def status():
        calls.append(timer.monotonic())
        return real_status()

    timer = clock()
    monkeypatch.setattr(policy, "status", status)
    with measured.automatic_watcher():
        for _ in range(7):
            measured.quiet_wait(10, clock=timer)
    assert calls == [0, 60]
    assert timer.sleeps == [10] * 7
    monkeypatch.setattr(policy, "status", real_status)
    assert aggregate.preview(installation) == []


def test_automatic_watcher_cannot_create_or_acknowledge_a_host_choice(
    installation, tmp_path, monkeypatch
):
    untouched = tmp_path / "different-account-data"
    monkeypatch.setattr(policy, "default_directory", lambda: untouched)
    with measured.automatic_watcher():
        with measured.operation("rollback") as attempt:
            assert attempt is None
        measured.quiet_wait(10, clock=clock())
    assert policy.status()["reason"] == "disclosure_required"
    assert not untouched.exists()


@pytest.mark.parametrize("failure", [ValueError, service_updates.UpdateInterrupted])
def test_optional_delivery_error_preserves_remaining_wait_but_shutdown_does_not_wait(
    installation, monkeypatch, failure
):
    timer = clock()
    active = workflow.begin("update.apply", "headless")
    active.finish("success")

    async def failed(deadline, current, clock):
        assert deadline == 10
        clock.elapsed[0] += 3
        raise failure("PRIVATE_DELIVERY_DETAIL")

    monkeypatch.setattr(measured, "_deliver_until", failed)
    with measured.automatic_watcher():
        if failure is ValueError:
            measured.quiet_wait(10, clock=timer)
            assert timer.sleeps == [7] and timer.elapsed == [10]
        else:
            with pytest.raises(service_updates.UpdateInterrupted):
                measured.quiet_wait(10, clock=timer)
            assert timer.sleeps == [] and timer.elapsed == [3]
