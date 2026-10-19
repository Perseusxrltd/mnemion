"""Copy reconciled legacy records into a private native space, without publishing."""

import hashlib
import json
from collections import Counter
from uuid import uuid5

from pydantic import ValidationError

from ..journal.format import JournalEntry, JournalError
from ..journal.privacy import scan
from .buffer_import_models import LegacyBufferRecord
from .errors import ServiceError
from .models import MemoryInput, SourceInput, json_value
from .private_import import authorize
from .repository import audit, idempotency, remember_receipt


def _digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Repeated JSON property")
        result[key] = value
    return result


def _records(command):
    text = command.jsonl.get_secret_value()
    try:
        size = len(text.encode("utf-8"))
    except UnicodeError:
        raise ServiceError(422, "buffer_invalid_input", "Use valid UTF-8 text.") from None
    if size > 1024**2 or (text and not text.endswith("\n")):
        raise ServiceError(
            422,
            "buffer_incomplete_input",
            "Use complete newline-terminated JSONL, no larger than 1 MiB.",
        )
    records, duplicates = {}, 0
    try:
        for line in text.removeprefix("\ufeff").split("\n"):
            if not line.strip():
                continue
            record = LegacyBufferRecord.model_validate(json.loads(line, object_pairs_hook=_object))
            if not record.text.strip():
                raise ValueError("Empty content")
            digest = _digest(record.model_dump(mode="json"))
            if record.id in records:
                if records[record.id][1] != digest:
                    raise ValueError("Conflicting identity")
                duplicates += 1
            else:
                records[record.id] = record, digest
            if len(records) > 100:
                raise ValueError("Too many records")
    except (ValueError, TypeError, RecursionError, ValidationError):
        raise ServiceError(
            422,
            "buffer_invalid_input",
            "A record is invalid, repeats an ID with different content, or exceeds the 100-record limit. Nothing was imported.",
        ) from None
    if not records and not command.withdrawn_ids:
        raise ServiceError(
            422, "buffer_empty_input", "Provide records or explicitly reviewed withdrawals."
        )
    return records, duplicates


def _authorize(conn, identity, space):
    authorize(conn, identity, space, code="buffer_private_space_required")


def _alias(namespace, legacy_id):
    return f"legacy-buffer:{namespace}:{legacy_id}"


def _plan(conn, identity, space, command, records, duplicates):
    items = []
    writers = set()
    denials = set(command.withdrawn_ids)
    for legacy_id in sorted(set(records) | denials, key=str):
        alias = _alias(command.namespace, legacy_id)
        memory = uuid5(space, alias)
        row = conn.execute(
            "SELECT id,version,deleted_at,review_state FROM mnemion.memories WHERE id=%s AND space_id=%s",
            (memory, space),
        ).fetchone()
        denied = conn.execute(
            "SELECT 1 FROM mnemion.recovery_denials WHERE memory_id=%s AND space_id=%s",
            (memory, space),
        ).fetchone()
        aliases = {
            r["legacy_id"]
            for r in conn.execute(
                "SELECT legacy_id FROM mnemion.legacy_aliases WHERE space_id=%s AND memory_id=%s",
                (space, memory),
            )
        }
        item = {
            "legacy_id": str(legacy_id),
            "memory_id": str(memory),
            "version": row["version"] if row else None,
        }
        if row and alias not in aliases:
            item.update(action="conflict", code="buffer_identity_conflict")
        elif legacy_id in denials:
            item["action"] = (
                "withdraw" if row and not row["deleted_at"] else "withdrawn" if denied else "deny"
            )
        elif denied or (row and row["deleted_at"]):
            item["action"] = "withdrawn"
        elif row:
            if alias + ":sha256:" + records[legacy_id][1] not in aliases:
                item.update(action="conflict", code="buffer_record_changed")
            else:
                item["action"] = (
                    "preserved_changes"
                    if row["version"] > 1 or row["review_state"] != "ordinary"
                    else "already_imported"
                )
        else:
            record = records[legacy_id][0]
            try:
                scan(
                    JournalEntry(
                        id=record.id,
                        ts=record.ts,
                        tenant_id=identity.tenant_id,
                        space_id=space,
                        memory_id=memory,
                        version=1,
                        writer=identity.principal_id,
                        action="upsert",
                        text=record.text,
                        subject=record.subject,
                        kind="note",
                        important=record.important,
                        metadata={"desk": record.desk, "journal": record.journal},
                    ),
                    personal_data=command.reject_personal_data,
                )
                item["action"] = "create"
            except JournalError as exc:
                item.update(action="rejected", code=exc.code)
        if item["action"] in {"create", "already_imported", "preserved_changes"}:
            writers.add(records[legacy_id][0].desk)
        items.append(item)
    input_digest = _digest(
        {
            "namespace": command.namespace,
            "jsonl": hashlib.sha256(command.jsonl.get_secret_value().encode()).hexdigest(),
            "withdrawn": sorted(str(value) for value in denials),
            "reject_personal_data": command.reject_personal_data,
        }
    )
    digest = _digest(
        {
            "format": "mnemion-legacy-buffer-review",
            "version": 1,
            "input": input_digest,
            "tenant": str(identity.tenant_id),
            "principal": str(identity.principal_id),
            "space": str(space),
            "items": items,
        }
    )
    counts = dict(Counter(item["action"] for item in items))
    return {
        "namespace": command.namespace,
        "space_id": str(space),
        "preview_sha256": digest,
        "input_sha256": input_digest,
        "can_import": not any(counts.get(key) for key in ("conflict", "rejected")),
        "duplicates": duplicates,
        "writers": sorted(writers),
        "items": items,
        "counts": counts,
        "source_only": True,
        "remote_delivery_verified": False,
    }


class BufferImportService:
    def __init__(self, memory):
        self.memory = memory
        self.db = memory.db

    def preview(self, identity, space, command):
        with self.db.administration_transaction(identity) as conn:
            _authorize(conn, identity, space)
            records, duplicates = _records(command)
            return _plan(conn, identity, space, command, records, duplicates)

    def apply(self, identity, space, command, key):
        from uuid import UUID

        with self.db.administration_transaction(identity) as conn:
            _authorize(conn, identity, space)
            records, duplicates = _records(command)
            plan = _plan(conn, identity, space, command, records, duplicates)
            digest, previous = idempotency(
                conn,
                identity,
                space,
                key,
                {
                    "kind": "buffer.import",
                    "input": plan["input_sha256"],
                    "preview": command.preview_sha256,
                },
            )
            if previous:
                return previous
            if plan["preview_sha256"] != command.preview_sha256:
                raise ServiceError(
                    409,
                    "buffer_preview_changed",
                    "The input or destination changed. Review a new preview before importing.",
                )
            if not plan["can_import"]:
                raise ServiceError(
                    409,
                    "buffer_review_required",
                    "Resolve rejected or conflicting records before importing this batch.",
                )
            for item in plan["items"]:
                memory = UUID(item["memory_id"])
                if item["action"] == "withdraw":
                    self.memory.forget_in_transaction(
                        conn,
                        identity,
                        memory,
                        expected_version=item["version"],
                        key=f"buffer-withdraw:{key}:{memory}",
                    )
                elif item["action"] == "deny":
                    conn.execute(
                        "INSERT INTO mnemion.recovery_denials(tenant_id,space_id,memory_id) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                        (identity.tenant_id, space, memory),
                    )
                elif item["action"] == "create":
                    record, fingerprint = records[UUID(item["legacy_id"])]
                    metadata = {
                        "buffer_import": {
                            "namespace": command.namespace,
                            "id": str(record.id),
                            "desk": record.desk,
                            "kind": record.kind,
                            "ts": record.ts.isoformat(),
                            "journal": record.journal,
                        },
                        "source_updated_at": record.ts.isoformat(),
                        "important": record.important,
                    }
                    content = MemoryInput(
                        content=record.text,
                        subject=record.subject,
                        kind="note",
                        metadata=metadata,
                        source=SourceInput(title="Reconciled legacy buffer record"),
                    )
                    conn.execute(
                        "INSERT INTO mnemion.memories(tenant_id,space_id,id,subject,kind,created_by) VALUES(%s,%s,%s,%s,'note',%s)",
                        (identity.tenant_id, space, memory, record.subject, identity.principal_id),
                    )
                    revision = self.memory._revision(conn, identity, space, memory, 1, content)
                    conn.execute(
                        "UPDATE mnemion.memories SET current_revision_id=%s,version=1 WHERE id=%s",
                        (revision, memory),
                    )
                    self.memory._operation(conn, identity, space, memory, revision, "ingest")
                    alias = _alias(command.namespace, record.id)
                    for value in (alias, alias + ":sha256:" + fingerprint):
                        conn.execute(
                            "INSERT INTO mnemion.legacy_aliases(tenant_id,space_id,legacy_id,memory_id) VALUES(%s,%s,%s,%s)",
                            (identity.tenant_id, space, value, memory),
                        )
            audit(
                conn,
                identity,
                "memory.buffer_imported",
                space,
                space_id=space,
                details={
                    "namespace": command.namespace,
                    "input_sha256": plan["input_sha256"],
                    "counts": plan["counts"],
                    "source_only": True,
                },
            )
            result = {
                field: plan[field]
                for field in (
                    "namespace",
                    "space_id",
                    "preview_sha256",
                    "counts",
                    "items",
                    "source_only",
                    "remote_delivery_verified",
                )
            }
            return remember_receipt(conn, identity, space, key, digest, json_value(result))
