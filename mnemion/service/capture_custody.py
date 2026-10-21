"""Server-consented custody and immutable, permission-scoped event receipts."""

import hashlib
import re
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from ..capture_identity import canonical_capture_json, capture_event_id, capture_lineage_id
from ..capture_policy import CapturePolicy
from .db import require_administrator, require_space
from .errors import ServiceError, not_found
from .models import json_value
from .repository import audit
from .capture_progress import CaptureProgress


def source_lock(conn, source_id):
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"capture:{source_id}",))


def members_lock(conn, identity, connector_id):
    conn.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
        (f"capture-members:{identity.tenant_id}:{connector_id}",),
    )


def lock_memory_lineage(conn, memory_id):
    """Order capture ingestion and canonical forgetting before memory row locks."""
    row = conn.execute(
        "SELECT source_id FROM mnemion.capture_events WHERE memory_id=%s", (memory_id,)
    ).fetchone()
    if row:
        source_lock(conn, row["source_id"])


def selected_item(item, capture_mode, producer_scope, namespace, capture_policy=None):
    """Require actual selected-fragment provenance; never accept raw message mode."""
    data = item.model_dump(mode="json")
    metadata = data["memory"]["metadata"]
    generation = metadata.get("source_generation")
    start, end, part = (
        metadata.get("source_byte_start"),
        metadata.get("source_byte_end"),
        metadata.get("part"),
    )
    original = metadata.get("source_external_id")
    revision = metadata.get("source_revision")
    path = metadata.get("path")
    valid = (
        metadata.get("capture") == "mnemion-live-jsonl-v1"
        and metadata.get("source_fragment") is True
        and isinstance(generation, str)
        and re.fullmatch(r"[a-f0-9]{32}", generation)
        and type(start) is int
        and type(end) is int
        and 0 <= start < end <= 1_000_000_000_000
        and type(part) is int
        and 0 <= part <= 999999
        and isinstance(original, str)
        and original.startswith(f"{producer_scope}:{generation}:bytes:{start}")
        and isinstance(revision, str)
        and re.fullmatch(r"[a-f0-9]{64}", revision)
        and isinstance(path, str)
        and 1 <= len(path) <= 4096
        and producer_scope
        == "conversation:" + hashlib.sha256((namespace + "\0" + path).encode()).hexdigest()
        and data["memory"]["source"] is not None
        and data["memory"]["source"]["content"] == data["memory"]["content"]
    )
    if valid:
        base = f"{producer_scope}:{generation}:bytes:{start}"
        valid = original == base or original.startswith(base + "#conversation:")
        valid = (
            valid
            and item.external_id
            == (hashlib.sha256(original.encode()).hexdigest() + f":part:{part:06d}")
            and item.revision
            == hashlib.sha256((revision + ":mnemion-text-v1").encode()).hexdigest()
        )
    if capture_mode == "messages":
        valid = valid and (
            metadata.get("capture_mode") == "messages"
            and metadata.get("raw_evidence_stored") is False
            and metadata.get("projection") == "mnemion-conversation-v1"
            and "#conversation:" in (original or "")
            and "raw_source_external_id" not in metadata
            and "raw_document_sha256" not in metadata
        )
    if capture_policy is not None:
        policy = CapturePolicy.model_validate(capture_policy)
        valid = valid and (
            policy.capture_mode == capture_mode
            and policy.allows_path(path)
            and metadata.get("capture_policy_revision") == policy.revision
            and end <= policy.max_file_bytes
        )
    elif "capture_policy_revision" in metadata:
        valid = False
    if not valid:
        raise ServiceError(
            422, "capture_selection_invalid", "Send only the source's approved selected evidence."
        )
    return data


class CaptureCustody(CaptureProgress):
    def __init__(self, memory):
        self.memory, self.db = memory, memory.db

    @staticmethod
    def _source_value(conn, row):
        history = conn.execute(
            "SELECT mnemion.capture_source_has_history(%s) AS present", (row["source_id"],)
        ).fetchone()["present"]
        return {**json_value(row), "has_capture_history": history}

    def source_status(self, identity, connector_id, source_id):
        with self.db.transaction(identity) as conn:
            row = conn.execute(
                "SELECT * FROM mnemion.capture_sources WHERE source_id=%s AND connector_id=%s",
                (source_id, connector_id),
            ).fetchone()
            if not row:
                raise not_found()
            return self._source_value(conn, row)

    def source(self, identity, connector_id, source_id, command):
        with self.db.transaction(identity) as conn:
            require_administrator(conn)
            members_lock(conn, identity, connector_id)
            source_lock(conn, source_id)
            self.db._check_identity(conn, identity)
            connector = conn.execute(
                "SELECT * FROM mnemion.connectors WHERE id=%s AND disabled_at IS NULL",
                (connector_id,),
            ).fetchone()
            if (
                not connector
                or connector["provider"] != "conversations"
                or connector["access_mode"] != "published"
            ):
                raise ServiceError(
                    422, "capture_connector_required", "Choose a published conversation connector."
                )
            row = conn.execute(
                "SELECT * FROM mnemion.capture_sources WHERE source_id=%s", (source_id,)
            ).fetchone()
            if row:
                if (
                    row["connector_id"] != connector_id
                    or row["namespace"] != command.namespace
                    or row["capture_mode"] != command.capture_mode
                    or row["capture_policy"]
                    != (
                        command.capture_policy.model_dump(mode="json")
                        if command.capture_policy
                        else None
                    )
                    or row["revoked_at"]
                ):
                    raise ServiceError(
                        409,
                        "capture_policy_immutable",
                        "A retired or different capture policy needs reviewed migration.",
                    )
                if row["name"] == command.name and set(row["members"]) == set(command.members):
                    return self._source_value(conn, row)
                if command.expected_version != row["version"]:
                    raise ServiceError(
                        409, "version_conflict", "Capture custody changed; reload before saving."
                    )
                row = conn.execute(
                    "UPDATE mnemion.capture_sources SET name=%s,members=%s,version=version+1 WHERE source_id=%s RETURNING *",
                    (command.name, command.members, source_id),
                ).fetchone()
                conn.execute(
                    "UPDATE mnemion.spaces SET name=%s WHERE id=%s", (command.name, row["space_id"])
                )
            else:
                if command.expected_version != 0:
                    raise ServiceError(
                        409, "version_conflict", "Capture custody does not exist at that version."
                    )
                space = uuid4()
                conn.execute(
                    "INSERT INTO mnemion.spaces(tenant_id,id,name,description) VALUES(%s,%s,%s,'Consented durable conversation custody')",
                    (identity.tenant_id, space, command.name),
                )
                row = conn.execute(
                    """INSERT INTO mnemion.capture_sources(tenant_id,source_id,connector_id,space_id,namespace,name,members,capture_mode,capture_policy)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                    (
                        identity.tenant_id,
                        source_id,
                        connector_id,
                        space,
                        command.namespace,
                        command.name,
                        command.members,
                        command.capture_mode,
                        Jsonb(command.capture_policy.model_dump(mode="json"))
                        if command.capture_policy
                        else None,
                    ),
                ).fetchone()
            audit(
                conn,
                identity,
                "capture.custody_configured",
                source_id,
                details={"connector_id": connector_id, "capture_mode": command.capture_mode},
            )
            return self._source_value(conn, row)

    def revoke_source(self, identity, connector_id, source_id):
        with self.db.transaction(identity) as conn:
            require_administrator(conn)
            source_lock(conn, source_id)
            self.db._check_identity(conn, identity)
            row = conn.execute(
                "UPDATE mnemion.capture_sources SET version=version+CASE WHEN revoked_at IS NULL THEN 1 ELSE 0 END,revoked_at=coalesce(revoked_at,now()) WHERE source_id=%s AND connector_id=%s RETURNING *",
                (source_id, connector_id),
            ).fetchone()
            if not row:
                raise not_found()
            audit(conn, identity, "capture.custody_revoked", source_id)
            return self._source_value(conn, row)

    def grant(self, identity, source_id, grant_id, command):
        with self.db.transaction(identity) as conn:
            require_administrator(conn)
            source_lock(conn, source_id)
            self.db._check_identity(conn, identity)
            source = conn.execute(
                "SELECT * FROM mnemion.capture_sources WHERE source_id=%s AND revoked_at IS NULL",
                (source_id,),
            ).fetchone()
            if not source:
                raise not_found()
            key = conn.execute(
                """SELECT k.id FROM mnemion.api_keys k JOIN mnemion.connectors c
                     ON c.tenant_id=k.tenant_id AND c.principal_id=k.principal_id
                   WHERE k.id=%s AND c.id=%s AND c.disabled_at IS NULL AND k.revoked_at IS NULL
                     AND (k.expires_at IS NULL OR k.expires_at>clock_timestamp())""",
                (command.device_key_id, source["connector_id"]),
            ).fetchone()
            if not key:
                raise ServiceError(
                    422, "capture_device_key", "Choose this connector's current dedicated API key."
                )
            before = conn.execute(
                "SELECT * FROM mnemion.capture_grants WHERE grant_id=%s", (grant_id,)
            ).fetchone()
            if before and (
                before["source_id"] != source_id
                or before["device_key_id"] != command.device_key_id
                or before["revoked_at"]
            ):
                raise ServiceError(
                    409,
                    "capture_grant_immutable",
                    "Use a new grant for a different or revoked device authorization.",
                )
            conn.execute(
                "INSERT INTO mnemion.capture_grants(tenant_id,grant_id,source_id,device_key_id) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (identity.tenant_id, grant_id, source_id, command.device_key_id),
            )
            audit(
                conn,
                identity,
                "capture.device_authorized",
                grant_id,
                details={"source_id": source_id, "device_key_id": command.device_key_id},
            )
            return self._grant(conn, identity, grant_id, active=False)

    def _grant(self, conn, identity, grant_id, *, active=True):
        row = conn.execute(
            """SELECT g.*,s.connector_id,s.space_id,s.namespace,s.capture_mode,s.capture_policy,s.revoked_at AS source_revoked_at,
                      c.disabled_at AS connector_disabled,k.revoked_at AS key_revoked,
                      k.expires_at AS key_expires,p.disabled_at AS principal_disabled,p.administrator,
                      mnemion.administrator() AS caller_admin,
                      (k.expires_at IS NULL OR k.expires_at>clock_timestamp()) AS key_current
               FROM mnemion.capture_grants g JOIN mnemion.capture_sources s USING(tenant_id,source_id)
                 JOIN mnemion.connectors c ON c.tenant_id=s.tenant_id AND c.id=s.connector_id
                 JOIN mnemion.api_keys k ON k.tenant_id=g.tenant_id AND k.id=g.device_key_id
                 JOIN mnemion.principals p ON p.tenant_id=c.tenant_id AND p.id=c.principal_id
               WHERE g.grant_id=%s""",
            (grant_id,),
        ).fetchone()
        if not row or (not row["caller_admin"] and row["device_key_id"] != identity.key_id):
            raise not_found()
        row["active"] = (
            not any(
                row[k]
                for k in (
                    "revoked_at",
                    "source_revoked_at",
                    "connector_disabled",
                    "key_revoked",
                    "principal_disabled",
                    "administrator",
                )
            )
            and row["key_current"]
        )
        if active and (not row["active"] or row["device_key_id"] != identity.key_id):
            raise ServiceError(
                403, "capture_grant_inactive", "This device no longer has active capture custody."
            )
        return json_value(row)

    def status(self, identity, grant_id, *, revoke=False):
        with self.db.transaction(identity) as conn:
            row = self._grant(conn, identity, grant_id, active=False)
            source_lock(conn, row["source_id"])
            self.db._check_identity(conn, identity)
            if revoke:
                conn.execute(
                    "SELECT mnemion.revoke_capture_grant(%s,%s)", (grant_id, identity.key_id)
                )
                audit(conn, identity, "capture.device_revoked", grant_id)
            return self._grant(conn, identity, grant_id, active=False)

    def _receipt(self, conn, grant, page_id, ids):
        rows = conn.execute(
            """SELECT e.event_id,e.lineage_id,e.memory_id,e.operation_id,
                      m.deleted_at IS NOT NULL OR e.memory_id IS NULL AS forgotten
               FROM mnemion.capture_events e
                 LEFT JOIN mnemion.memories m ON m.tenant_id=e.tenant_id AND m.space_id=e.space_id AND m.id=e.memory_id
               WHERE e.source_id=%s AND e.event_id=ANY(%s)""",
            (UUID(grant["source_id"]), ids),
        ).fetchall()
        by_id = {row["event_id"]: row for row in rows}
        if len(by_id) != len(ids):
            raise ServiceError(
                409,
                "capture_receipt_unavailable",
                "The stored event receipt needs recovery reconciliation.",
            )
        items = []
        for identifier in ids:
            row = by_id[identifier]
            items.append(
                {
                    "event_id": identifier,
                    "lineage_id": row["lineage_id"],
                    "memory_id": None if row["forgotten"] else row["memory_id"],
                    "operation_id": None if row["forgotten"] else row["operation_id"],
                    "outcome": "forgotten" if row["forgotten"] else "stored",
                }
            )
        return json_value(
            {
                "page_id": page_id,
                "grant_id": grant["grant_id"],
                "source_id": grant["source_id"],
                "durable": True,
                "items": items,
            }
        )

    def page(self, identity, grant_id, command=None, *, page_id=None):
        with self.db.transaction(identity) as conn:
            grant = self._grant(conn, identity, grant_id)
            source_lock(conn, grant["source_id"])
            conn.execute(
                "SELECT mnemion.lock_capture_authority(%s,%s)", (grant_id, identity.key_id)
            )
            self.db._check_identity(conn, identity)
            grant = self._grant(conn, identity, grant_id)
            require_space(conn, UUID(grant["space_id"]), 20, writing=command is not None)
            page_id = command.page_id if command is not None else page_id
            old = conn.execute(
                "SELECT * FROM mnemion.capture_pages WHERE grant_id=%s AND page_id=%s",
                (grant_id, page_id),
            ).fetchone()
            if command is None:
                if not old:
                    raise not_found()
                return self._receipt(conn, grant, page_id, old["event_ids"])
            digest = hashlib.sha256(
                canonical_capture_json(command.model_dump(mode="json"))
            ).hexdigest()
            if old:
                if old["request_hash"] != digest:
                    raise ServiceError(
                        409,
                        "capture_page_conflict",
                        "A capture page ID must identify immutable bytes.",
                    )
                return self._receipt(conn, grant, page_id, old["event_ids"])
            source_id, space_id = UUID(grant["source_id"]), UUID(grant["space_id"])
            ids = []
            for event in command.events:
                data = selected_item(
                    event.item,
                    grant["capture_mode"],
                    event.producer_scope,
                    grant["namespace"],
                    grant["capture_policy"],
                )
                if capture_event_id(source_id, event.producer_scope, data) != event.event_id:
                    raise ServiceError(
                        422,
                        "capture_event_identity",
                        "The capture event does not match its selected evidence.",
                    )
                lineage = capture_lineage_id(event.producer_scope, data)
                payload_hash = hashlib.sha256(canonical_capture_json(data)).hexdigest()
                previous = conn.execute(
                    "SELECT * FROM mnemion.capture_events WHERE source_id=%s AND producer_scope=%s AND origin_external_id=%s AND origin_revision=%s",
                    (source_id, event.producer_scope, event.item.external_id, event.item.revision),
                ).fetchone()
                if previous:
                    if (
                        previous["payload_hash"] != payload_hash
                        or previous["event_id"] != event.event_id
                    ):
                        raise ServiceError(
                            409,
                            "capture_revision_conflict",
                            "An origin revision must identify immutable evidence.",
                        )
                    ids.append(event.event_id)
                    continue
                denied = conn.execute(
                    "SELECT 1 FROM mnemion.capture_denials WHERE source_id=%s AND lineage_id=%s",
                    (source_id, lineage),
                ).fetchone()
                receipt = (
                    {}
                    if denied
                    else self.memory.save_in_transaction(
                        conn, identity, space_id, event.item.memory, "capture:" + event.event_id
                    )
                )
                conn.execute(
                    """INSERT INTO mnemion.capture_events(tenant_id,source_id,event_id,producer_scope,origin_external_id,origin_revision,lineage_id,payload_hash,space_id,memory_id,operation_id)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        identity.tenant_id,
                        source_id,
                        event.event_id,
                        event.producer_scope,
                        event.item.external_id,
                        event.item.revision,
                        lineage,
                        payload_hash,
                        space_id,
                        receipt.get("memory_id"),
                        receipt.get("operation_id"),
                    ),
                )
                ids.append(event.event_id)
            conn.execute(
                "INSERT INTO mnemion.capture_pages(tenant_id,grant_id,page_id,request_hash,event_ids) VALUES(%s,%s,%s,%s,%s)",
                (identity.tenant_id, grant_id, page_id, digest, ids),
            )
            audit(
                conn,
                identity,
                "capture.page_committed",
                page_id,
                space_id=space_id,
                details={"source_id": source_id, "grant_id": grant_id, "events": len(ids)},
            )
            return self._receipt(conn, grant, page_id, ids)

    def fences(self, identity, grant_id, *, after=None, limit=100):
        with self.db.transaction(identity) as conn:
            grant = self._grant(conn, identity, grant_id)
            source_lock(conn, grant["source_id"])
            conn.execute(
                "SELECT mnemion.lock_capture_authority(%s,%s)", (grant_id, identity.key_id)
            )
            self.db._check_identity(conn, identity)
            grant = self._grant(conn, identity, grant_id)
            rows = conn.execute(
                "SELECT lineage_id,forgotten_at FROM mnemion.capture_denials WHERE source_id=%s AND (%s::text IS NULL OR lineage_id>%s) ORDER BY lineage_id LIMIT %s",
                (UUID(grant["source_id"]), after, after, limit + 1),
            ).fetchall()
            return json_value(
                {
                    "items": rows[:limit],
                    "next_cursor": rows[limit - 1]["lineage_id"] if len(rows) > limit else None,
                }
            )
