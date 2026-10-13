"""Suspended clocks and corrections cannot defer or storm managed update checks."""

from datetime import datetime, timezone
import os
from types import SimpleNamespace

import pytest

from mnemion.service import update_schedule
from mnemion.service import update_state as state_io

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Managed updates run on Unix")


@pytest.fixture
def schedule(tmp_path):
    clock = SimpleNamespace(wall=1_791_872_000.0, monotonic_value=1000.0)
    clock.time = lambda: clock.wall
    clock.monotonic = lambda: clock.monotonic_value
    root = state_io.directory(tmp_path / "updates")
    return update_schedule.UpdateSchedule(root, clock=clock), clock, root


def test_resume_uses_elapsed_wall_time_when_the_monotonic_clock_was_frozen(schedule):
    timer, clock, _ = schedule
    timer.after(21600, reason="periodic")
    clock.monotonic_value += 5.4 * 3600
    clock.wall += 16 * 3600
    assert timer.due()


def test_backwards_wall_clock_does_not_postpone_the_monotonic_deadline(schedule):
    timer, clock, _ = schedule
    timer.after(21600, reason="periodic")
    clock.monotonic_value += 21600
    clock.wall -= 86400
    assert timer.due()


def test_repeated_forward_clock_jumps_cannot_remove_the_short_retry_floor(schedule):
    timer, clock, _ = schedule
    for _ in range(3):
        timer.after(21600, reason="periodic")
        clock.wall += 86400
        clock.monotonic_value += 29
        assert not timer.due()
        clock.monotonic_value += 1
        assert timer.due()


def test_diagnostics_record_the_actual_jittered_deadline_and_failure_attempt(schedule, monkeypatch):
    timer, clock, root = schedule
    monkeypatch.setattr(update_schedule.time, "time", clock.time)
    timer.after(23760, reason="periodic")
    before = update_schedule.schedule_status(root, enabled=True, interval=21600, last_check=None)
    assert not before["overdue"] and not before["schedule_estimated"]
    assert datetime.fromisoformat(before["next_check_at"]).timestamp() == clock.wall + 23760
    clock.wall += 86400
    assert update_schedule.schedule_status(root, enabled=True, interval=21600, last_check=None)[
        "overdue"
    ]
    timer.attempt()
    attempted = datetime.fromtimestamp(clock.wall, timezone.utc)
    # A failed network request also gets a new bounded wait, even if last-check
    # still describes an older success.
    timer.after(19440, reason="periodic")
    after = update_schedule.schedule_status(root, enabled=True, interval=21600, last_check=None)
    assert datetime.fromisoformat(after["last_attempt_at"]) == attempted
    assert not after["overdue"]
    stored = state_io.read(root / "schedule.json")
    assert not any("monotonic" in key for key in stored)


def test_disabled_and_older_runtime_status_do_not_invent_a_scheduled_check(schedule, monkeypatch):
    _, clock, root = schedule
    monkeypatch.setattr(update_schedule.time, "time", clock.time)
    unknown = update_schedule.schedule_status(root, enabled=True, interval=21600, last_check=None)
    assert unknown["next_check_at"] is None and not unknown["overdue"]
    old = {"checked_at": datetime.fromtimestamp(clock.wall - 86400, timezone.utc).isoformat()}
    estimated = update_schedule.schedule_status(root, enabled=True, interval=21600, last_check=old)
    assert estimated["overdue"] and estimated["schedule_estimated"]
    disabled = update_schedule.schedule_status(root, enabled=False, interval=21600, last_check=old)
    assert not disabled["overdue"] and disabled["next_check_at"] is None


@pytest.mark.parametrize("value", [None, "not-a-date", "2026-10-13T12:00:00"])
def test_invalid_persisted_schedule_is_not_reported_as_healthy(schedule, value):
    _, _, root = schedule
    state_io.write(root / "schedule.json", {"format": 1, "next_check_at": value})
    with pytest.raises(update_schedule.ManifestError, match="Invalid managed update schedule"):
        update_schedule.schedule_status(root, enabled=True, interval=21600, last_check=None)
