"""Real private-store spending and process fences; no production collector."""

from __future__ import annotations

import asyncio
from contextlib import closing
import json
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from mnemion.product_telemetry import aggregate, delivery, policy


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root, company = tmp_path / "private", tmp_path / "company.json"
    now = [1700000000000]
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", True)
    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://example.invalid/v3/report")
    monkeypatch.setattr(policy, "company_policy_file", lambda: company)
    monkeypatch.setattr(delivery, "_now_ms", lambda: now[0])
    monkeypatch.setattr(aggregate, "_day", lambda: now[0] // delivery.DAY_MS)
    current = policy.configure(
        root,
        {"enabled": True, "expected_revision": 0, "disclosure_version": policy.DISCLOSURE_VERSION},
    )
    budget = delivery.DeliveryBudget(root, policy_path=company)

    def fill():
        state = policy.status(root)
        assert aggregate.record(
            root,
            {"kind": "submission", "workflow": "memory.recall", "surface": "native_agent"},
            expected_revision=state["revision"],
            expected_generation=state["store_generation"],
        )

    def reserve(**extra):
        state = policy.status(root)
        return budget.reserve(
            expected_revision=state["revision"],
            expected_generation=state["store_generation"],
            network="unmetered",
            constrained=False,
            **extra,
        )

    def sql(query, args=()):
        with closing(sqlite3.connect(root / policy.DATABASE_NAME)) as db:
            result = db.execute(query, args).fetchall()
            db.commit()
            return result

    return SimpleNamespace(
        root=root,
        company=company,
        now=now,
        initial=current,
        budget=budget,
        fill=fill,
        reserve=reserve,
        sql=sql,
    )


def test_unavailable_network_pressure_and_unavailable_collection_never_spend(
    installation, monkeypatch
):
    f = installation
    f.fill()
    for network, constrained in [("unknown", False), ("metered", False), ("unmetered", True)]:
        assert (
            f.budget.reserve(
                expected_revision=f.initial["revision"],
                expected_generation=f.initial["store_generation"],
                network=network,
                constrained=constrained,
            )
            is None
        )
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", False)
    assert f.reserve() is None
    assert f.sql("SELECT count(*) FROM delivery_attempts") == [(0,)]
    assert f.sql("SELECT count(*) FROM pending")[0][0] > 0


def test_spending_survives_crash_restart_cancel_and_opt_out_reenable(installation):
    f = installation
    f.fill()
    report = f.reserve()
    assert report is not None and f.budget.current(report)
    before = report.preview()
    assert before["body_bytes"] == 25
    assert before["view"] == "bounded_summary"
    assert before["randomized_sign"] is None
    assert before["aggregation"] == "bounded_summary_publication_noise"
    assert f.sql("SELECT count(*) FROM pending") == [(0,)]
    assert policy.status(f.root)["delivery_budget"]["attempts_in_rolling_week"] == 1
    f.budget.cancel(report)
    assert report.preview() is None and report._body == b"\0" * 25
    f.budget = delivery.DeliveryBudget(f.root, policy_path=f.company)
    off = policy.configure(f.root, {"enabled": False, "expected_revision": 0})
    policy.configure(
        f.root,
        {
            "enabled": True,
            "expected_revision": off["revision"],
            "expected_generation": off["store_generation"],
            "disclosure_version": policy.DISCLOSURE_VERSION,
        },
    )
    f.fill()
    assert f.reserve() is None
    assert f.sql("SELECT reserved_bytes FROM delivery_attempts") == [(65536,)]
    assert f.sql("SELECT lease_token, lease_deadline_ms FROM delivery_state") == [(None, 0)]
    assert "lease_token" not in json.dumps(policy.status(f.root)["delivery_budget"])
    assert "at_ms" not in json.dumps(policy.status(f.root)["delivery_budget"])


def test_minimum_spacing_jitter_and_seven_slot_retention_are_shared(installation):
    f = installation
    for index in range(9):
        f.fill()
        report = f.reserve()
        assert report is not None
        next_ms = f.sql("SELECT next_ms FROM delivery_state")[0][0]
        assert f.now[0] + 86400000 <= next_ms <= f.now[0] + 90000000
        f.budget.cancel(report)
        assert f.sql("SELECT count(*) FROM delivery_attempts")[0][0] <= 7
        f.now[0] = next_ms - 1
        f.fill()
        assert f.reserve() is None
        f.now[0] += 1
    assert (f.root / policy.DATABASE_NAME).stat().st_size <= 96 * 1024
    assert not (f.root / (policy.DATABASE_NAME + "-wal")).exists()


@pytest.mark.parametrize("count,step", [(7, 36000000), (4, 3600000)])
def test_inconsistent_preexisting_attempt_history_cannot_increase_allowance(
    installation, count, step
):
    f = installation
    f.sql("UPDATE delivery_state SET clock_ms=?, next_ms=?", (f.now[0], f.now[0]))
    for index in range(count):
        f.sql(
            "INSERT INTO delivery_attempts VALUES (?, ?, 65536)", (index, f.now[0] - index * step)
        )
    f.fill()
    assert f.reserve() is None
    assert f.sql("SELECT count(*) FROM delivery_attempts") == [(count,)]


def test_clock_rollback_expiry_and_policy_changes_erase_old_report_without_refund(installation):
    f = installation
    f.fill()
    report = f.reserve()
    f.now[0] -= 1
    assert not f.budget.current(report)
    assert report._body == b"\0" * 25
    assert f.sql("SELECT lease_token, lease_deadline_ms FROM delivery_state") == [(None, 0)]
    assert f.reserve() is None
    assert policy.status(f.root)["delivery_budget"]["state"] == "clock_rollback"
    f.now[0] = f.sql("SELECT next_ms FROM delivery_state")[0][0]
    f.fill()
    report = f.reserve()
    f.now[0] += 5000
    writes = []
    assert not f.budget.guarded_write(report, lambda packet: writes.append(packet) or True)
    assert writes == []
    assert f.sql("SELECT count(*) FROM delivery_attempts") == [(2,)]
    assert f.sql("SELECT lease_token FROM delivery_state") == [(None,)]


def test_company_restriction_is_checked_again_at_actual_write_boundary(installation):
    f = installation
    f.company.write_text(
        json.dumps({"schema_version": 1, "enabled": True, "metric_groups": ["usage"]})
    )
    f.fill()
    report = f.reserve()
    f.company.write_text(
        json.dumps({"schema_version": 1, "enabled": True, "metric_groups": ["resources"]})
    )
    writes = []
    assert not f.budget.guarded_write(report, lambda packet: writes.append(packet) or True)
    assert writes == [] and report._body == b"\0" * 25
    assert f.sql("SELECT count(*) FROM delivery_attempts") == [(1,)]
    assert f.sql("SELECT lease_token FROM delivery_state") == [(None,)]


def test_completed_and_throwing_handoffs_are_single_use_and_never_refunded(installation):
    f = installation
    f.fill()
    report = f.reserve()
    writes = []
    assert f.budget.guarded_write(report, lambda packet: writes.append(packet) or True)
    assert len(writes) == 1 and len(writes[0]) == 25
    assert not f.budget.guarded_write(report, lambda packet: writes.append(packet) or True)
    assert report._body == b"\0" * 25
    assert f.budget.current(report)
    f.budget.cancel(report)
    assert f.sql("SELECT lease_token FROM delivery_state") == [(None,)]
    f.now[0] = f.sql("SELECT next_ms FROM delivery_state")[0][0]
    f.fill()
    report = f.reserve()

    def throws(packet):
        raise RuntimeError("PRIVATE_SENTINEL")

    assert not f.budget.guarded_write(report, throws)
    assert f.sql("SELECT count(*) FROM delivery_attempts") == [(2,)]
    assert b"PRIVATE_SENTINEL" not in (f.root / policy.DATABASE_NAME).read_bytes()


@pytest.mark.parametrize("abort_raises", [False, True])
@pytest.mark.parametrize("handed_off", [False, True])
def test_in_flight_watcher_aborts_after_other_process_opt_out_and_clears_memory(
    installation, abort_raises, handed_off
):
    f = installation
    f.fill()
    report = f.reserve()
    if handed_off:
        assert f.budget.guarded_write(report, lambda _packet: True)
        assert f.budget.current(report)
    program = """
import json,sys
from pathlib import Path
from mnemion.product_telemetry import policy
result=policy.configure(Path(sys.argv[1]),{'enabled':False,'expected_revision':0})
print(json.dumps({'enabled':result['user_enabled'],'pending':result['pending_records']}))
"""

    async def run():
        cancelled = asyncio.Event()
        calls = []

        def abort():
            calls.append(1)
            cancelled.set()
            if abort_raises:
                raise RuntimeError("PRIVATE_ABORT_SENTINEL")

        task = asyncio.create_task(f.budget.watch(report, abort))
        await asyncio.sleep(0)
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            program,
            str(f.root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(child.communicate(), 10)
        assert child.returncode == 0 and stderr == b"", stderr.decode(errors="replace")
        assert json.loads(stdout) == {"enabled": False, "pending": 0}
        await asyncio.wait_for(cancelled.wait(), 1)
        await task
        assert calls == [1]

    asyncio.run(run())
    assert report.preview() is None and report._body == b"\0" * 25
    assert f.sql("SELECT count(*) FROM delivery_attempts") == [(1,)]
    assert f.sql("SELECT lease_token FROM delivery_state") == [(None,)]


def test_concurrent_handoffs_do_not_repeat_or_cancel_the_winning_request(installation):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    f = installation
    f.fill()
    report = f.reserve()
    entered = Barrier(2)
    writes = []

    def handoff():
        entered.wait(timeout=5)
        return f.budget.guarded_write(report, lambda body: writes.append(body) or True)

    with ThreadPoolExecutor(max_workers=2) as executor:
        tasks = [executor.submit(handoff) for _ in range(2)]
        assert sorted(task.result(timeout=10) for task in tasks) == [False, True]
    assert len(writes) == 1
    assert f.budget.current(report)
    assert report._body == b"\0" * 25
    f.budget.cancel(report)
    assert f.sql("SELECT lease_token FROM delivery_state") == [(None,)]


def test_busy_or_damaged_store_never_writes_or_recreates_settings(installation):
    f = installation
    f.fill()
    with closing(sqlite3.connect(f.root / policy.DATABASE_NAME)) as other:
        other.execute("BEGIN IMMEDIATE")
        assert f.reserve() is None
    assert f.sql("SELECT count(*) FROM delivery_attempts") == [(0,)]
    report = f.reserve()
    path = f.root / policy.DATABASE_NAME
    path.write_bytes(b"broken PRIVATE_SENTINEL")
    assert not f.budget.current(report)
    assert f.reserve() is None
    assert policy.status(f.root)["reason"] == "storage_unavailable"
    assert path.read_bytes() == b"broken PRIVATE_SENTINEL"


def test_v3_migration_keeps_choice_generation_and_does_not_fabricate_a_disclosure(installation):
    f = installation
    off = policy.configure(f.root, {"enabled": False, "expected_revision": 0})
    f.sql("DROP TABLE delivery_attempts")
    f.sql("DROP TABLE delivery_state")
    f.sql("DROP TABLE report_review")
    f.sql("ALTER TABLE preferences DROP COLUMN connection_mode")
    f.sql("PRAGMA user_version=3")
    before = policy.status(f.root)
    assert (
        before["reason"] == "user_disabled"
        and before["delivery_budget"]["state"] == "upgrade_required"
    )
    after = policy.configure(f.root, {"enabled": False, "expected_revision": 0})
    assert after["store_generation"] == off["store_generation"]
    assert after["reason"] == "user_disabled" and after["disclosure_version"] == 0
    assert f.sql("PRAGMA user_version") == [(policy.STORAGE_VERSION,)]


def test_v4_upgrade_preserves_spending_and_connection_change_cancels_lease(installation):
    f = installation
    f.fill()
    report = f.reserve()
    assert report is not None
    spent = f.sql("SELECT * FROM delivery_attempts")
    f.sql("DROP TABLE report_review")
    f.sql("ALTER TABLE preferences DROP COLUMN connection_mode")
    f.sql("PRAGMA user_version=4")
    before = policy.status(f.root)
    assert before["connection_mode"] == "auto"
    assert before["delivery_budget"]["state"] == "upgrade_required"
    after = policy.configure(
        f.root,
        {
            "enabled": True,
            "expected_revision": before["revision"],
            "expected_generation": before["store_generation"],
            "disclosure_version": policy.DISCLOSURE_VERSION,
            "connection_mode": "metered",
        },
    )
    assert after["revision"] == before["revision"] + 1
    assert after["store_generation"] == before["store_generation"]
    assert f.sql("SELECT * FROM delivery_attempts") == spent
    assert not f.budget.current(report)
    f.fill()
    f.now[0] += delivery.DAY_MS + delivery.JITTER_MS
    assert f.reserve() is None


def test_unmetered_declaration_only_resolves_unknown_and_cannot_override_restrictions(installation):
    f = installation
    current = policy.configure(
        f.root,
        {
            "enabled": True,
            "expected_revision": f.initial["revision"],
            "expected_generation": f.initial["store_generation"],
            "disclosure_version": policy.DISCLOSURE_VERSION,
            "connection_mode": "unmetered",
        },
    )
    f.fill()

    def attempt(network, constrained=False):
        return f.budget.reserve(
            expected_revision=current["revision"],
            expected_generation=current["store_generation"],
            network=network,
            constrained=constrained,
        )

    assert attempt("metered") is None
    assert attempt("unknown", True) is None
    assert f.sql("SELECT count(*) FROM delivery_attempts") == [(0,)]
    report = attempt("unknown")
    assert report is not None
    off = policy.configure(
        f.root, {"enabled": False, "expected_revision": 0, "connection_mode": "auto"}
    )
    assert off["connection_mode"] == "unmetered"
    assert not f.budget.current(report)
    assert attempt("unknown") is None
    assert f.sql("SELECT count(*) FROM delivery_attempts") == [(1,)]


def test_async_function_is_never_invoked_under_the_final_write_lock(installation):
    f = installation
    f.fill()
    report = f.reserve()
    invoked = []

    async def invalid(packet):
        invoked.append(packet)
        return True

    assert not f.budget.guarded_write(report, invalid)
    assert invoked == [] and report.preview() is None


def test_old_generation_cannot_send_or_cancel_a_new_store_reservation(installation):
    f = installation
    f.fill()
    old = f.reserve()
    (f.root / policy.DATABASE_NAME).unlink()
    new = policy.configure(
        f.root,
        {"enabled": True, "expected_revision": 0, "disclosure_version": policy.DISCLOSURE_VERSION},
    )
    assert old.generation != new["store_generation"]
    f.fill()
    report = f.reserve()
    f.budget.cancel(old)
    assert f.budget.current(report)
    assert not f.budget.current(old)


def test_stalled_wall_clock_cannot_extend_a_prepared_report_lifetime(installation, monkeypatch):
    f = installation
    elapsed = [100.0]
    monkeypatch.setattr(delivery, "_monotonic", lambda: elapsed[0])
    f.fill()
    report = f.reserve()
    assert report is not None and f.budget.current(report)
    elapsed[0] += 5.001
    writes = []
    assert not f.budget.guarded_write(report, lambda packet: writes.append(packet) or True)
    assert writes == [] and report._body == b"\0" * 25
    assert f.sql("SELECT lease_token FROM delivery_state") == [(None,)]
    assert f.sql("SELECT count(*) FROM delivery_attempts") == [(1,)]
