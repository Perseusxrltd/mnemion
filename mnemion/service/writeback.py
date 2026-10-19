"""Opt-in journal capture, committed receipts and a separately authorized publisher."""

from __future__ import annotations

import logging
import threading
from uuid import UUID, uuid4

from ..journal.config import Configuration
from ..journal.format import JournalEntry, JournalError
from ..journal.git import GitJournal
from ..journal.notes import notes_prefix
from ..journal.privacy import scan
from ..journal.spool import Spool
from ..local_state import LocalSetupError, lock
from .db import Database, Identity, new_token, require_administrator, require_space
from .errors import ServiceError
from .models import json_value
from .repository import audit
from .writeback_models import WritebackPolicyInput

logger = logging.getLogger(__name__)

_EVENT = """SELECT e.*,r.content,r.subject,r.kind,r.metadata,m.deleted_at,m.review_state
    FROM mnemion.writeback_events e JOIN mnemion.memories m
      ON m.tenant_id=e.tenant_id AND m.space_id=e.space_id AND m.id=e.memory_id
    LEFT JOIN mnemion.memory_revisions r ON r.tenant_id=e.tenant_id
      AND r.space_id=e.space_id AND r.id=e.revision_id """


class WritebackService:
    def __init__(self, database: Database, configuration: Configuration | None = None):
        self.db = database
        self.configuration = (
            configuration if configuration is not None else Configuration.from_environment()
        )
        self.destinations = {(d.tenant_id, d.space_id): d for d in self.configuration.destinations}
        self._stop = threading.Event()
        self._thread = None
        self._step = threading.Lock()

    def destination(self, identity, space, settings=None):
        value = self.destinations.get((identity.tenant_id, space))
        if (
            value is None
            or settings is not None
            and (
                value.id != settings["destination_id"]
                or value.fingerprint != settings["fingerprint"]
            )
        ):
            raise ServiceError(
                409,
                "journal_destination_unavailable",
                "An administrator must approve the current host journal destination.",
            )
        return value

    @staticmethod
    def _settings(conn, space, *, locked=False):
        return conn.execute(
            "SELECT * FROM mnemion.writeback_settings WHERE space_id=%s"
            + (" FOR UPDATE" if locked else ""),
            (space,),
        ).fetchone()

    @staticmethod
    def _publisher(settings):
        return Identity(settings["tenant_id"], settings["publisher_id"], settings["key_id"])

    def configure(self, identity, space, command: WritebackPolicyInput):
        destination = self.destination(identity, space)
        if command.destination_id != destination.id:
            raise ServiceError(
                422,
                "journal_destination_mismatch",
                "Choose the approved destination for this space.",
            )
        with self.db.administration_transaction(identity) as conn:
            require_administrator(conn)
            require_space(conn, space, 40, writing=True)
            if conn.execute(
                "SELECT 1 FROM mnemion.connector_scopes WHERE space_id=%s", (space,)
            ).fetchone():
                raise ServiceError(
                    409,
                    "journal_native_space_required",
                    "Choose a writable native space; source spaces retain their provider's policy.",
                )
            settings = self._settings(conn, space, locked=True)
            if command.expected_version != (settings["version"] if settings else 0):
                raise ServiceError(
                    409, "version_conflict", "The journal policy changed; refresh before retrying."
                )
            # Authenticate and validate scope before touching operator storage.
            Spool(destination)
            if settings is None or command.repair_publisher:
                publisher, key = uuid4(), uuid4()
                token, digest = new_token()
                conn.execute(
                    """INSERT INTO mnemion.principals(tenant_id,id,name,kind,administrator)
                    VALUES (%s,%s,'Mnemion Git journal publisher','application',false)""",
                    (identity.tenant_id, publisher),
                )
                conn.execute(
                    """INSERT INTO mnemion.api_keys(tenant_id,id,principal_id,name,token_hash,prefix)
                    VALUES (%s,%s,%s,'Internal journal publisher',%s,%s)""",
                    (identity.tenant_id, key, publisher, digest, token[:12]),
                )
                # No bearer credential is saved or returned. This internal
                # publisher has one explicit grant and no organization role.
                del token
                conn.execute(
                    """INSERT INTO mnemion.space_grants(tenant_id,space_id,principal_id,role)
                    VALUES (%s,%s,%s,'reviewer')""",
                    (identity.tenant_id, space, publisher),
                )
                if settings:
                    conn.execute(
                        "UPDATE mnemion.api_keys SET revoked_at=coalesce(revoked_at,now()) WHERE id=%s",
                        (settings["key_id"],),
                    )
                    conn.execute(
                        "DELETE FROM mnemion.space_grants WHERE space_id=%s AND principal_id=%s",
                        (space, settings["publisher_id"]),
                    )
            else:
                publisher, key = settings["publisher_id"], settings["key_id"]
            folding = {
                name: getattr(command, name)
                if getattr(command, name) is not None
                else settings[name]
                if settings
                else default
                for name, default in (
                    ("fold_enabled", False),
                    ("fold_after_hours", 24),
                    ("fold_interval_seconds", 3600),
                )
            }
            conn.execute(
                """INSERT INTO mnemion.writeback_settings
                  (tenant_id,space_id,destination_id,fingerprint,publisher_id,key_id,paused,interval_seconds,created_by,
                   fold_enabled,fold_after_hours,fold_interval_seconds,next_fold_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s THEN clock_timestamp() END)
                ON CONFLICT(tenant_id,space_id) DO UPDATE SET destination_id=excluded.destination_id,
                  fingerprint=excluded.fingerprint,publisher_id=excluded.publisher_id,key_id=excluded.key_id,
                  paused=excluded.paused,interval_seconds=excluded.interval_seconds,version=writeback_settings.version+1,
                  updated_at=clock_timestamp(),next_push_at=clock_timestamp(),last_error=NULL,
                  fold_enabled=excluded.fold_enabled,fold_after_hours=excluded.fold_after_hours,
                  fold_interval_seconds=excluded.fold_interval_seconds,next_fold_at=excluded.next_fold_at,
                  last_fold_error=NULL""",
                (
                    identity.tenant_id,
                    space,
                    destination.id,
                    destination.fingerprint,
                    publisher,
                    key,
                    command.paused,
                    command.interval_seconds,
                    identity.principal_id,
                    folding["fold_enabled"],
                    folding["fold_after_hours"],
                    folding["fold_interval_seconds"],
                    folding["fold_enabled"],
                ),
            )
            audit(
                conn,
                identity,
                "journal.configured",
                space,
                space_id=space,
                details={
                    "destination_id": destination.id,
                    "paused": command.paused,
                    "retained_git_history_acknowledged": True,
                    "publisher_id": publisher,
                    **folding,
                    "notes_prefix": notes_prefix(destination) if folding["fold_enabled"] else None,
                },
            )
        return self.status(identity, space)

    def status(self, identity, space):
        with self.db.transaction(identity) as conn:
            require_space(conn, space)
            settings = self._settings(conn, space)
            destination = self.destinations.get((identity.tenant_id, space))
            permissions = conn.execute(
                """SELECT mnemion.administrator() AND mnemion.authorized(%s,40)
                AND NOT EXISTS (SELECT FROM mnemion.connector_scopes WHERE space_id=%s) AS configure,
                mnemion.authorized(%s,30) AS organize""",
                (space, space, space),
            ).fetchone()
            result = {
                "configured": settings is not None,
                "can_configure": permissions["configure"],
                "can_organize": permissions["organize"],
                "notes_prefix": notes_prefix(destination) if destination else None,
                "destination": {
                    "id": destination.id,
                    "label": destination.label,
                    "repository": destination.remote or "Local Git repository",
                    "branch": destination.branch,
                    "prefix": destination.prefix,
                    "personal_data_scan": destination.personal_data_scan,
                    "custom_scanner": bool(destination.scanner),
                }
                if destination
                else None,
                "version": settings["version"] if settings else 0,
                "state": "not_configured",
                "pending_entries": 0,
                "pending_content_bytes": 0,
                "external_history_retained": True,
                "existing_memories_backfilled": False,
            }
            if settings:
                publisher_live = conn.execute(
                    "SELECT mnemion.writeback_publisher_live(%s) AS live", (space,)
                ).fetchone()["live"]
                state = "paused" if settings["paused"] else "ready"
                if not publisher_live:
                    state = "publisher_unavailable"
                if not destination or destination.fingerprint != settings["fingerprint"]:
                    state = "destination_changed"
                pending = conn.execute(
                    """SELECT count(*) AS count,coalesce(sum(octet_length(r.content)),0) AS bytes
                    FROM mnemion.writeback_events e LEFT JOIN mnemion.memory_revisions r
                      ON r.tenant_id=e.tenant_id AND r.space_id=e.space_id AND r.id=e.revision_id
                    WHERE e.space_id=%s AND e.state IN ('pending','local')""",
                    (space,),
                ).fetchone()
                result.update(
                    state=state,
                    paused=settings["paused"],
                    interval_seconds=settings["interval_seconds"],
                    publisher_id=str(settings["publisher_id"]),
                    pending_entries=pending["count"],
                    pending_content_bytes=pending["bytes"],
                    last_push_at=settings["last_push_at"],
                    last_commit=settings["last_commit"],
                    last_error=settings["last_error"],
                    last_entries=settings["last_entries"],
                    last_bytes=settings["last_bytes"],
                    **{
                        field: settings[field]
                        for field in (
                            "fold_enabled",
                            "fold_after_hours",
                            "fold_interval_seconds",
                            "next_fold_at",
                            "last_fold_at",
                            "last_fold_commit",
                            "last_fold_error",
                            "last_fold_notes",
                            "last_fold_archived_files",
                            "last_fold_pending_notes",
                            "last_fold_pending_files",
                            "last_fold_read_bytes",
                            "last_fold_written_bytes",
                        )
                    },
                )
            return json_value(result)

    @staticmethod
    def _entry(row):
        return JournalEntry(
            id=row["id"],
            ts=row["created_at"],
            tenant_id=row["tenant_id"],
            space_id=row["space_id"],
            memory_id=row["memory_id"],
            version=row["version"],
            writer=row["writer"],
            action=row["action"],
            important=row["important"],
            text=row["content"] if row["action"] == "upsert" else None,
            subject=row["subject"] if row["action"] == "upsert" else None,
            metadata=row["metadata"] if row["action"] == "upsert" else {},
            kind=row["kind"] or "note",
        )

    def capture(self, conn, identity, space, memory, revision, version, event_id, action):
        settings = self._settings(conn, space)
        if settings is None:
            return None
        destination = self.destination(identity, space, settings)
        if action != "upsert":
            conn.execute(
                """UPDATE mnemion.writeback_events SET state='suppressed'
                WHERE space_id=%s AND memory_id=%s AND action='upsert' AND state IN ('pending','local')""",
                (space, memory),
            )
        conn.execute(
            """INSERT INTO mnemion.writeback_events
            (tenant_id,space_id,id,memory_id,revision_id,version,writer,action,important)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,coalesce((SELECT metadata->'important'='true'::jsonb
                FROM mnemion.memory_revisions WHERE id=%s),false))""",
            (
                identity.tenant_id,
                space,
                event_id,
                memory,
                revision,
                version,
                identity.principal_id,
                action,
                revision,
            ),
        )
        row = conn.execute(
            _EVENT + " WHERE e.space_id=%s AND e.id=%s", (space, event_id)
        ).fetchone()
        entry = self._entry(row)
        try:
            scan(entry, personal_data=destination.personal_data_scan, scanner=destination.scanner)
        except JournalError as error:
            raise ServiceError(
                422,
                error.code,
                "This space's publication scan rejected the memory; no save or journal entry was accepted.",
            ) from None
        receipt = {
            "event_id": str(event_id),
            "durability": "remote_git" if entry.important else "local_journal",
            "remote_pending": not entry.important,
            "external_history_retained": True,
        }
        self.db.after_commit(
            conn, lambda: self._after_commit(identity, space, event_id, important=entry.important)
        )
        return receipt

    def replay(self, conn, identity, receipt):
        journal = receipt.get("writeback")
        if journal:
            self.db.after_commit(
                conn,
                lambda: self._after_commit(
                    identity,
                    UUID(str(receipt["space_id"])),
                    UUID(journal["event_id"]),
                    important=journal["durability"] == "remote_git",
                ),
            )

    def _after_commit(self, identity, space, event_id, *, important=False):
        try:
            self.flush(identity, space, event_id)
            if important:
                self.push(identity, space, required=event_id)
        except (ServiceError, JournalError, OSError, LocalSetupError):
            raise ServiceError(
                503,
                "journal_delivery_pending",
                "The database change committed, but required journal delivery is pending. Retry with the same idempotency key; do not create another memory.",
            ) from None

    def flush(self, identity, space, event_id):
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 20)
            settings = self._settings(conn, space)
            destination = self.destination(identity, space, settings)
            row = conn.execute(
                _EVENT + " WHERE e.space_id=%s AND e.id=%s FOR UPDATE OF e", (space, event_id)
            ).fetchone()
            if not row or row["state"] in {"pushed", "suppressed"}:
                return
            if row["action"] == "upsert" and (
                row["deleted_at"] or row["review_state"] != "ordinary" or row["content"] is None
            ):
                conn.execute(
                    "UPDATE mnemion.writeback_events SET state='suppressed' WHERE id=%s",
                    (event_id,),
                )
                return
            entry = self._entry(row)
            spool = Spool(destination)
            if entry.action == "forget":
                spool.forget_pending_content(entry)
            else:
                spool.record(entry)
            conn.execute(
                """UPDATE mnemion.writeback_events SET state='local',journaled_at=coalesce(journaled_at,clock_timestamp())
                WHERE id=%s""",
                (event_id,),
            )

    def push(self, identity, space, *, expected_version=None, required=None):
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 20)
            settings = self._settings(conn, space)
            if settings is None:
                raise ServiceError(
                    409,
                    "journal_not_configured",
                    "Enable a host-approved journal destination first.",
                )
            if expected_version is not None and settings["version"] != expected_version:
                raise ServiceError(
                    409, "version_conflict", "The journal policy changed; refresh before retrying."
                )
            if settings["paused"]:
                raise ServiceError(
                    409, "journal_paused", "Publication is paused; local journal capture continues."
                )
            destination = self.destination(identity, space, settings)
            publisher = self._publisher(settings)
        with self.db.transaction(publisher) as conn:
            require_space(conn, space, 30)
            if (
                required is not None
                and conn.execute(
                    "SELECT 1 FROM mnemion.writeback_events WHERE id=%s AND state IN ('pushed','suppressed')",
                    (required,),
                ).fetchone()
            ):
                return {"already_delivered": True}
            rows = conn.execute(
                _EVENT
                + """ WHERE e.space_id=%s AND e.state IN ('pending','local')
                AND (e.action<>'upsert' OR (m.deleted_at IS NULL AND m.review_state='ordinary' AND r.id IS NOT NULL))
                ORDER BY (e.id=%s) DESC,e.created_at,e.id LIMIT %s""",
                (space, required, destination.max_batch_entries),
            ).fetchall()
            entries, size = [], 0
            for row in rows:
                value = self._entry(row)
                length = len(value.line())
                if size + length > destination.max_batch_bytes:
                    break
                entries.append(value)
                size += length
        if not entries:
            if required is not None:
                raise ServiceError(
                    409,
                    "journal_event_unavailable",
                    "The requested journal operation is not publishable.",
                )
            return {"entries": 0, "bytes": 0}
        for entry in entries:
            self.flush(publisher, space, entry.id)

        def current():
            with self.db.transaction(publisher) as conn:
                require_space(conn, space, 30)
                live = self._settings(conn, space)
                if not live or live["version"] != settings["version"] or live["paused"]:
                    raise JournalError("journal_policy_changed")
                count = conn.execute(
                    """SELECT count(*) AS count FROM mnemion.writeback_events e
                    JOIN mnemion.memories m ON m.tenant_id=e.tenant_id AND m.space_id=e.space_id AND m.id=e.memory_id
                    WHERE e.space_id=%s AND e.id=ANY(%s) AND e.state IN ('local','pushed')
                      AND (e.action<>'upsert' OR (m.deleted_at IS NULL AND m.review_state='ordinary'))""",
                    (space, [entry.id for entry in entries]),
                ).fetchone()["count"]
                if count != len(entries):
                    raise JournalError("journal_publication_changed")

        try:
            report = GitJournal(destination, cancel=self._stop).publish(
                entries, before_push=current
            )
            with self.db.transaction(publisher) as conn:
                conn.execute(
                    """UPDATE mnemion.writeback_events SET state='pushed',pushed_at=clock_timestamp(),commit_id=%s
                    WHERE space_id=%s AND id=ANY(%s) AND state='local'""",
                    (report["commit"], space, [e.id for e in entries]),
                )
                conn.execute(
                    """UPDATE mnemion.writeback_settings SET last_push_at=clock_timestamp(),last_commit=%s,
                    last_error=NULL,last_entries=%s,last_bytes=%s WHERE space_id=%s""",
                    (report["commit"], len(entries), size, space),
                )
                audit(
                    conn,
                    publisher,
                    "journal.published",
                    space,
                    space_id=space,
                    details={"commit": report["commit"], "entries": len(entries), "bytes": size},
                )
            spool = Spool(destination)
            with lock(spool.root):
                try:
                    spool.acknowledge(entries)
                except FileNotFoundError:
                    pass  # A concurrent denial may already have removed a private receipt.
            return report
        except (JournalError, OSError, LocalSetupError) as error:
            code = error.code if isinstance(error, JournalError) else "journal_storage_unavailable"
            with self.db.transaction(publisher) as conn:
                conn.execute(
                    "UPDATE mnemion.writeback_settings SET last_error=%s WHERE space_id=%s",
                    (code, space),
                )
            raise ServiceError(
                503,
                code,
                "Git publication is pending. Check this destination's Git credential manager, connection and journal status.",
            ) from None

    def start(self):
        if self.destinations and self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="mnemion-journal", daemon=True)
            self._thread.start()

    def organize(self, identity, space, *, expected_version=None):
        from .journal_folding import organize

        return organize(self, identity, space, expected_version=expected_version)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def run_once(self):
        if not self.destinations or not self._step.acquire(blocking=False):
            return False
        try:
            organizing = False
            with self.db.pool.connection() as conn:
                settings = conn.execute(
                    "SELECT * FROM mnemion.claim_writeback(%s)",
                    ([d.fingerprint for d in self.destinations.values()],),
                ).fetchone()
                if settings is None:
                    settings = conn.execute(
                        "SELECT * FROM mnemion.claim_journal_fold(%s)",
                        ([d.fingerprint for d in self.destinations.values()],),
                    ).fetchone()
                    organizing = settings is not None
            if settings is None:
                return False
            if organizing:
                self.organize(self._publisher(settings), settings["space_id"])
            else:
                self.push(self._publisher(settings), settings["space_id"])
            return True
        finally:
            self._step.release()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.run_once()
            except (ServiceError, JournalError, OSError, LocalSetupError):
                logger.info("Journal delivery remains pending; inspect the scoped journal status.")
            except Exception as error:
                logger.warning("Journal delivery deferred (%s)", type(error).__name__)
            self._stop.wait(5)
