"""Local capture using the same selected renderer as legacy conversation mirrors.

Producer metadata and selected ciphertext share the inbox transaction. This
module performs no service requests; even control/health polling happens later.
"""

import hashlib
import json
import time

from ..capture_identity import canonical_capture_json, capture_event_id
from .conversation_inbox import InboxError
from .live_conversations import ConversationSnapshot
from .providers import ProviderError

WINDOW_BYTES = 32 * 1024**2
WINDOW_SEGMENTS = 64
PASS_BYTES = 64 * 1024**2
PASS_SEGMENTS = 256
PASS_SCOPES = 256
PASS_SECONDS = 30


class ScanBudget:
    """Cooperative whole-connection allowance, including verified prefix reads."""

    def __init__(self, max_seconds):
        self.deadline = time.monotonic() + min(PASS_SECONDS, max_seconds)
        self.bytes = self.segments = self.scopes = 0

    @property
    def exhausted(self):
        return (
            self.scopes >= PASS_SCOPES
            or self.segments >= PASS_SEGMENTS
            or self.bytes >= PASS_BYTES
            or time.monotonic() >= self.deadline
        )

    def charge(self, report):
        self.scopes += 1
        if report is not None:
            self.bytes += report.get("bytes_read", 0)
            self.segments += report.get("segments_rendered", 0)


class LocalCaptureState:
    observes_selection = True
    resumable_capture = True

    def __init__(self, inbox, scope, budget=None):
        self.inbox, self.connection, self.scope = inbox, inbox.connection, scope
        # A recovered device must verify its copied prefix before trusting the
        # old file's inode/stat cache. This is cache identity, never provenance.
        self.capture_grant = inbox.binding["grant_id"]
        self.budget = budget
        self.event_count = self.connection.execute(
            "SELECT COUNT(*) FROM producer_events"
        ).fetchone()[0]
        self.segment_count = self.connection.execute(
            "SELECT COUNT(*) FROM producer_segments"
        ).fetchone()[0]
        self.retained_before = 0
        _, pending = inbox._usage()
        # This is a work allowance, not a promise that a fragment fits. The
        # inbox still checks exact selected bytes and commits them atomically.
        self.window_bytes = min(
            WINDOW_BYTES, max(1024, (inbox.limits.pending_bytes - pending) // 8)
        )
        if budget is not None:
            self.window_bytes = min(self.window_bytes, max(1024, PASS_BYTES - budget.bytes))

    def window_reached(self, *, segments, new_bytes, read_bytes, remaining_seconds, scan_seconds):
        return (
            segments >= WINDOW_SEGMENTS
            or new_bytes >= self.window_bytes
            or remaining_seconds <= scan_seconds / 4
            or (
                self.budget is not None
                and (
                    self.budget.segments + segments >= PASS_SEGMENTS
                    or self.budget.bytes + read_bytes >= PASS_BYTES
                    or time.monotonic() >= self.budget.deadline
                )
            )
        )

    def retain_prefix(self, before, scan):
        # Retained sources never need to resend old reference lists. Preserve
        # this prefix by position instead of decrypting/updating its whole
        # history on every scan. The mirror keeps its original reference path.
        self.retained_before = before
        return self.connection.execute(
            "SELECT COUNT(*) FROM producer_segments WHERE scope=? AND start<?", (self.scope, before)
        ).fetchone()[0]

    def read(self):
        return self.inbox.checkpoint(self.scope)

    def rewind_events(self, start):
        result = self.connection.execute(
            "DELETE FROM producer_events WHERE scope=? AND position>=?", (self.scope, start)
        )
        self.event_count -= result.rowcount

    def event(self, session, event, digest, position):
        identity = hashlib.sha256(canonical_capture_json([session, event])).hexdigest()
        old = self.connection.execute(
            "SELECT digest FROM producer_events WHERE scope=? AND identity=?",
            (self.scope, identity),
        ).fetchone()
        if old:
            if old[0] != digest:
                raise ProviderError("conversation_event_conflict")
            return False
        if self.event_count >= self.inbox.limits.events:
            raise InboxError("capture_capacity_blocked")
        self.connection.execute(
            "INSERT INTO producer_events(scope,identity,digest,position) VALUES(?,?,?,?)",
            (self.scope, identity, digest, position),
        )
        self.event_count += 1
        return True

    def references(self, before, scan):
        for start, payload in self.connection.execute(
            "SELECT start,payload FROM producer_segments WHERE scope=? AND start<? ORDER BY start",
            (self.scope, before),
        ):
            self.connection.execute(
                "UPDATE producer_segments SET seen=? WHERE scope=? AND start=?",
                (scan, self.scope, start),
            )
            yield json.loads(self.inbox._open(payload, f"segment:{self.scope}:{start}"))

    def segment(self, start, items, scan, *, reuse=False):
        previous = self.connection.execute(
            "SELECT payload FROM producer_segments WHERE scope=? AND start=?", (self.scope, start)
        ).fetchone()
        known = (
            {
                (value["external_id"], value["revision"])
                for value in json.loads(
                    self.inbox._open(previous[0], f"segment:{self.scope}:{start}")
                )
            }
            if previous and reuse
            else set()
        )
        if not previous:
            if self.segment_count >= self.inbox.limits.events:
                raise InboxError("capture_capacity_blocked")
            self.segment_count += 1
        refs = [{"external_id": item.external_id, "revision": item.revision} for item in items]
        self.connection.execute(
            "INSERT INTO producer_segments(scope,start,payload,seen) VALUES(?,?,?,?) ON CONFLICT(scope,start) DO UPDATE SET payload=excluded.payload,seen=excluded.seen",
            (
                self.scope,
                start,
                self.inbox._seal(canonical_capture_json(refs), f"segment:{self.scope}:{start}"),
                scan,
            ),
        )
        return known

    def finish(self, scan):
        self.connection.execute(
            "DELETE FROM producer_segments WHERE scope=? AND seen<>? AND start>=?",
            (self.scope, scan, self.retained_before),
        )


def capture_scope(inbox, provider, scope, *, budget=None):
    """Stream a verified producer prefix into one atomic local acceptance."""
    snapshot = None
    try:
        state = LocalCaptureState(inbox, scope, budget)
        previous = state.read()
        snapshot = ConversationSnapshot(
            provider, scope, state, previous["checkpoint"] if previous else None
        )

        def selected():
            for item in snapshot.items():
                if item is None or item.action == "retain":
                    continue
                value = item.model_dump(mode="json")
                yield {
                    "event_id": capture_event_id(inbox.binding["source_id"], scope, value),
                    "producer_scope": scope,
                    "item": value,
                }

        def verified():
            if snapshot.ready is None:
                return False
            state.finish(snapshot.scan_id)
            inbox.observations.accepted(scope, snapshot.ready, snapshot.report)
            return True

        result = inbox.accept(scope, selected(), lambda: snapshot.ready, verify=verified)
    except (ProviderError, OSError, ValueError, InboxError):
        inbox.observations.failed(scope, snapshot.report if snapshot is not None else None)
        raise
    finally:
        if budget is not None:
            budget.charge(snapshot.report if snapshot is not None else None)
    return {**result, "capture": snapshot.report}


def capture_available(inbox, provider):
    """Capture what is available without treating disappearance as forgetting."""
    reports, failures = [], []
    budget = ScanBudget(provider.config.max_scan_seconds)
    try:
        scopes = provider.scopes()
        work = inbox.observations.catalog(scopes, scheduled=True)
    except (ProviderError, OSError, ValueError, InboxError) as error:
        inbox.observations.catalog_unavailable()
        return {
            "completed": False,
            "scopes": [],
            "errors": [
                error.code if isinstance(error, InboxError) else "capture_source_unavailable"
            ],
            **inbox.status(),
        }
    for scope in work:
        # Always allow one attempt after a slow catalog. The existing per-file
        # deadline still applies, and the next pass starts after this scope.
        if budget.scopes and budget.exhausted:
            break
        started = False
        try:
            inbox.observations.scan_started(scope)
            started = True
            reports.append(
                {"external_id": scope, **capture_scope(inbox, provider, scope, budget=budget)}
            )
        except (ProviderError, OSError, ValueError, InboxError) as error:
            code = getattr(error, "code", "capture_source_unavailable")
            failures.append(
                code
                if code
                in {
                    "capture_capacity_blocked",
                    "capture_fence_capacity",
                    "capture_disk_full",
                    "capture_prefix_changed",
                    "capture_checkpoint_invalid",
                    "capture_integrity_failed",
                    "capture_event_invalid",
                    "capture_event_conflict",
                    "source_changed_during_read",
                    "conversation_scan_deadline",
                    "conversation_record_limit",
                    "conversation_file_limit",
                    "conversation_event_conflict",
                    "conversation_field_selection_limit",
                }
                else "capture_source_unavailable"
            )
            if not started or code in {
                "capture_capacity_blocked",
                "capture_fence_capacity",
                "capture_disk_full",
            }:
                break
    status = inbox.status()
    if not failures and status["coverage"]["failed_scopes"]:
        # A source that failed earlier in this sweep has not been retried yet.
        failures.append("capture_source_unavailable")
    deferred = status["coverage"]["checking_scopes"] > 0
    return {
        "completed": not failures and not deferred,
        "deferred": deferred,
        "scopes": reports,
        "errors": failures,
        **status,
    }
