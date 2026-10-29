"""Real SQLite review transactions, privacy fences and exact-byte delivery."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import base64
import json
import sqlite3

import pytest

from mnemion.product_telemetry import (
    aggregate,
    delivery,
    inspection,
    policy,
    review,
    review_storage,
)

DAY = 86400000


@pytest.fixture
def subject(tmp_path, monkeypatch):
    root, company = tmp_path / "private", tmp_path / "company.json"
    clock = {
        "now": 20000 * DAY + 100000,
        "elapsed": 123456,
        "epoch": "a" * 32,
        "reads": 0,
        "initializations": 0,
    }
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", True)
    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://example.invalid/v3/report")
    monkeypatch.setattr(policy, "company_policy_file", lambda: company)
    monkeypatch.setattr(policy, "transport_available", lambda: True)
    monkeypatch.setattr(aggregate, "_day", lambda: clock["now"] // DAY)
    monkeypatch.setattr(delivery, "_now_ms", lambda: clock["now"])
    monkeypatch.setattr(inspection, "_now_ms", lambda: clock["now"])

    def read(*, initialize=False):
        clock["reads"] += 1
        clock["initializations"] += int(initialize)
        return {"epoch": clock["epoch"], "elapsed_ms": clock["elapsed"]} if clock["epoch"] else None

    monkeypatch.setattr(inspection, "read_review_clock", read)
    state = policy.configure(
        root,
        {"enabled": True, "expected_revision": 0, "disclosure_version": policy.DISCLOSURE_VERSION},
    )

    class Subject:
        def __init__(self):
            self.root, self.company, self.clock = root, company, clock
            self.state = state
            self.budget = delivery.DeliveryBudget(root)

        def request(self, **extra):
            status = inspection.status(root)
            return {
                "expected_revision": status["status"]["revision"],
                "expected_generation": status["status"]["store_generation"],
                "expected_review_token": status["review"]["token"],
                **extra,
            }

        def action(self, action, **extra):
            return inspection.execute(root, action, self.request(**extra))

        def pause(self):
            return self.action("review_mode", mode="review")

        def record(self):
            status = policy.status(root)
            return aggregate.record(
                root,
                {"kind": "submission", "workflow": "memory.recall", "surface": "native_agent"},
                expected_revision=status["revision"],
                expected_generation=status["store_generation"],
            )

        def reserve(self):
            status = policy.status(root)
            return self.budget.reserve(
                expected_revision=status["revision"],
                expected_generation=status["store_generation"],
                network="unmetered",
                constrained=False,
            )

        def stored(self):
            with closing(sqlite3.connect(root / policy.DATABASE_NAME)) as connection:
                return {
                    "review": review_storage.read(connection),
                    "pending": connection.execute(
                        "SELECT cell,count,window_day FROM pending ORDER BY cell"
                    ).fetchall(),
                    "contributions": connection.execute(
                        "SELECT scope,count,window_day FROM producer_budget ORDER BY scope"
                    ).fetchall(),
                    "spent": connection.execute(
                        "SELECT slot,at_ms,reserved_bytes FROM delivery_attempts"
                    ).fetchall(),
                }

    return Subject()


def test_pause_can_precede_permission_and_read_only_status_does_not_initialize(
    tmp_path, monkeypatch
):
    root = tmp_path / "private"
    monkeypatch.setattr(policy, "COLLECTION_AVAILABLE", False)
    monkeypatch.setattr(
        inspection,
        "read_review_clock",
        lambda **_: pytest.fail("A privacy preference cannot initialize clocks"),
    )
    request = {"expected_revision": 0, "expected_generation": None, "expected_review_token": None}
    assert inspection.status(root)["packet"] is None
    assert inspection.execute(root, "inspect_report", request)["packet"] is None
    assert not root.exists()
    paused = inspection.execute(root, "review_mode", {**request, "mode": "review"})
    assert paused["review"]["outcome"] == "paused"
    assert paused["status"]["disclosure_version"] == 0
    assert not paused["status"]["effective_enabled"]
    assert paused["status"]["pending_records"] == 0
    saved = inspection.execute(
        root,
        "inspect_report",
        {
            "expected_revision": paused["status"]["revision"],
            "expected_generation": paused["status"]["store_generation"],
            "expected_review_token": paused["review"]["token"],
        },
    )
    assert saved["packet"] is None and saved["message"] == "collection_not_permitted"


def test_empty_review_does_not_sample_randomness_or_start_a_clock(subject, monkeypatch):
    subject.pause()
    monkeypatch.setattr(inspection, "prepare", lambda *_, **__: pytest.fail("No input to encode"))
    result = subject.action("inspect_report")
    assert result["message"] == "no_observations" and result["packet"] is None
    assert subject.clock["reads"] == subject.clock["initializations"] == 0
    assert subject.stored()["spent"] == []


def test_repeated_inspection_keeps_exact_bytes_and_preserves_new_observations(subject, monkeypatch):
    subject.pause()
    assert subject.record()
    initial = subject.stored()
    first = subject.action("inspect_report")
    assert first["review"]["outcome"] == "held" and first["packet"]["body_bytes"] == 25
    assert first["packet"]["report_selection"] == "reviewed"
    assert first["packet"]["view"] == "bounded_summary"
    assert first["packet"]["aggregation"] == "bounded_summary_publication_noise"
    assert first["packet"]["randomized_sign"] is None
    assert first["packet"]["per_report_privacy_loss"] is None
    assert "not unique people" in first["packet"]["protected_unit"]
    held = subject.stored()
    assert held["pending"] == held["spent"] == []
    assert held["contributions"] == initial["contributions"]
    assert not subject.budget.eligible(
        expected_revision=subject.state["revision"],
        expected_generation=subject.state["store_generation"],
    )
    monkeypatch.setattr(
        inspection, "prepare", lambda *_, **__: pytest.fail("Inspection must not redraw")
    )
    assert subject.record()
    later = subject.stored()
    subject.clock["now"] += 10
    subject.clock["elapsed"] += 10
    repeated = subject.action("inspect_report")
    assert repeated["packet"] == first["packet"]
    assert repeated["review"]["token"] == first["review"]["token"]
    assert repeated["review"]["expires_ms"] == first["review"]["expires_ms"]
    assert subject.stored()["pending"] == later["pending"]
    assert subject.clock["initializations"] == 1
    reads = subject.clock["reads"]
    assert inspection.status(subject.root)["packet"] is None
    assert subject.clock["reads"] == reads


def test_approval_claims_exact_packet_once_without_erasing_later_counts(subject, monkeypatch):
    subject.pause()
    assert subject.record()
    packet = subject.action("inspect_report")["packet"]
    assert subject.record()
    pending = subject.stored()["pending"]
    assert subject.action("approve_report")["review"]["outcome"] == "approved"
    monkeypatch.setattr(
        delivery,
        "prepare_summary",
        lambda *_, **__: pytest.fail("Approved bytes cannot be regenerated"),
    )
    report = subject.reserve()
    assert report is not None and report.preview() == packet
    stored = subject.stored()
    assert stored["pending"] == pending and len(stored["spent"]) == 1
    assert stored["review"]["outcome"] == "consumed" and stored["review"]["report"] is None
    written = []
    assert subject.budget.guarded_write(report, lambda body: written.append(body) is None)
    assert written == [base64.b64decode(packet["body_base64"])]
    assert subject.reserve() is None
    subject.budget.cancel(report)
    assert len(subject.stored()["spent"]) == 1


def test_competing_owners_can_claim_only_once(subject):
    subject.pause()
    assert subject.record()
    packet = subject.action("inspect_report")["packet"]
    subject.action("approve_report")
    approved = subject.stored()
    with ThreadPoolExecutor(max_workers=2) as workers:
        # Nonblocking optional telemetry may make both contenders back off.
        # Force that case and prove the approved packet and allowance survive.
        with closing(subject.budget._open()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            assert list(workers.map(lambda _: subject.reserve(), range(2))) == [None, None]
            connection.rollback()
        assert subject.stored() == approved
        results = list(workers.map(lambda _: subject.reserve(), range(2)))
    assert sum(result is not None for result in results) <= 1
    if all(result is None for result in results):
        assert subject.stored() == approved
        results.append(subject.reserve())
    assert sum(result is not None for result in results) == 1
    assert len(subject.stored()["spent"]) == 1
    assert subject.reserve() is None
    for report in results:
        if report is not None:
            assert report.preview() == packet
            subject.budget.cancel(report)


@pytest.mark.parametrize("damage", ["legacy_wire", "reserved_byte", "group_mismatch"])
def test_a_review_cannot_approve_legacy_or_automatic_marked_bytes(subject, damage):
    subject.pause()
    assert subject.record()
    subject.action("inspect_report")
    stored = subject.stored()["review"]
    if damage == "legacy_wire":
        stored["report"]["packet"][0] = 1
    elif damage == "reserved_byte":
        stored["report"]["packet"][5] = 1
    else:
        stored["report"]["packet"][6] = 0
    with closing(sqlite3.connect(subject.root / policy.DATABASE_NAME)) as connection:
        review_storage.write(connection, stored)
        connection.commit()
    result = subject.action("approve_report")
    assert result["review"]["outcome"] == "invalidated"
    assert result["packet"] is None and subject.reserve() is None
    assert subject.stored()["spent"] == []


@pytest.mark.parametrize(
    "change",
    [
        "wall_expiry",
        "elapsed_expiry",
        "wall_rollback",
        "elapsed_rollback",
        "new_epoch",
        "missing_epoch",
    ],
)
def test_expired_or_uncertain_age_cannot_approve_or_silently_resume(subject, change):
    subject.pause()
    assert subject.record()
    subject.action("inspect_report")
    if change == "wall_expiry":
        subject.clock["now"] += 900000
    if change == "elapsed_expiry":
        subject.clock["elapsed"] += 900000
    if change == "wall_rollback":
        subject.clock["now"] -= 1
    if change == "elapsed_rollback":
        subject.clock["elapsed"] -= 1
    if change == "new_epoch":
        subject.clock["epoch"] = "b" * 32
    if change == "missing_epoch":
        subject.clock["epoch"] = None
    result = subject.action("approve_report")
    assert result["review"]["outcome"] == "expired" and result["packet"] is None
    assert subject.stored()["review"]["report"] is None
    assert subject.stored()["review"]["mode"] == "review"
    assert subject.reserve() is None and subject.stored()["spent"] == []


def test_expiry_after_paid_claim_still_blocks_the_final_write(subject):
    subject.pause()
    assert subject.record()
    subject.action("inspect_report")
    subject.action("approve_report")
    subject.clock["elapsed"] += 899999
    report = subject.reserve()
    assert report is not None
    subject.clock["elapsed"] += 1
    assert not subject.budget.guarded_write(
        report, lambda _: pytest.fail("Expired packet reached transport")
    )
    assert len(subject.stored()["spent"]) == 1


def test_stale_controls_and_policy_changes_cannot_authorize_a_different_packet(
    subject, monkeypatch
):
    subject.pause()
    assert subject.record()
    stale = subject.request()
    subject.action("inspect_report")
    with pytest.raises(policy.PolicyError, match="telemetry_review_changed"):
        inspection.execute(subject.root, "approve_report", stale)
    monkeypatch.setattr(policy, "COLLECTOR_URL", "https://changed.invalid/v3/report")
    result = subject.action("approve_report")
    assert result["review"]["outcome"] == "invalidated" and subject.reserve() is None
    assert subject.stored()["spent"] == []


def test_group_change_invalidates_even_if_selected_group_is_still_allowed(subject):
    subject.pause()
    assert subject.record()
    subject.action("inspect_report")
    subject.company.write_text(
        json.dumps({"schema_version": 1, "enabled": True, "metric_groups": ["usage"]})
    )
    assert subject.action("approve_report")["review"]["outcome"] == "invalidated"
    assert subject.reserve() is None


def test_opt_out_clears_bytes_and_preserves_manual_mode_on_reenable(subject):
    subject.pause()
    assert subject.record()
    subject.action("inspect_report")
    off = policy.configure(subject.root, {"enabled": False, "expected_revision": 0})
    stored = subject.stored()
    assert stored["review"]["mode"] == "review" and stored["review"]["report"] is None
    on = policy.configure(
        subject.root,
        {
            "enabled": True,
            "expected_revision": off["revision"],
            "expected_generation": off["store_generation"],
            "disclosure_version": policy.DISCLOSURE_VERSION,
        },
    )
    assert on["effective_enabled"] and subject.stored()["review"]["mode"] == "review"
    assert subject.record() and subject.reserve() is None


def test_discard_and_resume_never_restore_staged_input_or_contribution_allowance(subject):
    subject.pause()
    assert subject.record()
    subject.action("inspect_report")
    contributions = subject.stored()["contributions"]
    assert subject.action("discard_report")["review"]["outcome"] == "discarded"
    assert subject.stored()["pending"] == [] and subject.stored()["contributions"] == contributions
    assert subject.record()
    subject.action("review_mode", mode="automatic")
    report = subject.reserve()
    assert report is not None
    subject.budget.cancel(report)


def test_owned_work_erases_an_expired_body_without_restarting_delivery(subject):
    subject.pause()
    assert subject.record()
    subject.action("inspect_report")
    subject.clock["elapsed"] += 900000
    assert subject.record()
    assert subject.stored()["review"]["outcome"] == "expired"
    assert subject.stored()["review"]["report"] is None and subject.stored()["spent"] == []


def test_review_cannot_outlive_the_oldest_observation_window(subject):
    subject.clock["now"] = 20001 * DAY - 5
    subject.pause()
    assert subject.record()
    with closing(sqlite3.connect(subject.root / policy.DATABASE_NAME)) as connection:
        connection.execute("UPDATE pending SET window_day=19999")
        connection.commit()
    result = subject.action("inspect_report")
    assert result["review"]["expires_ms"] == 20001 * DAY
    subject.clock["now"] += 5
    subject.clock["elapsed"] += 5
    assert subject.action("approve_report")["review"]["outcome"] == "expired"


def test_migration_preserves_pending_observations_and_spent_allowance(subject):
    assert subject.record()
    report = subject.reserve()
    assert report is not None
    subject.budget.cancel(report)
    assert subject.record()
    old = subject.stored()
    with closing(sqlite3.connect(subject.root / policy.DATABASE_NAME)) as connection:
        connection.executescript("DROP TABLE report_review; PRAGMA user_version=5;")
    assert inspection.status(subject.root)["message"] == "upgrade_required"
    result = subject.pause()
    new = subject.stored()
    assert result["review"]["mode"] == "review"
    assert (
        new["pending"] == old["pending"]
        and new["spent"] == old["spent"]
        and new["contributions"] == old["contributions"]
    )


def test_arbitrary_packet_or_destination_inputs_are_rejected_before_any_control_work(subject):
    before = subject.stored()
    with pytest.raises(policy.PolicyError, match="telemetry_invalid_review"):
        inspection.execute(subject.root, "inspect_report", subject.request(packet=[1, 0, 0, 0]))
    assert subject.stored() == before and subject.clock["reads"] == 0


def _legacy_lifetime():
    return {
        "created_ms": 1000000,
        "expires_ms": 1060000,
        "checked_ms": 1000000,
        "clock": {"epoch": "ab" * 16, "elapsed_ms": 10},
        "checked_elapsed_ms": 10,
    }


def _stale_manual_approval():
    token = "c" * 32
    return {
        "version": 1,
        "mode": "review",
        "token": token,
        "outcome": "approved",
        "report": {
            "packet": [0, 0, 0, 0],
            "stamp": {"revision": 1, "store_generation": "d" * 32},
            "groups": ["usage", "reliability", "performance", "resources"],
            "binding": {
                "disclosure_version": 1,
                "wire_version": 2,
                "catalog_version": 2,
                "destination": "https://example.invalid/v1/report",
                "route_address": None,
            },
            "lifetime": _legacy_lifetime(),
        },
    }


def test_corrupted_automatic_state_is_not_recovered_and_stale_manual_approval_is_invalidated(
    subject,
):
    enabled = policy.status(subject.root)["user_enabled"]
    subject.company.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "enabled": True,
                "metric_groups": ["usage", "reliability", "performance", "resources"],
            }
        )
    )
    company = subject.company.read_bytes()
    fresh = {
        "version": 1,
        "mode": "automatic",
        "token": None,
        "outcome": "inactive",
        "report": None,
    }
    assert review.parse_review(json.dumps(fresh)) == fresh
    assert review.salvage_stale_review(json.dumps(fresh)) is None
    counterexample = json.dumps(
        {"version": 1, "mode": "automatic", "report": {"packet": [0, 0, 0, 0]}}
    )
    with pytest.raises(ValueError, match="telemetry_review_unavailable"):
        review.parse_review(counterexample)
    assert review.salvage_stale_review(counterexample) is None
    assert review.salvage_stale_review(counterexample) != review.fresh_review()
    broken = dict(_stale_manual_approval())
    del broken["token"]
    assert review.salvage_stale_review(json.dumps(broken)) is None
    with closing(sqlite3.connect(subject.root / policy.DATABASE_NAME)) as connection:
        connection.execute("UPDATE report_review SET state=? WHERE singleton=1", (counterexample,))
        connection.commit()
        with pytest.raises(ValueError, match="telemetry_review_unavailable"):
            review_storage.read(connection)
    assert subject.reserve() is None

    def rows(query):
        with closing(sqlite3.connect(subject.root / policy.DATABASE_NAME)) as connection:
            return connection.execute(query).fetchall()

    assert rows("SELECT state FROM report_review") == [(counterexample,)]
    assert rows("SELECT count(*) FROM delivery_attempts") == [(0,)]
    stale = _stale_manual_approval()
    raw = json.dumps(stale)
    salvaged = review.salvage_stale_review(raw)
    assert salvaged == {
        "version": 1,
        "mode": "review",
        "token": stale["token"],
        "outcome": "invalidated",
        "report": None,
    }
    with closing(sqlite3.connect(subject.root / policy.DATABASE_NAME)) as connection:
        connection.execute("UPDATE report_review SET state=? WHERE singleton=1", (raw,))
        connection.commit()
        assert review_storage.read(connection) == salvaged
    assert subject.reserve() is None
    assert rows("SELECT count(*) FROM delivery_attempts") == [(0,)]
    stored = subject.stored()["review"]
    assert stored["mode"] == "review" and stored["outcome"] == "invalidated"
    assert stored["report"] is None and stored["token"] == stale["token"]
    assert policy.status(subject.root)["user_enabled"] is enabled
    assert subject.company.read_bytes() == company
