"""Restore a complete journal projection, preserving local decisions and denials."""

import hashlib
import io
import json
import sqlite3
from collections import Counter
from uuid import UUID, uuid5

from pydantic import ValidationError
from psycopg.errors import UniqueViolation

from ..journal.format import (
    JournalError,
    journal_path,
    matches_path,
    parse_catalog,
    parse_file,
    parse_line,
)
from ..journal.index import JournalIndex
from ..journal.privacy import scan
from .errors import ServiceError
from .journal_recovery_models import MAX_RECOVERY_BYTES, MAX_RECOVERY_IDENTITIES
from .models import MemoryInput, SourceInput, json_value
from .private_import import authorize
from .repository import audit, idempotency, remember_receipt


def _digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _inventory(command):
    """Validate every file before considering any positive memory."""
    index_db = sqlite3.connect(":memory:")
    try:
        catalog_bytes = command.catalog.get_secret_value().encode("utf-8")
        catalog = parse_catalog(catalog_bytes)
        if catalog.records > 10_000:
            raise JournalError("journal_recovery_record_limit")
        size = len(catalog_bytes)
        files = {}
        index = JournalIndex(index_db, max_records=10_000, max_bytes=MAX_RECOVERY_BYTES)
        for file in command.files:
            if file.path in files:
                raise JournalError("journal_recovery_duplicate_path")
            relative = file.path.removeprefix("_archive/")
            _, _, part = journal_path(relative)
            if part and catalog.schema_version < 2:
                raise JournalError("journal_recovery_catalog_version")
            data = file.text.get_secret_value().encode("utf-8")
            size += len(data)
            if size > MAX_RECOVERY_BYTES:
                raise JournalError("journal_recovery_byte_limit")
            files[file.path] = hashlib.sha256(data).hexdigest()
            for entry in parse_file(io.BytesIO(data), maximum=MAX_RECOVERY_BYTES):
                if (entry.tenant_id, entry.space_id) != (
                    catalog.tenant_id,
                    catalog.space_id,
                ) or not matches_path(entry, relative):
                    raise JournalError("journal_record_path_mismatch")
                index.add(entry)
        expected = {catalog.namespace: catalog.records} if catalog.records else {}
        if index.inventories() != expected:
            raise JournalError("journal_incomplete_inventory")
        latest = {}
        for line, denied in index_db.execute("SELECT line,denied FROM latest ORDER BY origin"):
            entry = parse_line(line)
            latest[entry.memory_id] = (entry, bool(denied))
        if len(set(latest) | set(command.withdrawn_ids)) > MAX_RECOVERY_IDENTITIES:
            raise JournalError("journal_recovery_identity_limit")
        digest = _digest(
            {
                "identity_mode": command.identity_mode,
                "catalog": hashlib.sha256(catalog_bytes).hexdigest(),
                "files": files,
                "withdrawn": sorted(str(value) for value in set(command.withdrawn_ids)),
                "reject_personal_data": command.reject_personal_data,
            }
        )
        return catalog, latest, {**index.describe(), "bytes": size}, digest
    except (JournalError, UnicodeError, ValueError, TypeError) as exc:
        raise ServiceError(
            422,
            exc.code if isinstance(exc, JournalError) else "journal_recovery_invalid_input",
            "Provide the complete native catalog, active files and archives with matching paths. The limit is 1 MiB, 10,000 physical records and 1,000 memory identities; never split or reduce a catalog to fit. Nothing was restored.",
        ) from None
    finally:
        index_db.close()


def _content(entry):
    return MemoryInput(
        content=entry.text,
        subject=entry.subject,
        kind=entry.kind,
        metadata={
            "journal_recovery": {
                "origin": entry.origin,
                "entry_id": str(entry.id),
                "version": entry.version,
                "writer": str(entry.writer),
                "timestamp": entry.ts.isoformat(),
                "metadata": entry.metadata,
            },
            "source_updated_at": entry.ts.isoformat(),
            "important": entry.important,
        },
        source=SourceInput(title="Recovered native journal record"),
    )


def _authorize(conn, identity, space):
    authorize(conn, identity, space, code="journal_recovery_private_space_required")


def _plan(conn, identity, space, command, inventory):
    catalog, latest, metrics, input_digest = inventory
    items = []
    external_denials = set(command.withdrawn_ids)
    identities = {
        original: (
            original
            if command.identity_mode == "original"
            else uuid5(space, f"native-journal:{catalog.namespace}:{original}")
        )
        for original in set(latest) | external_denials
    }
    for memory in sorted(identities.values(), key=str):
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
            (f"mnemion-journal-identity:{identity.tenant_id}:{memory}",),
        )
    for original in sorted(set(latest) | external_denials, key=str):
        origin = f"{catalog.namespace}:{original}"
        memory = identities[original]
        available = conn.execute(
            "SELECT mnemion.recovery_identity_available(%s,%s) AS available",
            (space, memory),
        ).fetchone()["available"]
        entry, forgotten = latest.get(original, (None, False))
        row = conn.execute(
            "SELECT id,version,deleted_at,review_state FROM mnemion.memories WHERE id=%s AND space_id=%s",
            (memory, space),
        ).fetchone()
        mapping = conn.execute(
            "SELECT * FROM mnemion.journal_recovery_origins WHERE space_id=%s AND origin=%s",
            (space, origin),
        ).fetchone()
        denied = conn.execute(
            "SELECT 1 FROM mnemion.recovery_denials WHERE space_id=%s AND memory_id=%s",
            (space, memory),
        ).fetchone()
        item = {
            "original_id": str(original),
            "memory_id": str(memory),
            "source_version": entry.version if entry else None,
            "version": row["version"] if row else None,
        }
        local_changed = bool(
            mapping
            and (
                mapping["locally_modified"]
                or (
                    row
                    and (
                        row["version"] != mapping["local_version"]
                        or row["review_state"]
                        != (
                            "quarantined"
                            if mapping["source_action"] == "quarantine"
                            else "ordinary"
                        )
                    )
                )
            )
        )
        if not available or (row and not mapping) or (mapping and mapping["memory_id"] != memory):
            item.update(action="conflict", code="journal_recovery_identity_conflict")
        elif forgotten or original in external_denials:
            item["action"] = (
                "withdraw" if row and not row["deleted_at"] else "withdrawn" if denied else "deny"
            )
        elif denied or (row and row["deleted_at"]):
            item["action"] = "withdrawn"
        elif mapping and entry.version < mapping["source_version"]:
            item["action"] = "stale_source"
        elif mapping and entry.version == mapping["source_version"]:
            if entry.digest != mapping["source_digest"]:
                item.update(action="conflict", code="journal_recovery_version_conflict")
            elif mapping["source_action"] == "quarantine" and not row:
                item["action"] = "held"
            elif not row:
                item.update(action="conflict", code="journal_recovery_missing_memory")
            else:
                item["action"] = (
                    "preserved_changes"
                    if local_changed
                    else "held"
                    if entry.action == "quarantine"
                    else "already_restored"
                )
        elif entry.action == "quarantine":
            item["action"] = "quarantine" if row else "hold"
        elif local_changed:
            item["action"] = "preserved_changes"
        elif mapping and mapping["source_action"] == "upsert" and not row:
            item.update(action="conflict", code="journal_recovery_missing_memory")
        else:
            try:
                scan(entry, personal_data=command.reject_personal_data)
                _content(entry)  # Check that provenance also fits native metadata limits.
                item["action"] = "update" if row else "release" if mapping else "create"
            except (JournalError, ValidationError) as exc:
                item.update(
                    action="rejected",
                    code=exc.code
                    if isinstance(exc, JournalError)
                    else "journal_recovery_metadata_limit",
                )
        # Bind every mutable identity fact, even when its visible action is unchanged.
        state = {
            "row": json_value(row),
            "mapping": json_value(mapping),
            "denied": bool(denied),
            "locally_modified": local_changed,
        }
        items.append((item, state))
    counts = dict(Counter(item["action"] for item, _ in items))
    digest = _digest(
        {
            "format": "mnemion-native-journal-review",
            "version": 1,
            "input": input_digest,
            "tenant": str(identity.tenant_id),
            "principal": str(identity.principal_id),
            "space": str(space),
            "items": items,
        }
    )
    return {
        "identity_mode": command.identity_mode,
        "namespace": catalog.namespace,
        "space_id": str(space),
        "preview_sha256": digest,
        "input_sha256": input_digest,
        "can_restore": not any(counts.get(key) for key in ("conflict", "rejected")),
        "records": metrics["records"],
        "duplicates": metrics["duplicates"],
        "bytes": metrics["bytes"],
        "counts": counts,
        "items": [item for item, _ in items],
        "source_only": True,
        "remote_delivery_verified": False,
    }, {item["original_id"]: state for item, state in items}


class JournalRecoveryService:
    def __init__(self, memory):
        self.memory, self.db = memory, memory.db

    def preview(self, identity, space, command):
        with self.db.administration_transaction(identity) as conn:
            _authorize(conn, identity, space)
            return _plan(conn, identity, space, command, _inventory(command))[0]

    def apply(self, identity, space, command, key):
        try:
            return self._apply(identity, space, command, key)
        except UniqueViolation:
            raise ServiceError(
                409,
                "journal_recovery_identity_conflict",
                "A recovery identity is already present. Review again or choose independent copies in a new private destination.",
            ) from None

    def _apply(self, identity, space, command, key):
        with self.db.administration_transaction(identity) as conn:
            _authorize(conn, identity, space)
            inventory = _inventory(command)
            plan, states = _plan(conn, identity, space, command, inventory)
            digest, previous = idempotency(
                conn,
                identity,
                space,
                key,
                {
                    "kind": "journal.recover",
                    "input": plan["input_sha256"],
                    "preview": command.preview_sha256,
                },
            )
            if previous:
                return previous
            if plan["preview_sha256"] != command.preview_sha256:
                raise ServiceError(
                    409,
                    "journal_recovery_preview_changed",
                    "The journal or destination changed. Review a fresh preview before restoring.",
                )
            if not plan["can_restore"]:
                raise ServiceError(
                    409,
                    "journal_recovery_review_required",
                    "Resolve conflicting or rejected records before restoring. Nothing changed.",
                )
            self.apply_items(conn, identity, space, key, plan, states, inventory[1])
            audit(
                conn,
                identity,
                "memory.journal_recovered",
                space,
                space_id=space,
                details={
                    "namespace": plan["namespace"],
                    "input_sha256": plan["input_sha256"],
                    "counts": plan["counts"],
                    "source_only": True,
                },
            )
            result = {
                field: plan[field]
                for field in (
                    "identity_mode",
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

    def apply_items(self, conn, identity, space, key, plan, states, latest):
        """Apply a reviewed batch inside its caller-owned policy transaction."""
        # Negative decisions are applied first; all changes still commit together.
        for item in sorted(
            plan["items"],
            key=lambda item: item["action"] not in {"withdraw", "deny", "hold", "quarantine"},
        ):
            memory = UUID(item["memory_id"])
            original = UUID(item["original_id"])
            action = item["action"]
            if action == "withdraw":
                self.memory.forget_in_transaction(
                    conn,
                    identity,
                    memory,
                    expected_version=item["version"],
                    key=f"journal-withdraw:{key}:{memory}",
                )
            elif action == "deny":
                conn.execute(
                    "INSERT INTO mnemion.recovery_denials(tenant_id,space_id,memory_id) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                    (identity.tenant_id, space, memory),
                )
            elif action in {"create", "release", "update", "hold", "quarantine"}:
                entry = latest[original][0]
                local_version = item["version"]
                modified = states[item["original_id"]]["locally_modified"]
                if action in {"create", "release", "update"}:
                    local_version = (local_version or 0) + 1
                    if action != "update":
                        conn.execute(
                            "INSERT INTO mnemion.memories(tenant_id,space_id,id,subject,kind,created_by) VALUES(%s,%s,%s,%s,%s,%s)",
                            (
                                identity.tenant_id,
                                space,
                                memory,
                                entry.subject,
                                entry.kind,
                                identity.principal_id,
                            ),
                        )
                    revision = self.memory._revision(
                        conn,
                        identity,
                        space,
                        memory,
                        local_version,
                        _content(entry),
                    )
                    conn.execute(
                        "UPDATE mnemion.memories SET current_revision_id=%s,version=%s,subject=%s,kind=%s,review_state='ordinary',updated_at=now() WHERE id=%s",
                        (revision, local_version, entry.subject, entry.kind, memory),
                    )
                    self.memory._operation(conn, identity, space, memory, revision, "ingest")
                elif action == "quarantine":
                    from .librarian import purge_librarian_dependencies

                    purge_librarian_dependencies(conn, identity.tenant_id, space, memory)
                    local_version += 1
                    conn.execute(
                        "UPDATE mnemion.memories SET review_state='quarantined',version=%s,updated_at=now() WHERE id=%s",
                        (local_version, memory),
                    )
                conn.execute(
                    """INSERT INTO mnemion.journal_recovery_origins
                       (tenant_id,space_id,origin,memory_id,source_version,source_digest,source_action,local_version,locally_modified)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT(tenant_id,space_id,origin) DO UPDATE SET
                         source_version=excluded.source_version,source_digest=excluded.source_digest,
                         source_action=excluded.source_action,local_version=excluded.local_version,
                         locally_modified=excluded.locally_modified,updated_at=now()""",
                    (
                        identity.tenant_id,
                        space,
                        entry.origin,
                        memory,
                        entry.version,
                        entry.digest,
                        entry.action,
                        local_version,
                        modified,
                    ),
                )
