"""Local capture using the same selected renderer as legacy conversation mirrors.

Producer metadata and selected ciphertext share the inbox transaction. This
module performs no service requests; even control/health polling happens later.
"""

import hashlib
import json

from ..capture_identity import canonical_capture_json, capture_event_id
from .conversation_inbox import InboxError
from .live_conversations import ConversationSnapshot
from .providers import ProviderError

WINDOW_BYTES = 32 * 1024**2
WINDOW_SEGMENTS = 64


class LocalCaptureState:
    observes_selection = True
    resumable_capture = True

    def __init__(self, inbox, scope):
        self.inbox, self.connection, self.scope = inbox, inbox.connection, scope
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

    def window_reached(self, *, segments, new_bytes, remaining_seconds, scan_seconds):
        return (
            segments >= WINDOW_SEGMENTS
            or new_bytes >= self.window_bytes
            or remaining_seconds <= scan_seconds / 4
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


def capture_scope(inbox, provider, scope):
    """Stream a verified producer prefix into one atomic local acceptance."""
    snapshot = None
    try:
        state = LocalCaptureState(inbox, scope)
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
    return {**result, "capture": snapshot.report}


def capture_available(inbox, provider):
    """Capture what is available without treating disappearance as forgetting."""
    reports, failures = [], []
    try:
        scopes = provider.scopes()
        inbox.observations.catalog(scopes)
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
    for scope in scopes:
        try:
            reports.append({"external_id": scope, **capture_scope(inbox, provider, scope)})
        except (ProviderError, OSError, ValueError, InboxError) as error:
            code = getattr(error, "code", "capture_source_unavailable")
            failures.append(
                code
                if code
                in {
                    "capture_capacity_blocked",
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
                }
                else "capture_source_unavailable"
            )
            if code in {"capture_capacity_blocked", "capture_disk_full"}:
                break
    deferred = any(item["capture"].get("scan_complete") is False for item in reports)
    return {
        "completed": not failures and not deferred,
        "deferred": deferred,
        "scopes": reports,
        "errors": failures,
        **inbox.status(),
    }
