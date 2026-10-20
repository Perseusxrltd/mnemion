"""Resumable, private journal staging with complete review before bounded writes."""

import base64
import binascii
import hashlib
from collections import Counter
from types import SimpleNamespace
from uuid import UUID, uuid4

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from ..journal.format import (
    MAX_LINE_BYTES,
    JournalError,
    journal_path,
    matches_path,
    parse_catalog,
    parse_line,
)
from .errors import ServiceError, not_found
from .journal_recovery import JournalRecoveryService, _authorize, _digest, _plan
from .journal_upload_models import (
    CHUNK_BYTES,
    REVIEW_BYTES,
    REVIEW_IDENTITIES,
    UPLOAD_BYTES,
    UPLOAD_IDENTITIES,
    UPLOAD_RECORDS,
    JournalUploadFile,
    JournalUploadStatus,
)
from .models import json_value
from .repository import audit, idempotency, remember_receipt


def _error(code, message, status=409):
    return ServiceError(status, "journal_upload_" + code, message)


def transport_digest(previous, offset, data):
    """A transport receipt, deliberately distinct from a raw file SHA-256."""
    return hashlib.sha256(
        bytes.fromhex(previous)
        + offset.to_bytes(8, "big")
        + len(data).to_bytes(8, "big")
        + hashlib.sha256(data).digest()
    ).hexdigest()


def _status(row):
    value = {
        **json_value(row),
        "bytes": row["total_bytes"],
        "can_restore": row["state"] == "reviewed"
        and not any(row["counts"].get(key) for key in ("conflict", "rejected")),
    }
    return JournalUploadStatus.model_validate(
        {key: value[key] for key in JournalUploadStatus.model_fields if key in value}
    ).model_dump(mode="json")


def _file(row):
    return JournalUploadFile(
        index=row["file_index"],
        path=row["path"],
        bytes=row["total_bytes"],
        received=row["received"],
        transport_sha256=row["transport_sha256"],
        complete=row["complete"],
    ).model_dump(mode="json")


class JournalUploadService:
    def __init__(self, memory):
        self.db = memory.db
        self.recovery = JournalRecoveryService(memory)

    def _load(self, conn, identity, space, upload):
        _authorize(conn, identity, space)
        row = conn.execute(
            """SELECT *,expires_at<=clock_timestamp() AS expired FROM mnemion.journal_uploads
               WHERE tenant_id=%s AND space_id=%s AND id=%s AND principal_id=%s FOR UPDATE""",
            (identity.tenant_id, space, upload, identity.principal_id),
        ).fetchone()
        if not row:
            raise not_found()
        if row["expired"]:
            raise _error(
                "expired", "This upload expired. Start again from the complete journal.", 410
            )
        return row

    @staticmethod
    def _touch(conn, row, **changes):
        # Only server-owned, fixed column names reach this helper.
        from psycopg import sql

        assignments = [sql.SQL("{}=%s").format(sql.Identifier(key)) for key in changes]
        values = [Jsonb(value) if isinstance(value, dict) else value for value in changes.values()]
        return conn.execute(
            sql.SQL("""UPDATE mnemion.journal_uploads SET {},version=version+1,
                updated_at=clock_timestamp(),expires_at=clock_timestamp()+interval '24 hours'
                WHERE tenant_id=%s AND id=%s RETURNING *""").format(sql.SQL(",").join(assignments)),
            (*values, row["tenant_id"], row["id"]),
        ).fetchone()

    def begin(self, identity, space, command, key):
        try:
            catalog_bytes = command.catalog.get_secret_value().encode("utf-8")
            catalog = parse_catalog(catalog_bytes)
            files = sorted(command.files, key=lambda item: item.path)
            total = sum(item.bytes for item in files)
            if total + len(catalog_bytes) > UPLOAD_BYTES:
                raise JournalError("journal_upload_byte_limit")
            if len({item.path for item in files}) != len(files):
                raise JournalError("journal_upload_duplicate_path")
            for item in files:
                _, _, part = journal_path(item.path.removeprefix("_archive/"))
                if part and catalog.schema_version < 2:
                    raise JournalError("journal_recovery_catalog_version")
            digest = _digest(
                {
                    "identity_mode": command.identity_mode,
                    "catalog": hashlib.sha256(catalog_bytes).hexdigest(),
                    "files": [item.model_dump() for item in files],
                    "withdrawn": sorted(str(value) for value in set(command.withdrawn_ids)),
                    "reject_personal_data": command.reject_personal_data,
                }
            )
        except (JournalError, UnicodeError) as exc:
            raise ServiceError(
                422,
                getattr(exc, "code", "journal_upload_invalid_input"),
                "Supply a complete native catalog and matching journal file declarations, up to 2 GiB.",
            ) from None
        with self.db.administration_transaction(identity) as conn:
            _authorize(conn, identity, space)
            receipt_hash, previous = idempotency(
                conn, identity, space, key, {"kind": "journal.upload", "declaration": digest}
            )
            if previous:
                return _status(self._load(conn, identity, space, UUID(previous["id"])))
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"journal-upload-capacity:{identity.tenant_id}:{identity.principal_id}",),
            )
            if not conn.execute(
                "SELECT mnemion.journal_upload_capacity(%s) AS ok", (total,)
            ).fetchone()["ok"]:
                raise _error(
                    "capacity",
                    "Cancel an unfinished upload or allow expired staging to be cleaned. Each administrator has two active uploads and 4 GiB of retained staging.",
                    429,
                )
            upload = uuid4()
            row = conn.execute(
                """INSERT INTO mnemion.journal_uploads
                   (tenant_id,id,space_id,principal_id,identity_mode,namespace,catalog_schema,
                    reject_personal_data,declaration_sha256,input_sha256,total_bytes,files,
                    completed_files,expected_records,identities)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (
                    identity.tenant_id,
                    upload,
                    space,
                    identity.principal_id,
                    command.identity_mode,
                    catalog.namespace,
                    catalog.schema_version,
                    command.reject_personal_data,
                    digest,
                    digest,
                    total,
                    len(files),
                    sum(item.bytes == 0 for item in files),
                    catalog.records,
                    len(set(command.withdrawn_ids)),
                ),
            ).fetchone()
            with conn.cursor() as cursor:
                cursor.executemany(
                    """INSERT INTO mnemion.journal_upload_files
                       (tenant_id,upload_id,file_index,path,total_bytes,complete) VALUES(%s,%s,%s,%s,%s,%s)""",
                    [
                        (identity.tenant_id, upload, index, item.path, item.bytes, item.bytes == 0)
                        for index, item in enumerate(files)
                    ],
                )
                cursor.executemany(
                    """INSERT INTO mnemion.journal_upload_latest
                       (tenant_id,upload_id,original_id,source_version,denied,priority)
                       VALUES(%s,%s,%s,0,true,0)""",
                    [
                        (identity.tenant_id, upload, original)
                        for original in set(command.withdrawn_ids)
                    ],
                )
            remember_receipt(conn, identity, space, key, receipt_hash, {"id": str(upload)})
            audit(
                conn,
                identity,
                "memory.journal_upload_started",
                upload,
                space_id=space,
                details={"files": len(files), "bytes": total, "namespace": catalog.namespace},
            )
            return _status(row)

    def get(self, identity, space, upload):
        with self.db.administration_transaction(identity) as conn:
            return _status(self._load(conn, identity, space, upload))

    def list(self, identity, space):
        with self.db.administration_transaction(identity) as conn:
            _authorize(conn, identity, space)
            return {
                "items": [
                    _status(row)
                    for row in conn.execute(
                        """SELECT * FROM mnemion.journal_uploads WHERE tenant_id=%s AND space_id=%s
                   AND principal_id=%s AND expires_at>clock_timestamp() ORDER BY created_at DESC LIMIT 8""",
                        (identity.tenant_id, space, identity.principal_id),
                    ).fetchall()
                ]
            }

    def files(self, identity, space, upload, cursor=0):
        with self.db.administration_transaction(identity) as conn:
            self._load(conn, identity, space, upload)
            rows = conn.execute(
                """SELECT file_index,path,total_bytes,received,transport_sha256,complete
                   FROM mnemion.journal_upload_files WHERE tenant_id=%s AND upload_id=%s
                   AND file_index>=%s ORDER BY file_index LIMIT 129""",
                (identity.tenant_id, upload, cursor),
            ).fetchall()
            return {
                "items": [_file(row) for row in rows[:128]],
                "next_cursor": rows[128]["file_index"] if len(rows) > 128 else None,
            }

    def decisions(self, identity, space, upload, cursor=0):
        with self.db.administration_transaction(identity) as conn:
            self._load(conn, identity, space, upload)
            rows = conn.execute(
                """SELECT batch_index,items FROM mnemion.journal_upload_batches
                   WHERE tenant_id=%s AND upload_id=%s AND batch_index>=%s
                   ORDER BY batch_index LIMIT 3""",
                (identity.tenant_id, upload, cursor),
            ).fetchall()
            return {
                "items": [item for row in rows[:2] for item in row["items"]],
                "next_cursor": rows[2]["batch_index"] if len(rows) > 2 else None,
            }

    def chunk(self, identity, space, upload, index, command):
        try:
            data = base64.b64decode(command.data.get_secret_value(), validate=True)
        except (ValueError, binascii.Error):
            raise _error("invalid_chunk", "Send one base64-encoded binary chunk.", 422) from None
        if not 0 < len(data) <= CHUNK_BYTES or hashlib.sha256(data).hexdigest() != command.sha256:
            raise _error("invalid_chunk", "The chunk length or SHA-256 does not match.", 422)
        try:
            with self.db.administration_transaction(identity) as conn:
                row = self._load(conn, identity, space, upload)
                file = conn.execute(
                    "SELECT * FROM mnemion.journal_upload_files WHERE tenant_id=%s AND upload_id=%s AND file_index=%s",
                    (identity.tenant_id, upload, index),
                ).fetchone()
                if not file:
                    raise not_found()
                previous = conn.execute(
                    """SELECT bytes,sha256 FROM mnemion.journal_upload_chunks
                       WHERE tenant_id=%s AND upload_id=%s AND file_index=%s AND file_offset=%s""",
                    (identity.tenant_id, upload, index, command.offset),
                ).fetchone()
                if previous:
                    if previous != {"bytes": len(data), "sha256": command.sha256}:
                        raise _error(
                            "chunk_changed",
                            "These bytes differ from an accepted chunk. Use the original files or start a new upload.",
                        )
                    return {"upload": _status(row), "file": _file(file), "repeated": True}
                if row["state"] != "uploading":
                    raise _error(
                        "state", "This upload is sealed. Start another upload for changed files."
                    )
                remaining = file["total_bytes"] - file["received"]
                if command.offset != file["received"] or len(data) != min(CHUNK_BYTES, remaining):
                    raise _error(
                        "offset",
                        "Resume at the acknowledged offset using full chunks except at the end of a file.",
                    )
                received = file["received"] + len(data)
                combined = bytes(file["tail"]) + data
                lines = combined.split(b"\n")
                tail = lines.pop()
                if len(tail) >= MAX_LINE_BYTES or (received == file["total_bytes"] and tail):
                    raise JournalError("journal_incomplete_or_oversized_record")
                entries = [parse_line(line + b"\n") for line in lines]
                for entry in entries:
                    if entry.origin.rsplit(":", 1)[0] != row["namespace"] or not matches_path(
                        entry, file["path"].removeprefix("_archive/")
                    ):
                        raise JournalError("journal_record_path_mismatch")
                metrics = self._stage(conn, row, entries)
                file = conn.execute(
                    """UPDATE mnemion.journal_upload_files SET received=%s,tail=%s,
                       transport_sha256=%s,complete=%s WHERE tenant_id=%s AND upload_id=%s
                       AND file_index=%s RETURNING *""",
                    (
                        received,
                        tail,
                        transport_digest(file["transport_sha256"], command.offset, data),
                        received == file["total_bytes"],
                        identity.tenant_id,
                        upload,
                        index,
                    ),
                ).fetchone()
                conn.execute(
                    """INSERT INTO mnemion.journal_upload_chunks
                       (tenant_id,upload_id,file_index,file_offset,bytes,sha256) VALUES(%s,%s,%s,%s,%s,%s)""",
                    (identity.tenant_id, upload, index, command.offset, len(data), command.sha256),
                )
                row = self._touch(
                    conn,
                    row,
                    **metrics,
                    received=row["received"] + len(data),
                    completed_files=row["completed_files"] + int(file["complete"]),
                )
                return {"upload": _status(row), "file": _file(file), "repeated": False}
        except JournalError as exc:
            raise ServiceError(
                422,
                exc.code,
                "The journal is inconsistent, incomplete or exceeds a recovery limit. This chunk was not accepted.",
            ) from None
        except UniqueViolation:
            raise _error(
                "version_conflict",
                "Two records claim the same identity and version. Supply an unambiguous complete journal.",
            ) from None

    @staticmethod
    def _stage(conn, row, entries):
        physical = row["physical_records"] + len(entries)
        if physical > UPLOAD_RECORDS:
            raise JournalError("journal_upload_record_limit")
        unique = {}
        for entry in entries:
            if entry.id in unique and unique[entry.id].digest != entry.digest:
                raise JournalError("journal_conflicting_record")
            unique[entry.id] = entry
        known = conn.execute(
            """SELECT event_id,digest FROM mnemion.journal_upload_events
               WHERE tenant_id=%s AND upload_id=%s AND event_id=ANY(%s)""",
            (row["tenant_id"], row["id"], list(unique)),
        ).fetchall()
        for previous in known:
            if unique[previous["event_id"]].digest != previous["digest"]:
                raise JournalError("journal_conflicting_record")
            del unique[previous["event_id"]]
        records = row["records"] + len(unique)
        if records > row["expected_records"]:
            raise JournalError("journal_incomplete_inventory")
        latest = {}
        for entry in unique.values():
            old, denied = latest.get(entry.memory_id, (entry, False))
            if old.version == entry.version and old.digest != entry.digest:
                raise JournalError("journal_conflicting_version")
            latest[entry.memory_id] = (
                max((old, entry), key=lambda value: value.version),
                denied or entry.action == "forget",
            )
        existing = conn.execute(
            """SELECT original_id FROM mnemion.journal_upload_latest
               WHERE tenant_id=%s AND upload_id=%s AND original_id=ANY(%s)""",
            (row["tenant_id"], row["id"], list(latest)),
        ).fetchall()
        identities = row["identities"] + len(latest) - len(existing)
        if identities > UPLOAD_IDENTITIES:
            raise JournalError("journal_upload_identity_limit")
        with conn.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO mnemion.journal_upload_events
                   (tenant_id,upload_id,event_id,original_id,source_version,digest) VALUES(%s,%s,%s,%s,%s,%s)""",
                [
                    (
                        row["tenant_id"],
                        row["id"],
                        entry.id,
                        entry.memory_id,
                        entry.version,
                        entry.digest,
                    )
                    for entry in unique.values()
                ],
            )
            cursor.executemany(
                """INSERT INTO mnemion.journal_upload_latest AS old
                   (tenant_id,upload_id,original_id,source_version,denied,action,priority,line)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(tenant_id,upload_id,original_id) DO UPDATE SET
                   source_version=greatest(old.source_version,excluded.source_version),
                   denied=old.denied OR excluded.denied,
                   action=CASE WHEN excluded.source_version>old.source_version THEN excluded.action ELSE old.action END,
                   line=CASE WHEN excluded.source_version>old.source_version THEN excluded.line ELSE old.line END,
                   priority=CASE WHEN old.denied OR excluded.denied OR
                       (CASE WHEN excluded.source_version>old.source_version THEN excluded.action ELSE old.action END)='quarantine'
                       THEN 0 ELSE 1 END""",
                [
                    (
                        row["tenant_id"],
                        row["id"],
                        original,
                        entry.version,
                        denied,
                        entry.action,
                        0 if denied or entry.action == "quarantine" else 1,
                        entry.line(),
                    )
                    for original, (entry, denied) in latest.items()
                ],
            )
        return {
            "physical_records": physical,
            "records": records,
            "duplicates": physical - records,
            "identities": identities,
        }

    @staticmethod
    def _batch(conn, row, *, saved=None):
        params = [row["tenant_id"], row["id"]]
        if saved:
            condition = "priority=%s AND original_id BETWEEN %s AND %s"
            params.extend((saved["priority"], saved["first_id"], saved["last_id"]))
        else:
            condition = "(priority,original_id)>(%s,%s)"
            params.extend((row["review_priority"], row["review_cursor"]))
        # Fetch only lengths first; selecting 64 maximum-size bodies could consume
        # far more than the review byte budget before Python can stop iteration.
        headers = conn.execute(
            """SELECT original_id,priority,coalesce(octet_length(line),0) AS bytes
               FROM mnemion.journal_upload_latest WHERE tenant_id=%s AND upload_id=%s AND """
            + condition
            + " ORDER BY priority,original_id LIMIT %s",
            (*params, REVIEW_IDENTITIES),
        ).fetchall()
        selected, total = [], 0
        for header in headers:
            if selected and (
                header["priority"] != selected[0]["priority"]
                or total + header["bytes"] > REVIEW_BYTES
            ):
                break
            selected.append(header)
            total += header["bytes"]
        if not selected:
            return [], {}
        latest = {}
        for item in conn.execute(
            """SELECT original_id,line,denied FROM mnemion.journal_upload_latest
               WHERE tenant_id=%s AND upload_id=%s AND original_id=ANY(%s)""",
            (row["tenant_id"], row["id"], [item["original_id"] for item in selected]),
        ).fetchall():
            latest[item["original_id"]] = (
                parse_line(bytes(item["line"])) if item["line"] is not None else None,
                item["denied"],
            )
        return selected, latest

    @staticmethod
    def _plan(conn, identity, space, row, latest):
        command = SimpleNamespace(
            identity_mode=row["identity_mode"],
            reject_personal_data=row["reject_personal_data"],
            withdrawn_ids=[],
        )
        return _plan(
            conn,
            identity,
            space,
            command,
            (
                SimpleNamespace(namespace=row["namespace"]),
                latest,
                {
                    "records": row["records"],
                    "duplicates": row["duplicates"],
                    "bytes": row["total_bytes"],
                },
                row["input_sha256"],
            ),
        )

    def advance(self, identity, space, upload, command):
        try:
            return self._advance(identity, space, upload, command)
        except UniqueViolation:
            raise _error(
                "identity_conflict",
                "A recovery identity changed. Review the complete inventory again before continuing.",
            ) from None

    def _advance(self, identity, space, upload, command):
        with self.db.administration_transaction(identity) as conn:
            row = self._load(conn, identity, space, upload)
            if command.expected_version != row["version"]:
                raise _error(
                    "version_changed",
                    "Progress changed. Refresh this upload before continuing; accepted batches are already recorded.",
                )
            action = command.action
            allowed = {
                "finish_upload": {"uploading"},
                "review": {"reviewing"},
                "restart_review": {"reviewing", "reviewed", "restoring"},
                "authorize": {"reviewed"},
                "restore": {"restoring"},
                "cancel": {"uploading", "reviewing", "reviewed", "restoring", "completed"},
            }
            if row["state"] not in allowed[action]:
                raise _error("state", "Refresh the upload to see its current available actions.")
            if action == "cancel":
                row = self._touch(conn, row, state="cancelled")
                row = conn.execute(
                    "UPDATE mnemion.journal_uploads SET expires_at=clock_timestamp() WHERE tenant_id=%s AND id=%s RETURNING *",
                    (identity.tenant_id, upload),
                ).fetchone()
            elif action == "finish_upload":
                if (
                    row["completed_files"] != row["files"]
                    or row["records"] != row["expected_records"]
                ):
                    raise _error(
                        "incomplete",
                        "Upload every declared file, including archives and continuations, before review.",
                    )
                chain = row["declaration_sha256"]
                with conn.cursor(name="journal_inventory") as cursor:
                    cursor.execute(
                        """SELECT file_index,transport_sha256 FROM mnemion.journal_upload_files
                        WHERE tenant_id=%s AND upload_id=%s ORDER BY file_index""",
                        (identity.tenant_id, upload),
                    )
                    for file in cursor:
                        chain = _digest([chain, file["file_index"], file["transport_sha256"]])
                row = self._touch(conn, row, state="reviewing", input_sha256=chain)
            elif action == "restart_review":
                conn.execute(
                    "DELETE FROM mnemion.journal_upload_batches WHERE tenant_id=%s AND upload_id=%s",
                    (identity.tenant_id, upload),
                )
                row = self._touch(
                    conn,
                    row,
                    state="reviewing",
                    preview_sha256=None,
                    review_priority=-1,
                    review_cursor=UUID(int=0),
                    reviewed_batches=0,
                    applied_batches=0,
                    reviewed_identities=0,
                    processed_identities=0,
                    counts={},
                    applied_counts={},
                )
            elif action == "review":
                selected, latest = self._batch(conn, row)
                if not selected:
                    row = self._touch(
                        conn,
                        row,
                        state="reviewed",
                        preview_sha256=row["preview_sha256"]
                        or _digest([row["input_sha256"], "empty"]),
                    )
                else:
                    plan, _ = self._plan(conn, identity, space, row, latest)
                    conn.execute(
                        """INSERT INTO mnemion.journal_upload_batches
                        (tenant_id,upload_id,batch_index,priority,first_id,last_id,sha256,items)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (
                            identity.tenant_id,
                            upload,
                            row["reviewed_batches"],
                            selected[0]["priority"],
                            selected[0]["original_id"],
                            selected[-1]["original_id"],
                            plan["preview_sha256"],
                            Jsonb(plan["items"]),
                        ),
                    )
                    counts = dict(Counter(row["counts"]) + Counter(plan["counts"]))
                    reviewed = row["reviewed_identities"] + len(latest)
                    row = self._touch(
                        conn,
                        row,
                        reviewed_batches=row["reviewed_batches"] + 1,
                        reviewed_identities=reviewed,
                        counts=counts,
                        review_priority=selected[-1]["priority"],
                        review_cursor=selected[-1]["original_id"],
                        preview_sha256=_digest(
                            [row["preview_sha256"] or row["input_sha256"], plan["preview_sha256"]]
                        ),
                        state="reviewed" if reviewed == row["identities"] else "reviewing",
                    )
            elif action == "authorize":
                if not all(
                    (
                        command.reviewed_complete_inventory,
                        command.reviewed_withdrawals,
                        command.acknowledge_source_only,
                        command.acknowledge_resumable_batches,
                    )
                ):
                    raise _error(
                        "approval_required",
                        "Confirm the complete inventory, later withdrawals, private destination and resumable batch behavior before restoring.",
                        422,
                    )
                if (
                    not _status(row)["can_restore"]
                    or command.preview_sha256 != row["preview_sha256"]
                ):
                    raise _error(
                        "review_required",
                        "Resolve rejected or conflicting records and approve the current complete review.",
                    )
                row = self._touch(
                    conn, row, state="restoring" if row["identities"] else "completed"
                )
            elif action == "restore":
                saved = conn.execute(
                    """SELECT * FROM mnemion.journal_upload_batches
                    WHERE tenant_id=%s AND upload_id=%s AND batch_index=%s AND NOT applied""",
                    (identity.tenant_id, upload, row["applied_batches"]),
                ).fetchone()
                if not saved:
                    raise _error(
                        "review_required",
                        "The reviewed batch is unavailable. Review again before continuing.",
                    )
                _, latest = self._batch(conn, row, saved=saved)
                plan, states = self._plan(conn, identity, space, row, latest)
                if not plan["can_restore"] or plan["preview_sha256"] != saved["sha256"]:
                    raise _error(
                        "preview_changed",
                        "The destination changed. Earlier batches remain saved; review again before continuing.",
                    )
                self.recovery.apply_items(
                    conn, identity, space, f"upload:{upload}:{row['version']}", plan, states, latest
                )
                conn.execute(
                    """UPDATE mnemion.journal_upload_batches SET applied=true
                    WHERE tenant_id=%s AND upload_id=%s AND batch_index=%s""",
                    (identity.tenant_id, upload, saved["batch_index"]),
                )
                applied = row["applied_batches"] + 1
                row = self._touch(
                    conn,
                    row,
                    applied_batches=applied,
                    processed_identities=row["processed_identities"] + len(latest),
                    applied_counts=dict(Counter(row["applied_counts"]) + Counter(plan["counts"])),
                    state="completed" if applied == row["reviewed_batches"] else "restoring",
                )
                audit(
                    conn,
                    identity,
                    "memory.journal_batch_recovered",
                    upload,
                    space_id=space,
                    details={
                        "batch": saved["batch_index"],
                        "counts": plan["counts"],
                        "source_only": True,
                    },
                )
            if action in {"cancel", "restart_review", "authorize", "finish_upload"}:
                audit(
                    conn,
                    identity,
                    "memory.journal_upload_" + action,
                    upload,
                    space_id=space,
                    details={
                        "state": row["state"],
                        "processed_identities": row["processed_identities"],
                    },
                )
            return _status(row)
