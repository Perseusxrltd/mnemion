"""Idle backoff and the process-local librarian wake.

Loop tests drive the real runner thread with scripted events so a wait records
its timeout and blocks until the test releases it or the event is set. They do
not sleep for the backoff itself. The route test uses PostgreSQL.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from mnemion.service.api import create_app
from mnemion.service.librarian_models import LibrarianSettingsInput
from mnemion.service.librarian_provider import LibrarianRegistry
from mnemion.service.librarian_runner import LibrarianRunner
from service_tests.test_librarian import provider_fixture, save

_IDLE_CAP = (2, 4, 8, 16, 30, 30)


class ScriptedEvent(threading.Event):
    """Event.wait that records the timeout and waits for the test, not the clock."""

    def __init__(self):
        super().__init__()
        self.timeouts = []
        self._generation = 0
        self._waiting = False
        self._release = False
        self._gate = threading.Condition()

    def set(self):
        with self._gate:
            super().set()
            self._gate.notify_all()

    def wait(self, timeout=None):
        with self._gate:
            self.timeouts.append(timeout)
            self._generation += 1
            if super().is_set():
                return True
            self._waiting = True
            self._gate.notify_all()
            try:
                while not super().is_set() and not self._release:
                    self._gate.wait()
            finally:
                self._waiting = False
                self._release = False
                self._gate.notify_all()
            return super().is_set()

    def generation(self):
        with self._gate:
            if not self._gate.wait_for(lambda: self._waiting, 5):
                raise AssertionError(f"runner did not sleep; waits={list(self.timeouts)}")
            return self._generation

    def until_waiting(self, after=None):
        with self._gate:

            def parked():
                return self._waiting and (after is None or self._generation != after)

            if not self._gate.wait_for(parked, 5):
                raise AssertionError(f"runner did not sleep; waits={list(self.timeouts)}")
            return self.timeouts[-1]

    def force_timeout(self):
        with self._gate:
            if not self._gate.wait_for(lambda: self._waiting, 5):
                raise AssertionError(f"runner was not asleep; waits={list(self.timeouts)}")
            generation = self._generation
            self._release = True
            self._gate.notify_all()
            if not self._gate.wait_for(
                lambda: not self._waiting or self._generation != generation, 5
            ):
                raise AssertionError("runner did not leave its wait")

    def snapshot(self):
        with self._gate:
            return list(self.timeouts)


class DatabaseGuard:
    def __init__(self):
        self.used = False

    def __getattr__(self, name):
        self.used = True
        raise AssertionError(f"unexpected database access: {name}")


def idle_service(providers=(object(),)):
    return SimpleNamespace(
        db=SimpleNamespace(worker=False, pool=None),
        registry=SimpleNamespace(providers=providers, fingerprints=()),
    )


class Probe(LibrarianRunner):
    def __init__(self, behavior, *, can_start=None, service=None):
        super().__init__(service or idle_service(), can_start=can_start)
        self._behavior = behavior
        self.checks = 0

    def run_once(self):
        self.checks += 1
        return self._behavior(self)


@contextmanager
def paced(runner):
    runner._wake = ScriptedEvent()
    runner._stop = ScriptedEvent()
    runner.start()
    try:
        yield runner
    finally:
        runner.stop()


def assert_capped_idle(runner, samples):
    delays = []
    for expected in range(1, 7):
        delays.append(runner._wake.until_waiting())
        assert samples() == expected
        runner._wake.force_timeout()
    assert delays == list(_IDLE_CAP)


def release_until(runner, delay):
    for _ in range(8):
        seen = runner._wake.until_waiting()
        if seen == delay:
            return
        runner._wake.force_timeout()
    raise AssertionError(f"backoff did not reach {delay}; waits={runner._wake.snapshot()}")


def test_idle_backoff_reaches_thirty_seconds_and_does_not_poll_while_asleep():
    runner = Probe(lambda probe: False)
    with paced(runner):
        assert runner._thread.name == "mnemion-librarian"
        assert_capped_idle(runner, lambda: runner.checks)


def test_wake_interrupts_the_long_idle_wait_and_resets_backoff():
    runner = Probe(lambda probe: False)
    with paced(runner):
        release_until(runner, 30)
        sleeping = runner._wake.generation()
        before = runner.checks
        runner.wake()
        assert runner._wake.until_waiting(after=sleeping) == 2
        assert runner.checks == before + 1


def test_wake_during_an_empty_check_is_not_lost():
    def behavior(probe):
        if probe.checks == 1:
            probe.wake()
        return False

    runner = Probe(behavior)
    with paced(runner):
        # The wake is set inside the first empty check. The loop must check
        # again without the test releasing that wait as a timeout.
        assert runner._wake.until_waiting() == 2
        assert runner.checks == 2
        assert runner._wake.snapshot() == [2, 2]


def test_stop_interrupts_the_maximum_idle_wait():
    runner = Probe(lambda probe: False)
    runner._wake = ScriptedEvent()
    runner._stop = ScriptedEvent()
    runner.start()
    thread = runner._thread
    try:
        release_until(runner, 30)
        runner.stop()
        assert thread is not None and not thread.is_alive()
    finally:
        runner.stop()


def test_active_work_keeps_two_second_pacing_when_woken():
    def behavior(probe):
        if probe.checks <= 2:
            probe.wake()
            return True
        return False

    runner = Probe(behavior)
    with paced(runner):
        assert runner._stop.until_waiting() == 2
        assert runner.checks == 1
        for _ in range(5):
            runner.wake()
        assert runner.checks == 1
        assert runner._stop.snapshot() == [2]
        assert runner._wake.snapshot() == []
        runner._stop.force_timeout()
        assert runner._stop.until_waiting() == 2
        assert runner.checks == 2
        runner._stop.force_timeout()
        assert runner._wake.until_waiting() == 2
        assert runner.checks == 3
        runner._wake.force_timeout()
        assert runner._wake.until_waiting() == 4
        assert runner.checks == 4
        assert runner._stop.snapshot() == [2, 2]


def test_resource_deferral_stays_on_the_idle_backoff():
    calls = {"n": 0}
    pool = DatabaseGuard()
    service = idle_service()
    service.db.pool = pool

    def can_start():
        calls["n"] += 1
        return False

    runner = LibrarianRunner(service, can_start=can_start)
    with paced(runner):
        assert_capped_idle(runner, lambda: calls["n"])
        assert pool.used is False


def test_transient_failure_stays_on_the_idle_backoff():
    def behavior(probe):
        raise RuntimeError("database unavailable")

    runner = Probe(behavior)
    with paced(runner):
        assert_capped_idle(runner, lambda: runner.checks)
        assert runner._thread.is_alive()


def test_absent_providers_do_not_start_a_worker():
    runner = LibrarianRunner(idle_service(providers=()))
    runner.wake()
    runner.start()
    try:
        assert runner._thread is None
    finally:
        runner.stop()


class _CommitVisibleWake(threading.Event):
    def __init__(self, observe):
        super().__init__()
        self.states = []
        self._observe = observe

    def set(self):
        self.states.append(self._observe())
        super().set()


def test_create_run_wakes_after_commit_only_when_queued(env, monkeypatch):
    monkeypatch.setenv("MNEMION_LIBRARIAN_DISABLED", "1")
    provider, requests = provider_fixture()
    registry = LibrarianRegistry({provider.profile.id: provider})
    app = create_app(env.db, env.embedder, librarian_registry=registry)
    app.state.librarian.configure(
        env.owner,
        env.space,
        LibrarianSettingsInput(
            expected_version=0,
            profile_id=provider.profile.id,
            approve_network_egress=provider.profile.network_egress,
        ),
    )

    def visible_queued_state():
        with env.db.transaction(env.owner) as conn:
            row = conn.execute(
                """SELECT state FROM mnemion.librarian_runs
                   WHERE space_id=%s AND state='queued'""",
                (env.space,),
            ).fetchone()
        return row["state"] if row else "absent"

    def run_count():
        with env.db.transaction(env.owner) as conn:
            return conn.execute(
                "SELECT count(*) AS n FROM mnemion.librarian_runs WHERE space_id=%s",
                (env.space,),
            ).fetchone()["n"]

    base = f"/v1/spaces/{env.space}/librarian"
    with TestClient(app) as api:
        runner = app.state.librarian_runner
        assert runner._thread is None
        wake = _CommitVisibleWake(visible_queued_state)
        runner._wake = wake
        refused = api.post(
            base + "/runs",
            json={"mode": "organize"},
            headers={"Idempotency-Key": "unauthorized"},
        )
        assert refused.status_code == 401 and wake.states == []
        api.headers["Authorization"] = "Bearer " + env.token
        assert api.get(base).status_code == 200
        assert api.get(base + "/models").status_code == 200
        assert api.get(base + "/runs").status_code == 200
        assert api.get(base + "/coverage").status_code == 200
        assert wake.states == []
        missing_key = api.post(base + "/runs", json={"mode": "organize"})
        assert missing_key.status_code == 422 and wake.states == []
        empty = api.post(
            base + "/runs",
            json={"mode": "organize"},
            headers={"Idempotency-Key": "empty-library"},
        )
        assert empty.status_code == 202, empty.text
        assert empty.json()["state"] == "completed" and empty.json()["selected"] == 0
        assert wake.states == []
        before_reject = run_count()
        missing = api.post(
            base + "/runs",
            json={"mode": "organize", "memory_ids": [str(uuid4())]},
            headers={"Idempotency-Key": "missing-memory"},
        )
        assert missing.status_code == 404 and wake.states == []
        assert run_count() == before_reject
        save(env)
        queued = api.post(
            base + "/runs",
            json={"mode": "organize"},
            headers={"Idempotency-Key": "queued-run"},
        )
        assert queued.status_code == 202, queued.text
        body = queued.json()
        assert body["state"] == "queued" and body["selected"] == 1
        assert wake.states == ["queued"]
        assert api.get(base + f"/runs/{body['id']}").status_code == 200
        assert api.get(base + "/runs").status_code == 200
        assert api.get(base + "/proposals").status_code == 200
        assert wake.states == ["queued"]
        replay = api.post(
            base + "/runs",
            json={"mode": "organize"},
            headers={"Idempotency-Key": "queued-run"},
        )
        assert replay.status_code == 202, replay.text
        assert replay.json()["id"] == body["id"] and replay.json()["state"] == "queued"
        assert wake.states == ["queued", "queued"]
        conflict = api.post(
            base + "/runs",
            json={"mode": "review"},
            headers={"Idempotency-Key": "second-run"},
        )
        assert conflict.status_code == 409 and wake.states == ["queued", "queued"]
        cancelled = api.post(base + f"/runs/{body['id']}/cancel")
        assert cancelled.status_code == 200 and cancelled.json()["state"] == "cancelled"
        assert wake.states == ["queued", "queued"]
        assert requests == []
        assert runner._thread is None
