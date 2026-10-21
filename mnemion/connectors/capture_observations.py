"""Encrypted source accounting committed with the local inbox, without HTTP.

The current prefix is not lifetime coverage. Missing files and generation changes
retain uncertainty; a later successful scan cannot reconstruct unseen history.
Status reads one aggregate record instead of decrypting every source checkpoint.
"""

from bisect import bisect_right
import hashlib
import json
import re

from ..capture_coverage import (
    CaptureCoverage,
    CaptureSchedule,
    IndexCounts,
    PrefixObservation,
    SelectionCounts,
    utc_now,
)
from ..capture_identity import canonical_capture_json
from .conversation_inbox import InboxError

PREFIX = "coverage:"
SUMMARY = "coverage-summary"
SCHEDULE = "coverage-schedule"
COUNTERS = (
    "tracked_scopes",
    "checking_scopes",
    "failed_scopes",
    "missing_scopes",
    "uncertain_scopes",
    "unknown_prefix_scopes",
    "observed_bytes",
    "examined_prefix_bytes",
    "unaccepted_observed_bytes",
    "unresolved_previous_bytes",
)


def contribution(value):
    if value is None:
        return {**dict.fromkeys(COUNTERS, 0), "records": SelectionCounts().model_dump()}
    return {
        "tracked_scopes": 1,
        "checking_scopes": int(value.outcome in {"checking", "deferred"}),
        "failed_scopes": int(value.outcome == "failed"),
        "missing_scopes": int(value.outcome == "missing"),
        "uncertain_scopes": int(value.uncertain),
        "unknown_prefix_scopes": int(value.records is None),
        "observed_bytes": value.observed_bytes,
        "examined_prefix_bytes": value.examined_bytes,
        "unaccepted_observed_bytes": value.observed_bytes - value.examined_bytes,
        "unresolved_previous_bytes": value.unresolved_bytes,
        "records": (value.records or SelectionCounts()).model_dump(),
    }


class Observations:
    def __init__(self, inbox):
        self.inbox, self.connection = inbox, inbox.connection

    def _read(self, name, model, default=None):
        row = self.connection.execute("SELECT value FROM metadata WHERE name=?", (name,)).fetchone()
        if row is None:
            return default
        try:
            if len(row[0]) > 32768:
                raise ValueError()
            return model.model_validate(json.loads(self.inbox._open(row[0], "observation:" + name)))
        except (ValueError, TypeError, KeyError):
            raise InboxError("capture_integrity_failed") from None

    def _save(self, name, value):
        encoded = canonical_capture_json(value.model_dump())
        self.connection.execute(
            "INSERT INTO metadata(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
            (name, self.inbox._seal(encoded, "observation:" + name)),
        )

    def _summary(self):
        mode = self.inbox.binding["capture_mode"]
        summary = self._read(SUMMARY, CaptureCoverage, CaptureCoverage(capture_mode=mode))
        if summary.capture_mode != mode:
            raise InboxError("capture_integrity_failed")
        return summary.model_dump()

    def _scope(self, scope):
        if not isinstance(scope, str) or not re.fullmatch(r"conversation:[a-f0-9]{64}", scope):
            raise InboxError("capture_checkpoint_invalid")
        return self._read(PREFIX + scope, PrefixObservation)

    def _replace(self, summary, scope, before, after):
        after = PrefixObservation.model_validate(after)
        old, new = contribution(before), contribution(after)
        for field in COUNTERS:
            summary[field] += new[field] - old[field]
        for field in summary["records"]:
            summary["records"][field] += new["records"][field] - old["records"][field]
        self._save(PREFIX + scope, after)

    def _finish(self, summary):
        self._save(SUMMARY, CaptureCoverage.model_validate(summary))

    def catalog(self, scopes, *, scheduled=False):
        if not isinstance(scopes, (list, tuple)) or len(set(scopes)) != len(scopes):
            raise InboxError("capture_checkpoint_invalid")
        with self.inbox._transaction():
            known = {
                row[0][len(PREFIX) :]
                for row in self.connection.execute(
                    "SELECT name FROM metadata WHERE name LIKE 'coverage:%'"
                )
            }
            known.update(row[0] for row in self.connection.execute("SELECT scope FROM checkpoints"))
            current = set(scopes)
            if len(known | current) > self.inbox.limits.scopes:
                raise InboxError("capture_capacity_blocked")
            work, reset = list(scopes), True
            if scheduled:
                ordered = sorted(current)
                digest = hashlib.sha256(canonical_capture_json(ordered)).hexdigest()
                schedule = self._read(SCHEDULE, CaptureSchedule)
                reset = schedule is None or schedule.catalog != digest or schedule.remaining == 0
                if reset:
                    schedule = CaptureSchedule(
                        catalog=digest,
                        remaining=len(ordered),
                        last_scope=schedule.last_scope if schedule else None,
                    )
                if schedule.remaining > len(ordered):
                    raise InboxError("capture_integrity_failed")
                offset = bisect_right(ordered, schedule.last_scope or "")
                work = (ordered[offset:] + ordered[:offset])[: schedule.remaining]
                self._save(SCHEDULE, schedule)
            summary = self._summary()
            interrupted = False
            observed = utc_now()
            summary.update(catalog="available", observed_at=observed)
            summary["tracked_from"] = summary["tracked_from"] or observed
            for scope in sorted(known | current):
                before = self._scope(scope)
                interrupted |= bool(before and before.outcome == "checking")
                after = (before or PrefixObservation()).model_dump()
                if before is None and scope in known:
                    prior = self.inbox.checkpoint(scope)
                    if prior and {"generation", "stat", "complete_end"} <= prior.keys():
                        after.update(
                            generation=prior["generation"],
                            observed_bytes=prior["stat"]["size"],
                            examined_bytes=prior["complete_end"],
                            uncertain=True,
                        )
                if scope not in current:
                    after["outcome"] = "missing"
                    after["uncertain"] = True
                elif not scheduled:
                    after["outcome"] = "checking"
                elif reset or before is None or before.outcome in {"checking", "missing"}:
                    # Deferred work is intentional. Only scan_started records
                    # an actual attempt; a crash then remains distinguishable.
                    after["outcome"] = (
                        "failed" if before and before.outcome == "failed" else "deferred"
                    )
                self._replace(summary, scope, before, after)
            if interrupted:
                summary["uncertain_intervals"] += 1
            if not current and not known:
                summary["complete_prefix_at"] = observed
            self._finish(summary)
            self.inbox._capacity()
            return work

    def scan_started(self, scope):
        """Persist the next turn before reading, including if this process dies."""
        with self.inbox._transaction():
            before = self._scope(scope)
            schedule = self._read(SCHEDULE, CaptureSchedule)
            if before is None or schedule is None or not schedule.remaining:
                raise InboxError("capture_checkpoint_invalid")
            self._save(
                SCHEDULE,
                schedule.model_copy(
                    update={"last_scope": scope, "remaining": schedule.remaining - 1}
                ),
            )
            summary = self._summary()
            self._replace(summary, scope, before, {**before.model_dump(), "outcome": "checking"})
            self._finish(summary)

    def catalog_unavailable(self):
        with self.inbox._transaction():
            summary = self._summary()
            if summary["catalog"] != "unavailable":
                summary["uncertain_intervals"] += 1
            summary.update(catalog="unavailable", observed_at=utc_now())
            self._finish(summary)

    def accepted(self, scope, checkpoint, report):
        # Called inside the same transaction as selected bytes and checkpoint.
        if not self.connection.in_transaction:
            raise RuntimeError("Prefix coverage needs the local acceptance transaction")
        before = self._scope(scope)
        after = (before or PrefixObservation()).model_dump()
        changed = bool(
            before
            and before.generation
            and (before.generation != checkpoint["generation"] or report.get("change") == "rewrite")
        )
        if changed:
            after["uncertain"] = True
            after["unresolved_bytes"] += before.observed_bytes - before.examined_bytes
        elif before and report["observed_size_bytes"] < before.observed_bytes:
            # A producer may remove an unexamined suffix between bounded
            # passes while keeping the already accepted prefix intact.
            lost = before.observed_bytes - max(report["observed_size_bytes"], before.examined_bytes)
            if lost > 0:
                after["uncertain"] = True
                after["unresolved_bytes"] += lost
        after.update(
            outcome="deferred" if report.get("scan_complete") is False else "accepted",
            generation=checkpoint["generation"],
            observed_bytes=report["observed_size_bytes"],
            examined_bytes=checkpoint["complete_end"],
            records=checkpoint["accounting"]["current"],
        )
        summary = self._summary()
        self._replace(summary, scope, before, after)
        if not (
            summary["checking_scopes"] or summary["failed_scopes"] or summary["missing_scopes"]
        ):
            summary["complete_prefix_at"] = utc_now()
        self._finish(summary)

    def failed(self, scope, report=None):
        with self.inbox._transaction():
            before = self._scope(scope)
            after = (before or PrefixObservation()).model_dump()
            after.update(outcome="failed")
            if report and type(report.get("observed_size_bytes")) is int:
                generation = report.get("generation")
                changed = bool(
                    before
                    and before.generation
                    and (generation != before.generation or report.get("change") == "rewrite")
                )
                if changed:
                    after["uncertain"] = True
                    after["unresolved_bytes"] += before.observed_bytes - before.examined_bytes
                    after.update(examined_bytes=0, records=None)
                elif before and report["observed_size_bytes"] < before.observed_bytes:
                    lost = before.observed_bytes - max(
                        report["observed_size_bytes"], before.examined_bytes
                    )
                    if lost > 0:
                        after["uncertain"] = True
                        after["unresolved_bytes"] += lost
                after.update(
                    generation=generation,
                    observed_bytes=max(report["observed_size_bytes"], after["examined_bytes"]),
                )
            summary = self._summary()
            self._replace(summary, scope, before, after)
            self._finish(summary)

    def queued(self, previous_bytes, added_bytes):
        if not previous_bytes and added_bytes:
            summary = self._summary()
            summary["queue_nonempty_since"] = utc_now()
            self._finish(summary)

    def acknowledged(self):
        summary = self._summary()
        summary["last_acknowledged_at"] = utc_now()
        self._finish(summary)

    def contacted(self):
        with self.inbox._transaction():
            summary = self._summary()
            summary["last_contact_at"] = utc_now()
            self._finish(summary)

    def index_cursor(self):
        active = self._summary()["index"]["active"]
        return active["next_cursor"] if active else None

    def index_unavailable(self, *, unsupported=False):
        with self.inbox._transaction():
            summary = self._summary()
            summary["index"].update(
                status="unsupported" if unsupported else "unavailable", last_attempt_at=utc_now()
            )
            self._finish(summary)

    def indexed(self, page):
        """Commit one verified page, retaining the previous completed sweep.

        Server source counts cover all devices authorized for this source, not
        just this inbox. Their observation interval is not an atomic snapshot.
        """
        from ..service.capture_models import CaptureIndexPage

        page = CaptureIndexPage.model_validate(page)
        if any(
            getattr(page, field) != self.inbox.binding[field] for field in ("source_id", "grant_id")
        ):
            raise InboxError("capture_binding_mismatch")
        with self.inbox._transaction():
            summary = self._summary()
            progress = summary["index"]
            active = progress["active"]
            expected = active["next_cursor"] if active else None
            if page.after != expected:
                raise InboxError("capture_checkpoint_invalid")
            progress.update(status="available", last_attempt_at=utc_now())
            if active and active["generation_id"] != page.generation_id:
                # Restart from the beginning; a page following an older
                # generation's cursor cannot establish the new prefix.
                progress["active"] = None
                self._finish(summary)
                return False
            active = active or {
                "generation_id": page.generation_id,
                "started_at": page.observed_at,
                "observed_at": page.observed_at,
                "inference_paused": page.inference_paused,
                "pages": 0,
                "counts": IndexCounts().model_dump(),
                "next_cursor": None,
            }
            active.update(
                observed_at=page.observed_at,
                inference_paused=page.inference_paused,
                pages=active["pages"] + 1,
                next_cursor=page.next_cursor,
            )
            for key, value in page.counts.model_dump().items():
                active["counts"][key] += value
            if page.next_cursor is None:
                progress.update(active=None, completed=active)
            else:
                progress["active"] = active
            self._finish(summary)
            return page.next_cursor is None

    def status(self, pending_bytes):
        summary = self._summary()
        if not pending_bytes:
            summary["queue_nonempty_since"] = None
        return CaptureCoverage.model_validate(summary).model_dump()
