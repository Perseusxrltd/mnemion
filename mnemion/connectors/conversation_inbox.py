"""Encrypted, bounded local handoff queue for explicitly authorized capture.

This module never contacts a service or reads producer files. Its caller renders
only consented items and verifies the captured prefix before local acceptance.
Opening an existing inbox cannot initialize a lost database or change its owner.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import sqlite3
from typing import Callable, Iterable
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .. import local_state
from ..capture_history import CaptureHistory
from ..capture_identity import canonical_capture_json, capture_event_id, capture_lineage_id
from ..private_output import private_output
from ..service.capture_custody import selected_item
from ..service.connector_models import ConnectorItemInput
from ..service.errors import ServiceError
from .capture_errors import InboxError as InboxError

FORMAT = "mnemion-selected-inbox-v1"
PAGE_BYTES = 1_500_000
SCHEMA = """
CREATE TABLE metadata (name TEXT PRIMARY KEY, value BLOB NOT NULL);
CREATE TABLE events (
  sequence INTEGER PRIMARY KEY, event_id TEXT NOT NULL UNIQUE,
  scope TEXT NOT NULL, lineage TEXT NOT NULL, digest TEXT NOT NULL,
  size INTEGER NOT NULL, payload BLOB, state TEXT NOT NULL,
  CHECK(state IN ('pending','stored','forgotten'))
);
CREATE INDEX pending_events ON events(state, sequence);
CREATE INDEX event_lineage ON events(scope, lineage);
CREATE TABLE checkpoints (scope TEXT PRIMARY KEY, payload BLOB NOT NULL);
CREATE TABLE pages (
  page_id TEXT PRIMARY KEY, digest TEXT NOT NULL, payload BLOB,
  receipt BLOB, state TEXT NOT NULL CHECK(state IN ('pending','settled','fenced'))
);
CREATE TABLE page_events (
  page_id TEXT NOT NULL REFERENCES pages(page_id),
  event_id TEXT NOT NULL REFERENCES events(event_id),
  PRIMARY KEY(page_id,event_id)
);
CREATE TABLE denials (lineage TEXT PRIMARY KEY);
CREATE TABLE producer_segments (
  scope TEXT NOT NULL, start INTEGER NOT NULL, payload BLOB NOT NULL,
  seen TEXT NOT NULL, PRIMARY KEY(scope,start)
);
CREATE TABLE producer_events (
  scope TEXT NOT NULL, identity TEXT NOT NULL, digest TEXT NOT NULL,
  position INTEGER NOT NULL, PRIMARY KEY(scope,identity)
);
CREATE INDEX producer_event_position ON producer_events(scope,position);
"""


@dataclass(frozen=True)
class Limits:
    pending_bytes: int = 256 * 1024**2
    database_bytes: int = 512 * 1024**2
    minimum_free_bytes: int = 512 * 1024**2
    events: int = 100_000
    scopes: int = 10_000

    def __post_init__(self):
        if any(type(value) is not int or value < 1 for value in vars(self).values()):
            raise ValueError("Inbox limits must be positive integers")
        if self.database_bytes < 65536:
            raise ValueError("Inbox database limit is too small")


def binding_value(value: dict) -> dict:
    fields = {"tenant_id", "connector_id", "source_id", "grant_id", "namespace", "capture_mode"}
    if not isinstance(value, dict) or not fields <= set(value) <= fields | {"capture_policy"}:
        raise InboxError("capture_binding_invalid")
    try:
        if any(
            str(UUID(value[key])) != value[key] for key in fields - {"namespace", "capture_mode"}
        ):
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise InboxError("capture_binding_invalid") from None
    if (
        value["capture_mode"] not in {"messages", "complete"}
        or not isinstance(value["namespace"], str)
        or not 1 <= len(value["namespace"]) <= 512
        or any(ord(char) < 32 for char in value["namespace"])
    ):
        raise InboxError("capture_binding_invalid")
    if "capture_policy" in value:
        from ..capture_policy import CapturePolicy

        try:
            policy = CapturePolicy.model_validate(value["capture_policy"])
            if (
                policy.capture_mode != value["capture_mode"]
                or not policy.keeps_accepted
                or policy.model_dump(mode="json") != value["capture_policy"]
            ):
                raise ValueError()
        except ValueError:
            raise InboxError("capture_binding_invalid") from None
    return dict(value)


class Inbox:
    def __init__(self, connection, root, binding, key, limits):
        from .capture_observations import Observations

        self.connection, self.root, self.binding, self.limits = connection, root, binding, limits
        self.cipher = AESGCM(key)
        self.aad = canonical_capture_json({"format": FORMAT, "binding": binding})
        self.observations = Observations(self)

    def _seal(self, value: bytes, identity: str) -> bytes:
        nonce = os.urandom(12)
        return nonce + self.cipher.encrypt(nonce, value, self.aad + b"\0" + identity.encode())

    def _open(self, value: bytes, identity: str) -> bytes:
        try:
            return self.cipher.decrypt(value[:12], value[12:], self.aad + b"\0" + identity.encode())
        except (InvalidTag, ValueError, TypeError):
            raise InboxError("capture_integrity_failed") from None

    @contextmanager
    def _transaction(self):
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.connection.commit()
        finally:
            self.connection.rollback()

    def _usage(self):
        return self.connection.execute(
            "SELECT COUNT(*),COALESCE(SUM(CASE WHEN state='pending' THEN size ELSE 0 END),0) FROM events"
        ).fetchone()

    def _database_bytes(self):
        return (
            self.connection.execute("PRAGMA page_size").fetchone()[0]
            * self.connection.execute("PRAGMA page_count").fetchone()[0]
        )

    def _fence_usage(self):
        return (
            self.connection.execute("SELECT COUNT(*) FROM denials").fetchone()[0],
            self.fence_history_blocked(),
        )

    def _capacity(self, added_bytes=0, added_events=0, *, usage=None, fences=None):
        count, size = self._usage() if usage is None else usage
        denials, blocked = self._fence_usage() if fences is None else fences
        if blocked:
            raise InboxError("capture_fence_capacity")
        if (
            count + added_events > self.limits.events
            or denials > self.limits.events
            or size + added_bytes > self.limits.pending_bytes
            or self._database_bytes() > self.limits.database_bytes
        ):
            raise InboxError("capture_capacity_blocked")
        if shutil.disk_usage(self.root).free < self.limits.minimum_free_bytes + added_bytes * 2:
            raise InboxError("capture_disk_full")

    def _event(self, event: dict) -> tuple[bytes, str]:
        if (
            not isinstance(event, dict)
            or set(event) != {"event_id", "producer_scope", "item"}
            or not isinstance(event["producer_scope"], str)
            or not re.fullmatch(r"conversation:[a-f0-9]{64}", event["producer_scope"])
        ):
            raise InboxError("capture_event_invalid")
        try:
            item = ConnectorItemInput.model_validate(event["item"])
            if item.action != "upsert":
                raise ValueError()
            normalized = selected_item(
                item,
                self.binding["capture_mode"],
                event["producer_scope"],
                self.binding["namespace"],
                self.binding.get("capture_policy"),
            )
            if canonical_capture_json(normalized) != canonical_capture_json(event["item"]):
                raise ValueError()
            expected = capture_event_id(
                self.binding["source_id"], event["producer_scope"], normalized
            )
            if event["event_id"] != expected:
                raise ValueError()
            raw = canonical_capture_json(event)
            if len(raw) > PAGE_BYTES - 128:
                raise ValueError()
            return raw, capture_lineage_id(event["producer_scope"], normalized)
        except (ValueError, TypeError, KeyError, AttributeError, ServiceError):
            raise InboxError("capture_event_invalid") from None

    def accept(
        self,
        scope: str,
        events: Iterable[dict],
        checkpoint: dict | Callable[[], dict],
        *,
        verify: Callable[[], bool],
    ) -> dict:
        """Commit selected ciphertext and verified prefix together, before HTTP.

        Any parse, quota, verification or commit error leaves the previous local
        acceptance unchanged. Existing generations/events are never swept away.
        """
        if not isinstance(scope, str) or not re.fullmatch(r"conversation:[a-f0-9]{64}", scope):
            raise InboxError("capture_checkpoint_invalid")
        accepted = 0
        with self._transaction():
            usage = self._usage()
            fences = self._fence_usage()
            self._capacity(usage=usage, fences=fences)
            added_bytes = added_events = 0
            for event in events:
                raw, lineage = self._event(event)
                if event["producer_scope"] != scope:
                    raise InboxError("capture_event_invalid")
                event_id = event["event_id"]
                digest = hashlib.sha256(raw).hexdigest()
                existing = self.connection.execute(
                    "SELECT digest FROM events WHERE event_id=?", (event_id,)
                ).fetchone()
                if existing:
                    if existing[0] != digest:
                        raise InboxError("capture_event_conflict")
                    continue
                denied = self.connection.execute(
                    "SELECT 1 FROM denials WHERE lineage=?", (lineage,)
                ).fetchone()
                added_bytes += 0 if denied else len(raw)
                added_events += 1
                self._capacity(added_bytes, added_events, usage=usage, fences=fences)
                self.connection.execute(
                    "INSERT INTO events(event_id,scope,lineage,digest,size,payload,state) VALUES(?,?,?,?,?,?,?)",
                    (
                        event_id,
                        scope,
                        lineage,
                        digest,
                        len(raw),
                        None if denied else self._seal(raw, "event:" + event_id),
                        "forgotten" if denied else "pending",
                    ),
                )
                accepted += not bool(denied)
            if not self.connection.execute(
                "SELECT 1 FROM checkpoints WHERE scope=?", (scope,)
            ).fetchone():
                if (
                    self.connection.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
                    >= self.limits.scopes
                ):
                    raise InboxError("capture_capacity_blocked")
            if verify() is not True:
                raise InboxError("capture_prefix_changed")
            encoded_checkpoint = canonical_capture_json(
                checkpoint() if callable(checkpoint) else checkpoint
            )
            if len(encoded_checkpoint) > 32768:
                raise InboxError("capture_checkpoint_invalid")
            self._capacity(added_bytes, added_events, usage=usage, fences=fences)
            self.connection.execute(
                "INSERT INTO checkpoints(scope,payload) VALUES(?,?) ON CONFLICT(scope) DO UPDATE SET payload=excluded.payload",
                (scope, self._seal(encoded_checkpoint, "checkpoint:" + scope)),
            )
            self.observations.queued(usage[1], added_bytes)
            self._capacity(added_bytes, added_events, usage=usage, fences=fences)
        return {"locally_accepted": accepted, **self.status()}

    def checkpoint(self, scope: str) -> dict | None:
        if not isinstance(scope, str) or not re.fullmatch(r"conversation:[a-f0-9]{64}", scope):
            raise InboxError("capture_checkpoint_invalid")
        row = self.connection.execute(
            "SELECT payload FROM checkpoints WHERE scope=?", (scope,)
        ).fetchone()
        return json.loads(self._open(row[0], "checkpoint:" + scope)) if row else None

    def status(self) -> dict:
        counts = {
            state: (count, size)
            for state, count, size in self.connection.execute(
                "SELECT state,COUNT(*),COALESCE(SUM(size),0) FROM events GROUP BY state"
            )
        }
        pending, size = counts.get("pending", (0, 0))
        database_bytes = self._database_bytes()
        history = {
            "events": sum(value[0] for value in counts.values()),
            **{
                name: self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for name, table in (
                    ("producer_events", "producer_events"),
                    ("fragments", "producer_segments"),
                    ("delivery_pages", "pages"),
                    ("denials", "denials"),
                )
            },
            "scopes": self.connection.execute(
                "SELECT COUNT(*) FROM (SELECT scope FROM checkpoints UNION "
                "SELECT substr(name,10) FROM metadata WHERE name LIKE 'coverage:%')"
            ).fetchone()[0],
            "event_limit": self.limits.events,
            "scope_limit": self.limits.scopes,
            "database_bytes": database_bytes,
            "database_limit_bytes": self.limits.database_bytes,
            "fence_history_blocked": self.fence_history_blocked(),
        }
        history["over_limit"] = (
            max(history[name] for name in ("events", "producer_events", "fragments", "denials"))
            > self.limits.events
            or history["scopes"] > self.limits.scopes
            or database_bytes > self.limits.database_bytes
        )
        return {
            "format": FORMAT,
            "pending_events": pending,
            "pending_bytes": size,
            "database_bytes": database_bytes,
            "over_limit": size > self.limits.pending_bytes or history["over_limit"],
            "stored_events": counts.get("stored", (0, 0))[0],
            "forgotten_events": counts.get("forgotten", (0, 0))[0],
            "unknown_pages": self.connection.execute(
                "SELECT COUNT(*) FROM pages WHERE state='pending'"
            ).fetchone()[0],
            "coverage": self.observations.status(size),
            "history": CaptureHistory.model_validate(history).model_dump(mode="json"),
        }

    def page(self) -> dict | None:
        """Return one durably pinned page. Existing pages need reconciliation.

        No transaction remains open when this returns. A lost response preserves
        its exact page ID/body; callers reconcile through authenticated receipt
        lookup and may only replay the same idempotent page.
        """
        with self._transaction():
            old = self.connection.execute(
                "SELECT page_id,payload FROM pages WHERE state='pending'"
            ).fetchone()
            if old:
                return {"reconcile": True, "page": json.loads(self._open(old[1], "page:" + old[0]))}
            page = {"page_id": str(uuid4()), "events": []}
            for event_id, encrypted in self.connection.execute(
                "SELECT event_id,payload FROM events WHERE state='pending' ORDER BY sequence LIMIT 50"
            ):
                event = json.loads(self._open(encrypted, "event:" + event_id))
                candidate = {**page, "events": [*page["events"], event]}
                if len(canonical_capture_json(candidate)) > PAGE_BYTES:
                    break
                page = candidate
            if not page["events"]:
                return None
            raw = canonical_capture_json(page)
            # Delivery must remain possible after a reduced admission limit.
            # Reserve only the bounded page/journal overhead, not a new capture
            # allowance or the minimum free disk required for new evidence.
            if shutil.disk_usage(self.root).free < len(raw) * 3 + 65536:
                raise InboxError("capture_disk_full")
            self.connection.execute(
                "INSERT INTO pages(page_id,digest,payload,state) VALUES(?,?,?,'pending')",
                (
                    page["page_id"],
                    hashlib.sha256(raw).hexdigest(),
                    self._seal(raw, "page:" + page["page_id"]),
                ),
            )
            self.connection.executemany(
                "INSERT INTO page_events(page_id,event_id) VALUES(?,?)",
                [(page["page_id"], event["event_id"]) for event in page["events"]],
            )
        return {"reconcile": False, "page": page}

    def acknowledge(self, receipt: dict) -> dict:
        """Apply an authenticated matching service receipt, never a transport OK."""
        try:
            if (
                receipt.get("durable") is not True
                or receipt["grant_id"] != self.binding["grant_id"]
                or receipt["source_id"] != self.binding["source_id"]
                or str(UUID(receipt["page_id"])) != receipt["page_id"]
            ):
                raise ValueError()
            outcomes = receipt["items"]
            if not isinstance(outcomes, list) or not 1 <= len(outcomes) <= 50:
                raise ValueError()
            ids = [item["event_id"] for item in outcomes]
            if len(set(ids)) != len(ids):
                raise ValueError()
            for item in outcomes:
                if item["outcome"] not in {"stored", "forgotten"}:
                    raise ValueError()
                if item["outcome"] == "stored":
                    UUID(item["memory_id"])
                    UUID(item["operation_id"])
            encoded = canonical_capture_json(receipt)
            if len(encoded) > 32768:
                raise ValueError()
        except (ValueError, TypeError, KeyError, AttributeError):
            raise InboxError("capture_receipt_invalid") from None
        with self._transaction():
            row = self.connection.execute(
                "SELECT state,receipt FROM pages WHERE page_id=?", (receipt["page_id"],)
            ).fetchone()
            expected = {
                value[0]
                for value in self.connection.execute(
                    "SELECT event_id FROM page_events WHERE page_id=?", (receipt["page_id"],)
                )
            }
            if row is None or expected != set(ids):
                raise InboxError("capture_receipt_invalid")
            if row[0] == "fenced":
                raise InboxError("capture_receipt_fenced")
            original = (
                json.loads(self._open(row[1], "receipt:" + receipt["page_id"])) if row[1] else None
            )
            previous = {item["event_id"]: item for item in original["items"]} if original else {}
            # A receipt lookup may overlay a current forget fence. It may not
            # change a stored memory/operation identity or undo forgetting.
            for item in outcomes:
                old = previous.get(item["event_id"])
                if old and (
                    item["lineage_id"] != old["lineage_id"]
                    or (
                        item["outcome"] == "stored"
                        and (
                            old["outcome"] != "stored"
                            or item["memory_id"] != old["memory_id"]
                            or item["operation_id"] != old["operation_id"]
                        )
                    )
                ):
                    raise InboxError("capture_receipt_conflict")
                state = self.connection.execute(
                    "SELECT state FROM events WHERE event_id=?", (item["event_id"],)
                ).fetchone()[0]
                if state == "forgotten" and item["outcome"] != "forgotten":
                    raise InboxError("capture_receipt_stale")
            for item in outcomes:
                event = self.connection.execute(
                    "SELECT lineage FROM events WHERE event_id=?", (item["event_id"],)
                ).fetchone()
                if item.get("lineage_id") != event[0]:
                    raise InboxError("capture_receipt_invalid")
                if item["outcome"] == "forgotten":
                    self._deny(event[0])
                else:
                    self.connection.execute(
                        "UPDATE events SET state='stored',payload=NULL WHERE event_id=? AND state='pending'",
                        (item["event_id"],),
                    )
            self.connection.execute(
                "UPDATE pages SET state='settled',payload=NULL,receipt=coalesce(receipt,?) WHERE page_id=?",
                (self._seal(encoded, "receipt:" + receipt["page_id"]), receipt["page_id"]),
            )
            self.observations.acknowledged()
        return self.status()

    def _deny(self, lineage: str) -> bool:
        if (
            not self.connection.execute(
                "SELECT 1 FROM denials WHERE lineage=?", (lineage,)
            ).fetchone()
            and self.connection.execute("SELECT COUNT(*) FROM denials").fetchone()[0]
            >= self.limits.events
            and not self.connection.execute(
                "SELECT 1 FROM events WHERE lineage=? LIMIT 1", (lineage,)
            ).fetchone()
        ):
            # A foreign fence needs new history capacity. Held evidence must
            # still be purged, even when limits were lowered after acceptance.
            return False
        self.connection.execute("INSERT OR IGNORE INTO denials(lineage) VALUES(?)", (lineage,))
        self.connection.execute(
            "UPDATE events SET state='forgotten',payload=NULL WHERE lineage=?", (lineage,)
        )
        # The original page may contain forgotten ciphertext. It cannot be
        # replayed after a current authenticated forget fence has been observed.
        self.connection.execute(
            "UPDATE pages SET state='fenced',payload=NULL WHERE state='pending' AND page_id IN ("
            "SELECT p.page_id FROM page_events p JOIN events e USING(event_id) WHERE e.lineage=?)",
            (lineage,),
        )
        return True

    def fence_history_blocked(self) -> bool:
        row = self.connection.execute(
            "SELECT value FROM metadata WHERE name='fence_blocked'"
        ).fetchone()
        if row is None:
            return False
        try:
            value = json.loads(self._open(row[0], "fence_blocked"))
            if type(value) is not bool:
                raise ValueError()
            return value
        except (ValueError, TypeError, RecursionError):
            raise InboxError("capture_integrity_failed") from None

    def _block_fences(self, blocked: bool):
        self.connection.execute(
            "INSERT INTO metadata(name,value) VALUES('fence_blocked',?) "
            "ON CONFLICT(name) DO UPDATE SET value=excluded.value",
            (self._seal(canonical_capture_json(blocked), "fence_blocked"),),
        )

    def forget(self, lineage: str) -> dict:
        """Record a CURRENT authenticated service lineage fence, not an ACL grant."""
        if not isinstance(lineage, str) or not re.fullmatch(r"[a-f0-9]{64}", lineage):
            raise InboxError("capture_fence_invalid")
        with self._transaction():
            retained = self._deny(lineage)
            if not retained:
                self._block_fences(True)
                # A directly supplied fence may sort before the sweep cursor.
                # Revisit the whole service fence list before lifting the pause.
                self.connection.execute("DELETE FROM metadata WHERE name='fence_scan'")
        if not retained:
            raise InboxError("capture_fence_capacity")
        return self.status()

    def fence_cursor(self) -> str | None:
        row = self.connection.execute(
            "SELECT value FROM metadata WHERE name='fence_scan'"
        ).fetchone()
        return json.loads(self._open(row[0], "fence_scan")) if row else None

    def apply_fences(self, value: dict) -> bool:
        """Advance one bounded sweep, resetting at its end for later new fences."""
        self.fence_history_blocked()
        try:
            entries, cursor = value["items"], value["next_cursor"]
            if not isinstance(entries, list) or len(entries) > 100:
                raise ValueError()
            identifiers = [item["lineage_id"] for item in entries]
            if any(
                not isinstance(item, str) or not re.fullmatch(r"[a-f0-9]{64}", item)
                for item in identifiers
            ):
                raise ValueError()
            if identifiers != sorted(set(identifiers)) or (
                cursor is not None and (not identifiers or cursor != identifiers[-1])
            ):
                raise ValueError()
            previous = self.fence_cursor()
            if previous and identifiers and identifiers[0] <= previous:
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise InboxError("capture_fence_invalid") from None
        with self._transaction():
            retained = True
            for lineage in identifiers:
                if not self._deny(lineage):
                    retained = False
            if not retained:
                # Keep the cursor at the unretained page. Persist the pause so
                # a restart/offline scan cannot reintroduce omitted deletions.
                # Known-lineage purges above still commit in this transaction.
                self._block_fences(True)
                return False
            self.connection.execute(
                "INSERT INTO metadata(name,value) VALUES('fence_scan',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
                (self._seal(canonical_capture_json(cursor), "fence_scan"),),
            )
            if cursor is None:
                self._block_fences(False)
        return True


@contextmanager
def open_inbox(directory: Path, binding: dict, key: bytes, *, create=False, limits=Limits()):
    binding = binding_value(binding)
    if type(key) is not bytes or len(key) != 32:
        raise InboxError("capture_key_unavailable")
    root = local_state.directory(directory)
    try:
        with local_state.lock(root):
            path = root / "inbox.sqlite3"
            exists = path.exists() or path.is_symlink()
            if create == exists:
                raise InboxError("capture_already_exists" if create else "capture_inbox_missing")
            if not exists:
                with private_output(path):
                    pass
                local_state._sync_directory(root)
            for candidate in (
                path,
                root / "inbox.sqlite3-journal",
                root / "inbox.sqlite3-wal",
                root / "inbox.sqlite3-shm",
            ):
                if candidate.exists() or candidate.is_symlink():
                    local_state._regular(candidate)
                    if os.name == "nt":
                        from ..private_input import _windows_open

                        try:
                            descriptor = _windows_open(candidate)
                            os.close(descriptor)
                        except OSError:
                            raise InboxError("capture_storage_not_private") from None
            connection = sqlite3.connect(path, isolation_level=None)
            try:
                connection.execute("PRAGMA trusted_schema=OFF")
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA cache_size=-2048")
                connection.execute("PRAGMA temp_store=MEMORY")
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute("PRAGMA secure_delete=ON")
                if create:
                    # Free pages can be returned in bounded later scans without
                    # rewriting the full inbox or removing retained identities.
                    connection.execute("PRAGMA auto_vacuum=INCREMENTAL")
                page_size = connection.execute("PRAGMA page_size").fetchone()[0]
                page_count = connection.execute("PRAGMA page_count").fetchone()[0]
                # A reduced cap blocks admission, never receipt reconciliation
                # or forgetting. One bounded delivery page needs reserve even
                # when the existing database already exceeds the new limit.
                ceiling = max(
                    limits.database_bytes // page_size,
                    page_count + (3 * PAGE_BYTES + page_size - 1) // page_size,
                )
                connection.execute(f"PRAGMA max_page_count={ceiling}")
                inbox = Inbox(connection, root, binding, key, limits)
                if create:
                    connection.executescript("BEGIN IMMEDIATE;" + SCHEMA)
                    connection.execute(
                        "INSERT INTO metadata(name,value) VALUES('owner',?)",
                        (inbox._seal(FORMAT.encode(), "owner"),),
                    )
                    connection.commit()
                else:
                    row = connection.execute(
                        "SELECT value FROM metadata WHERE name='owner'"
                    ).fetchone()
                    if row is None or inbox._open(row[0], "owner") != FORMAT.encode():
                        raise InboxError("capture_integrity_failed")
                    inbox.fence_history_blocked()
                yield inbox
            finally:
                connection.rollback()
                connection.close()
    except sqlite3.Error as exc:
        code = (
            "capture_capacity_blocked"
            if getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_FULL
            else "capture_storage_unavailable"
        )
        raise InboxError(code) from None
    except local_state.LocalSetupError:
        raise InboxError("capture_storage_not_private") from None
