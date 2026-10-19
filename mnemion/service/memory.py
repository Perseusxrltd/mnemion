"""Canonical writes, revision history, review, and immediate deletion denial."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from .db import Database, Identity, require_space
from .embeddings import Generation
from .errors import ServiceError, not_found
from .models import BlockInput, MemoryInput, RevisionInput, ReviewInput, json_value
from .model_state import enqueue_candidate, settings
from .repository import audit, hydrate, idempotency, memory_row, remember_receipt


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _version(row: dict, expected: int) -> None:
    if row["version"] != expected:
        raise ServiceError(409, "version_conflict", "The record changed; fetch it before retrying.")


class MemoryService:
    def __init__(self, database: Database, generation: Generation):
        self.db = database
        self.generation = generation
        self.writeback = None

    def _revision(
        self,
        conn,
        identity: Identity,
        space: UUID,
        memory: UUID,
        version: int,
        command: MemoryInput,
        *,
        evidence_from: UUID | None = None,
    ) -> UUID:
        source_id, source_revision, revision = uuid4(), uuid4(), uuid4()
        if evidence_from is not None:
            # Reviewed organization changes keep the exact original source and
            # attachments. They cannot manufacture replacement evidence.
            inserted = conn.execute(
                """INSERT INTO mnemion.memory_revisions
                    (tenant_id,space_id,id,memory_id,version,content,content_hash,metadata,subject,kind,
                     source_revision_id,source_start,source_end,claim_status,valid_from,valid_to,created_by,passage_times)
                    SELECT tenant_id,space_id,%s,memory_id,%s,content,content_hash,%s,%s,kind,
                           source_revision_id,source_start,source_end,claim_status,valid_from,valid_to,%s,passage_times
                    FROM mnemion.memory_revisions WHERE tenant_id=%s AND space_id=%s AND memory_id=%s AND id=%s
                    RETURNING id""",
                (
                    revision,
                    version,
                    Jsonb(command.metadata),
                    command.subject,
                    identity.principal_id,
                    identity.tenant_id,
                    space,
                    memory,
                    evidence_from,
                ),
            ).fetchone()
            if not inserted:
                raise not_found()
            return revision
        from .passage_time import capture

        prior = conn.execute(
            """SELECT r.content,r.metadata,r.passage_times,r.recorded_at,now() AS captured_at
               FROM (SELECT 1) seed LEFT JOIN LATERAL (
                 SELECT content,metadata,passage_times,recorded_at
                 FROM mnemion.memory_revisions WHERE tenant_id=%s AND space_id=%s AND memory_id=%s
                 ORDER BY version DESC LIMIT 1
               ) r ON true""",
            (identity.tenant_id, space, memory),
        ).fetchone()
        chronology = capture(command.content, command.metadata, prior["captured_at"], prior)
        source = command.source
        source_content = (
            source.content if source and source.content is not None else command.content
        )
        start = source.start if source else 0
        end = source.end if source and source.end is not None else len(source_content)
        conn.execute(
            """INSERT INTO mnemion.sources(tenant_id, space_id, id, title, uri, created_by)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                identity.tenant_id,
                space,
                source_id,
                source.title if source else "Captured evidence",
                source.uri if source else None,
                identity.principal_id,
            ),
        )
        conn.execute(
            """INSERT INTO mnemion.source_revisions
                 (tenant_id, space_id, id, source_id, content, content_hash, media_type)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                identity.tenant_id,
                space,
                source_revision,
                source_id,
                source_content,
                _hash(source_content),
                source.media_type if source else "text/plain",
            ),
        )
        conn.execute(
            """INSERT INTO mnemion.memory_revisions
                 (tenant_id, space_id, id, memory_id, version, content, content_hash, metadata, subject, kind,
                  source_revision_id, source_start, source_end, claim_status, valid_from, valid_to, created_by, passage_times)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                identity.tenant_id,
                space,
                revision,
                memory,
                version,
                command.content,
                _hash(command.content),
                Jsonb(command.metadata),
                command.subject,
                command.kind,
                source_revision,
                start,
                end,
                command.claim_status,
                command.valid_from,
                command.valid_to,
                identity.principal_id,
                Jsonb(chronology),
            ),
        )
        return revision

    def _operation(
        self, conn, identity: Identity, space: UUID, memory: UUID, revision: UUID | None, kind: str
    ) -> dict:
        model_settings = settings(conn, space, self.generation.id)
        generation = model_settings["active_generation_id"] if kind != "delete" else None
        operation = uuid4()
        conn.execute(
            """INSERT INTO mnemion.operations
                 (tenant_id, space_id, id, memory_id, revision_id, kind, created_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (identity.tenant_id, space, operation, memory, revision, kind, identity.principal_id),
        )
        conn.execute(
            """INSERT INTO mnemion.jobs
                 (tenant_id, space_id, id, operation_id, revision_id, generation_id, kind)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                identity.tenant_id,
                space,
                uuid4(),
                operation,
                revision,
                generation,
                "purge" if kind == "delete" else "embed",
            ),
        )
        if kind != "delete" and model_settings["candidate_run_id"]:
            enqueue_candidate(
                conn,
                tenant=identity.tenant_id,
                space=space,
                memory=memory,
                revision=revision,
                run=model_settings["candidate_run_id"],
                generation=model_settings["candidate_generation_id"],
                created_by=identity.principal_id,
            )
        receipt = {
            "operation_id": operation,
            "memory_id": memory,
            "revision_id": revision,
            "space_id": space,
            "state": "accepted",
            "lexical_ready": kind != "delete",
            "semantic_ready": False,
            "generation_id": generation,
        }
        if self.writeback is not None:
            version = conn.execute(
                "SELECT version FROM mnemion.memories WHERE id=%s", (memory,)
            ).fetchone()["version"]
            journal = self.writeback.capture(
                conn,
                identity,
                space,
                memory,
                revision,
                version,
                operation,
                "forget" if kind == "delete" else "upsert",
            )
            if journal:
                receipt["writeback"] = journal
        return receipt

    def save(self, identity: Identity, space: UUID, command: MemoryInput, key: str) -> dict:
        with self.db.transaction(identity) as conn:
            return self.save_in_transaction(conn, identity, space, command, key)

    def save_in_transaction(
        self, conn, identity: Identity, space: UUID, command: MemoryInput, key: str
    ) -> dict:
        require_space(conn, space, 20, writing=True)
        if command.claim_status != "observed":
            require_space(conn, space, 30)
        digest, previous = idempotency(
            conn, identity, space, key, {"kind": "ingest", **command.model_dump(mode="json")}
        )
        if previous:
            if self.writeback is not None:
                self.writeback.replay(conn, identity, previous)
            return previous
        memory = uuid4()
        conn.execute(
            """INSERT INTO mnemion.memories(tenant_id, space_id, id, subject, kind, created_by)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                identity.tenant_id,
                space,
                memory,
                command.subject,
                command.kind,
                identity.principal_id,
            ),
        )
        revision = self._revision(conn, identity, space, memory, 1, command)
        conn.execute(
            "UPDATE mnemion.memories SET current_revision_id=%s, version=1 WHERE id=%s",
            (revision, memory),
        )
        receipt = self._operation(conn, identity, space, memory, revision, "ingest")
        audit(
            conn,
            identity,
            "memory.created",
            memory,
            space_id=space,
            details={"revision_id": revision},
        )
        return remember_receipt(conn, identity, space, key, digest, {**receipt, "version": 1})

    def fetch(
        self,
        identity: Identity,
        memory: UUID,
        *,
        revision: UUID | None = None,
        review: bool = False,
    ) -> dict:
        with self.db.transaction(identity) as conn:
            from .withdrawal import allowed

            row = memory_row(conn, memory, review=review)
            return {**hydrate(conn, row, revision), "can_forget": allowed(conn, identity, row)}

    def resolve_alias(
        self, identity: Identity, space: UUID, legacy_id: str, *, review: bool = False
    ) -> dict:
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30 if review else 10)
            row = conn.execute(
                "SELECT memory_id FROM mnemion.legacy_aliases WHERE space_id=%s AND legacy_id=%s",
                (space, legacy_id),
            ).fetchone()
            if row:
                identifier = row["memory_id"]
            else:
                try:
                    identifier = UUID(legacy_id)
                except ValueError:
                    raise not_found() from None
            memory = memory_row(conn, identifier, review=review)
            if memory["space_id"] != space:
                raise not_found()
            return hydrate(conn, memory)

    def revise(self, identity: Identity, memory: UUID, command: RevisionInput, key: str) -> dict:
        with self.db.transaction(identity) as conn:
            return self.revise_in_transaction(conn, identity, memory, command, key)

    def revise_in_transaction(
        self,
        conn,
        identity: Identity,
        memory: UUID,
        command: RevisionInput,
        key: str | None,
        *,
        preserve_evidence: bool = False,
    ) -> dict:
        # Check replay before the optimistic version check. The same request
        # remains a successful replay after its first version increment.
        grant = conn.execute(
            "SELECT mnemion.authorized(space_id,30) AS reviewer FROM mnemion.memories WHERE id=%s",
            (memory,),
        ).fetchone()
        review = bool(grant and grant["reviewer"])
        row = memory_row(conn, memory, review=review)
        space = row["space_id"]
        require_space(conn, space, 20, writing=True)
        # An atomic parent operation may own the receipt and its advisory lock.
        # Its nested revision must not allocate a second caller-visible key.
        digest = None
        if key is not None:
            digest, previous = idempotency(
                conn,
                identity,
                space,
                key,
                {
                    "kind": "revise",
                    "memory_id": str(memory),
                    **command.model_dump(mode="json", exclude_unset=True),
                    **({"preserve_evidence": True} if preserve_evidence else {}),
                },
            )
            if previous:
                if self.writeback is not None:
                    self.writeback.replay(conn, identity, previous)
                return previous
        row = memory_row(conn, memory, review=review, lock=True)
        _version(row, command.expected_version)
        current = hydrate(conn, row)
        if preserve_evidence and (
            command.source is not None or command.content != current["content"]
        ):
            raise ValueError("Evidence-preserving organization cannot rewrite memory content")
        # Omitted metadata remains intact. Explicit null/empty values are
        # meaningful changes, and therefore distinct idempotency payloads.
        preserved = {
            field: current[field]
            for field in (
                "subject",
                "kind",
                "metadata",
                "claim_status",
                "valid_from",
                "valid_to",
            )
        }
        command = RevisionInput(
            **{**preserved, **command.model_dump(mode="json", exclude_unset=True)}
        )
        if command.claim_status != "observed" or current["claim_status"] != "observed":
            require_space(conn, space, 30)
        version = row["version"] + 1
        revision = self._revision(
            conn,
            identity,
            space,
            memory,
            version,
            command,
            evidence_from=row["current_revision_id"] if preserve_evidence else None,
        )
        conn.execute(
            """UPDATE mnemion.memories SET current_revision_id=%s, version=%s,
                      subject=%s, kind=%s, updated_at=now() WHERE id=%s""",
            (revision, version, command.subject, command.kind, memory),
        )
        receipt = self._operation(conn, identity, space, memory, revision, "revise")
        audit(
            conn,
            identity,
            "memory.revised",
            memory,
            space_id=space,
            details={
                "revision_id": revision,
                "previous_revision_id": row["current_revision_id"],
                "reason": command.reason,
            },
        )
        response = json_value({**receipt, "version": version})
        if key is None:
            return response
        return remember_receipt(conn, identity, space, key, digest, response)

    def review(self, identity: Identity, memory: UUID, command: ReviewInput) -> dict:
        with self.db.transaction(identity) as conn:
            visible = memory_row(conn, memory, review=True)
            require_space(conn, visible["space_id"], 30, writing=True)
            row = memory_row(conn, memory, review=True, lock=True)
            _version(row, command.expected_version)
            version = row["version"] + 1
            if command.state == "quarantined":
                from .librarian import purge_librarian_dependencies

                purge_librarian_dependencies(conn, identity.tenant_id, row["space_id"], memory)
            conn.execute(
                """UPDATE mnemion.memories SET review_state=%s, version=%s, updated_at=now()
                   WHERE id=%s""",
                (command.state, version, memory),
            )
            audit(
                conn,
                identity,
                "memory.reviewed",
                memory,
                space_id=row["space_id"],
                details={"state": command.state, "reason": command.reason, "version": version},
            )
            if self.writeback is not None:
                self.writeback.capture(
                    conn,
                    identity,
                    row["space_id"],
                    memory,
                    row["current_revision_id"] if command.state == "ordinary" else None,
                    version,
                    uuid4(),
                    "upsert" if command.state == "ordinary" else "quarantine",
                )
            return {"memory_id": str(memory), "version": version, "review_state": command.state}

    def forget(self, identity: Identity, memory: UUID, *, expected_version: int, key: str) -> dict:
        with self.db.transaction(identity) as conn:
            return self.forget_in_transaction(
                conn, identity, memory, expected_version=expected_version, key=key
            )

    def forget_in_transaction(
        self, conn, identity: Identity, memory: UUID, *, expected_version: int, key: str
    ) -> dict:
        from .withdrawal import target

        row = target(conn, identity, memory)
        space = row["space_id"]
        require_space(conn, space, 20, writing=True)
        digest, previous = idempotency(
            conn,
            identity,
            space,
            key,
            {"kind": "delete", "memory_id": str(memory), "expected_version": expected_version},
        )
        # Recheck current authority after idempotency and row-lock waits. A
        # concurrent revision, quarantine or revocation cannot lend permission.
        row = target(conn, identity, memory, lock=True)
        self.db._check_identity(conn, identity)
        if previous:
            if self.writeback is not None:
                self.writeback.replay(conn, identity, previous)
            return previous
        if row["deleted_at"]:
            receipt = conn.execute(
                """SELECT d.operation_id, d.memory_id, d.requested_at, d.purged_at, o.state
                   FROM mnemion.deletion_receipts d JOIN mnemion.operations o
                     ON o.tenant_id=d.tenant_id AND o.space_id=d.space_id AND o.id=d.operation_id
                   WHERE d.memory_id=%s""",
                (memory,),
            ).fetchone()
            return remember_receipt(
                conn,
                identity,
                space,
                key,
                digest,
                {
                    **receipt,
                    "space_id": space,
                    "revision_id": None,
                    "generation_id": None,
                    "version": row["version"],
                    "deleted": True,
                    "lexical_ready": False,
                    "semantic_ready": False,
                },
            )
        _version(row, expected_version)
        from .librarian import purge_librarian_dependencies

        purge_librarian_dependencies(conn, identity.tenant_id, space, memory)
        conn.execute(
            """UPDATE mnemion.memories SET deleted_at=now(), updated_at=now(), version=version+1
               WHERE id=%s""",
            (memory,),
        )
        conn.execute(
            """UPDATE mnemion.jobs j SET state='cancelled', lease_id=NULL, lease_until=NULL
               FROM mnemion.operations o WHERE o.tenant_id=j.tenant_id AND o.space_id=j.space_id
                 AND o.id=j.operation_id AND o.memory_id=%s AND j.state IN ('pending','leased','failed')""",
            (memory,),
        )
        conn.execute(
            """UPDATE mnemion.operations SET state='cancelled', updated_at=now()
               WHERE memory_id=%s AND state IN ('accepted','indexing','failed')""",
            (memory,),
        )
        receipt = self._operation(conn, identity, space, memory, None, "delete")
        conn.execute(
            """INSERT INTO mnemion.recovery_denials (tenant_id, space_id, memory_id)
               VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
            (identity.tenant_id, space, memory),
        )
        conn.execute(
            """INSERT INTO mnemion.deletion_receipts
                 (tenant_id, space_id, memory_id, operation_id, requested_by)
               VALUES (%s, %s, %s, %s, %s)""",
            (identity.tenant_id, space, memory, receipt["operation_id"], identity.principal_id),
        )
        audit(conn, identity, "memory.deleted", memory, space_id=space)
        return remember_receipt(
            conn,
            identity,
            space,
            key,
            digest,
            {**receipt, "deleted": True, "version": row["version"] + 1},
        )

    def operation(self, identity: Identity, operation: UUID) -> dict:
        with self.db.transaction(identity) as conn:
            row = conn.execute(
                """SELECT id AS operation_id, space_id, memory_id, revision_id, kind,
                          state, error_code, created_at, updated_at
                   FROM mnemion.operations o WHERE id=%s AND EXISTS (
                       SELECT FROM mnemion.memories m WHERE m.tenant_id=o.tenant_id
                       AND m.space_id=o.space_id AND m.id=o.memory_id
                       AND (m.review_state='ordinary' OR mnemion.authorized(o.space_id,30)))""",
                (operation,),
            ).fetchone()
            if not row:
                raise not_found()
            return json_value(row)

    def operations(
        self, identity: Identity, space: UUID, *, state: str | None = None, limit: int = 100
    ) -> dict:
        with self.db.transaction(identity) as conn:
            require_space(conn, space)
            rows = conn.execute(
                """SELECT o.id AS operation_id, o.space_id, o.memory_id, o.revision_id, o.kind,
                          o.state, o.error_code, o.created_at, o.updated_at,
                          m.deleted_at IS NOT NULL AS memory_deleted
                   FROM mnemion.operations o JOIN mnemion.memories m
                     ON m.tenant_id=o.tenant_id AND m.space_id=o.space_id AND m.id=o.memory_id
                   WHERE o.space_id=%s AND (%s::text IS NULL OR o.state=%s)
                     AND (m.review_state='ordinary' OR mnemion.authorized(o.space_id,30))
                   ORDER BY o.created_at DESC, o.id DESC LIMIT %s""",
                (space, state, state, limit),
            ).fetchall()
            return {"items": json_value(rows)}

    def retry_operation(self, identity: Identity, operation: UUID) -> dict:
        with self.db.transaction(identity) as conn:
            row = conn.execute(
                "SELECT * FROM mnemion.operations WHERE id=%s FOR UPDATE", (operation,)
            ).fetchone()
            if not row:
                raise not_found()
            require_space(conn, row["space_id"], 30, writing=True)
            if row["state"] != "failed":
                raise ServiceError(
                    409, "operation_not_failed", "Only failed operations can be retried."
                )
            conn.execute(
                """UPDATE mnemion.jobs SET state='pending', attempts=0, available_at=now(), error_code=NULL
                   WHERE operation_id=%s AND state='failed'""",
                (operation,),
            )
            conn.execute(
                "UPDATE mnemion.operations SET state='accepted', error_code=NULL, updated_at=now() WHERE id=%s",
                (operation,),
            )
            audit(conn, identity, "operation.retried", operation, space_id=row["space_id"])
            return {"operation_id": str(operation), "state": "accepted"}

    def source(self, identity: Identity, revision: UUID, *, review: bool = False) -> dict:
        with self.db.transaction(identity) as conn:
            self._source_access(conn, revision, review)
            source = conn.execute(
                """SELECT sr.id AS source_revision_id, sr.source_id, sr.space_id,
                          sr.content, sr.content_hash, sr.media_type, sr.recorded_at, s.title, s.uri
                   FROM mnemion.source_revisions sr JOIN mnemion.sources s
                     ON s.tenant_id=sr.tenant_id AND s.space_id=sr.space_id AND s.id=sr.source_id
                   WHERE sr.id=%s AND s.deleted_at IS NULL""",
                (revision,),
            ).fetchone()
            if not source:
                raise not_found()
            source["attachments"] = conn.execute(
                """SELECT id AS attachment_id,name,media_type,content_hash,
                          octet_length(content) AS size_bytes FROM mnemion.source_attachments
                   WHERE source_revision_id=%s ORDER BY name,id""",
                (revision,),
            ).fetchall()
            return json_value(source)

    @staticmethod
    def _source_access(conn, revision: UUID, review: bool):
        row = conn.execute(
            """SELECT m.id FROM mnemion.memories m JOIN mnemion.memory_revisions r
                 ON r.tenant_id=m.tenant_id AND r.space_id=m.space_id AND r.memory_id=m.id
               WHERE r.source_revision_id=%s AND m.deleted_at IS NULL ORDER BY m.id LIMIT 1""",
            (revision,),
        ).fetchone()
        if not row:
            raise not_found()
        memory_row(conn, row["id"], review=review)

    def attachment(
        self, identity: Identity, revision: UUID, attachment: UUID, *, review: bool = False
    ) -> dict:
        with self.db.transaction(identity) as conn:
            self._source_access(conn, revision, review)
            row = conn.execute(
                "SELECT name,media_type,content,content_hash FROM mnemion.source_attachments WHERE id=%s AND source_revision_id=%s",
                (attachment, revision),
            ).fetchone()
            if not row:
                raise not_found()
            return {**row, "content": bytes(row["content"])}

    def history(self, identity: Identity, memory: UUID, *, review: bool = False) -> list[dict]:
        with self.db.transaction(identity) as conn:
            row = memory_row(conn, memory, review=review)
            ids = conn.execute(
                "SELECT id FROM mnemion.memory_revisions WHERE memory_id=%s ORDER BY version DESC LIMIT 1000",
                (memory,),
            ).fetchall()
            return [hydrate(conn, row, item["id"]) for item in ids]

    def list(
        self,
        identity: Identity,
        space: UUID,
        *,
        limit: int = 50,
        cursor: str | None = None,
        review: bool = False,
    ) -> dict:
        if not 1 <= limit <= 100:
            raise ServiceError(422, "invalid_limit", "Limit must be between 1 and 100.")
        after, snapshot = UUID(int=0), datetime.now(timezone.utc)
        if cursor:
            try:
                if not isinstance(cursor, str) or len(cursor) > 512:
                    raise ValueError()
                data = json.loads(
                    base64.b64decode(cursor.encode("ascii"), altchars=b"-_", validate=True)
                )
                if (
                    not isinstance(data, dict)
                    or set(data) != {"after", "snapshot", "space"}
                    or any(not isinstance(value, str) for value in data.values())
                ):
                    raise ValueError()
                after, snapshot = UUID(data["after"]), datetime.fromisoformat(data["snapshot"])
                if data["space"] != str(space) or snapshot.tzinfo is None:
                    raise ValueError()
            except (ValueError, KeyError, TypeError, UnicodeError):
                raise ServiceError(
                    422, "invalid_cursor", "The pagination cursor is invalid."
                ) from None
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30 if review else 10)
            rows = conn.execute(
                """SELECT * FROM mnemion.memories WHERE space_id=%s AND id>%s AND created_at<=%s
                   AND deleted_at IS NULL AND (review_state='ordinary' OR %s)
                   ORDER BY id LIMIT %s""",
                (space, after, snapshot, review, limit + 1),
            ).fetchall()
            next_cursor = None
            if len(rows) > limit:
                next_cursor = base64.urlsafe_b64encode(
                    json.dumps(
                        {
                            "space": str(space),
                            "after": str(rows[limit - 1]["id"]),
                            "snapshot": snapshot.isoformat(),
                        }
                    ).encode()
                ).decode()
            return {
                "items": [hydrate(conn, row) for row in rows[:limit]],
                "next_cursor": next_cursor,
            }

    def blocks(self, identity: Identity, space: UUID) -> list[dict]:
        with self.db.transaction(identity) as conn:
            require_space(conn, space)
            return json_value(
                conn.execute(
                    "SELECT key, content, version, updated_at, updated_by FROM mnemion.core_blocks WHERE space_id=%s ORDER BY key LIMIT 100",
                    (space,),
                ).fetchall()
            )

    def put_block(self, identity: Identity, space: UUID, key: str, command: BlockInput) -> dict:
        if not 1 <= len(key) <= 100 or not all(c.isalnum() or c in "_-" for c in key):
            raise ServiceError(422, "invalid_block_key", "Use a short alphanumeric block key.")
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30, writing=True)
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"block:{identity.tenant_id}:{space}:{key}",),
            )
            old = conn.execute(
                "SELECT version FROM mnemion.core_blocks WHERE space_id=%s AND key=%s", (space, key)
            ).fetchone()
            if (old["version"] if old else 0) != command.expected_version:
                raise ServiceError(
                    409, "version_conflict", "The block changed; fetch it before retrying."
                )
            version = command.expected_version + 1
            conn.execute(
                """INSERT INTO mnemion.core_blocks(tenant_id, space_id, key, content, version, updated_by)
                   VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (tenant_id, space_id, key)
                   DO UPDATE SET content=excluded.content, version=excluded.version,
                                 updated_by=excluded.updated_by, updated_at=now()""",
                (identity.tenant_id, space, key, command.content, version, identity.principal_id),
            )
            conn.execute(
                """INSERT INTO mnemion.core_block_revisions
                     (tenant_id, space_id, key, content, version, created_by) VALUES (%s, %s, %s, %s, %s, %s)""",
                (identity.tenant_id, space, key, command.content, version, identity.principal_id),
            )
            audit(
                conn, identity, "block.updated", key, space_id=space, details={"version": version}
            )
            return {
                "space_id": str(space),
                "key": key,
                "content": command.content,
                "version": version,
            }

    def status(self, identity: Identity, space: UUID) -> dict:
        with self.db.transaction(identity) as conn:
            require_space(conn, space)
            counts = conn.execute(
                """SELECT count(*) AS memories FROM mnemion.memories
                   WHERE space_id=%s AND deleted_at IS NULL AND review_state='ordinary'""",
                (space,),
            ).fetchone()
            queue = conn.execute(
                """SELECT o.state, count(*) AS count, min(o.created_at) AS oldest
                   FROM mnemion.operations o JOIN mnemion.memories m
                     ON m.tenant_id=o.tenant_id AND m.space_id=o.space_id AND m.id=o.memory_id
                   WHERE o.space_id=%s AND (m.review_state='ordinary' OR mnemion.authorized(o.space_id,30))
                   GROUP BY o.state ORDER BY o.state""",
                (space,),
            ).fetchall()
            return json_value(
                {
                    "space_id": space,
                    **counts,
                    "operations": queue,
                    "generation_id": settings(conn, space, self.generation.id)[
                        "active_generation_id"
                    ],
                }
            )

    def activity(
        self, identity: Identity, space: UUID, *, limit: int = 100, memory: UUID | None = None
    ) -> dict:
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            rows = conn.execute(
                """SELECT a.id,a.space_id,a.principal_id,a.action,a.resource_id,a.details,a.created_at,n.reason
                   FROM mnemion.audit_events a LEFT JOIN mnemion.memory_change_notes n
                     ON n.tenant_id=a.tenant_id AND n.event_id=a.id
                   WHERE a.space_id=%s AND (%s::text IS NULL OR a.resource_id=%s)
                   ORDER BY a.created_at DESC,a.id DESC LIMIT %s""",
                (space, str(memory) if memory else None, str(memory) if memory else None, limit),
            ).fetchall()
            return {"items": json_value(rows)}
