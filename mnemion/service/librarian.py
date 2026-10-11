"""Scoped librarian settings, durable jobs and versioned human decisions."""

from __future__ import annotations

from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from .db import Database, Identity, require_space
from .errors import ServiceError, not_found
from .evaluations import history_cursor, history_page
from .librarian_models import (
    PIPELINE_VERSION,
    LibrarianDecision,
    LibrarianRun,
    LibrarianRunInput,
    LibrarianSettingsInput,
    LibrarianSuggestion,
)
from .librarian_provider import LibrarianRegistry
from .memory import MemoryService
from .models import RevisionInput, json_value
from .repository import audit, idempotency, memory_row, remember_receipt

RUN_COLUMNS = ",".join(LibrarianRun.model_fields)


def reference_rows(conn, space, proposal):
    return conn.execute(
        """SELECT d.*,m.id AS available_memory,m.deleted_at,m.review_state,
            m.version AS current_version,m.current_revision_id,
            r.id AS available_revision,r.subject,r.metadata,
            s.id AS available_source,s.deleted_at AS source_deleted_at
            FROM mnemion.librarian_dependencies d
            LEFT JOIN mnemion.memories m ON m.tenant_id=d.tenant_id AND m.space_id=d.space_id AND m.id=d.memory_id
            LEFT JOIN mnemion.memory_revisions r ON r.tenant_id=d.tenant_id AND r.space_id=d.space_id AND r.id=d.revision_id
            LEFT JOIN mnemion.source_revisions sr ON sr.tenant_id=r.tenant_id AND sr.space_id=r.space_id AND sr.id=r.source_revision_id
            LEFT JOIN mnemion.sources s ON s.tenant_id=sr.tenant_id AND s.space_id=sr.space_id AND s.id=sr.source_id
            WHERE d.space_id=%s AND d.proposal_id=%s ORDER BY d.memory_id""",
        (space, proposal),
    ).fetchall()


def references_available(rows):
    return bool(rows) and all(
        r["available_memory"]
        and not r["deleted_at"]
        and r["review_state"] == "ordinary"
        and r["available_revision"]
        and r["available_source"]
        and not r["source_deleted_at"]
        for r in rows
    )


def purge_librarian_dependencies(conn, tenant, space, memory):
    affected = conn.execute(
        "SELECT proposal_id FROM mnemion.librarian_dependencies WHERE tenant_id=%s AND space_id=%s AND memory_id=%s",
        (tenant, space, memory),
    ).fetchall()
    for row in affected:
        scope = tenant, space, row["proposal_id"]
        conn.execute(
            """UPDATE mnemion.librarian_proposals SET state='invalidated',suggestion=NULL,
                version=version+1,previous_revision_id=NULL,applied_revision_id=NULL,applied_version=NULL
                WHERE tenant_id=%s AND space_id=%s AND id=%s""",
            scope,
        )
        conn.execute(
            "DELETE FROM mnemion.librarian_dependencies WHERE tenant_id=%s AND space_id=%s AND proposal_id=%s",
            scope,
        )
    conn.execute(
        "DELETE FROM mnemion.librarian_observations WHERE tenant_id=%s AND space_id=%s AND memory_id=%s",
        (tenant, space, memory),
    )


class LibrarianService:
    def __init__(self, database: Database, registry: LibrarianRegistry, memory: MemoryService):
        self.db, self.registry, self.memory = database, registry, memory

    def choices(self, identity, space):
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            return {"items": [p.profile.describe() for p in self.registry.providers.values()]}

    def _settings(self, conn, space, *, lock=False):
        return conn.execute(
            "SELECT * FROM mnemion.librarian_settings WHERE space_id=%s"
            + (" FOR UPDATE" if lock else ""),
            (space,),
        ).fetchone()

    def _settings_output(self, conn, space, row):
        budget = conn.execute(
            "SELECT calls_reserved FROM mnemion.librarian_budgets WHERE space_id=%s AND day=(now() AT TIME ZONE 'UTC')::date",
            (space,),
        ).fetchone()
        pending = conn.execute(
            "SELECT count(*) AS n FROM mnemion.librarian_proposals WHERE space_id=%s AND state='pending'",
            (space,),
        ).fetchone()["n"]
        fields = (
            "version",
            "profile_id",
            "profile_fingerprint",
            "enabled",
            "network_egress_approved",
            "mode",
            "max_memories",
            "max_calls_per_day",
            "interval_minutes",
            "next_run_at",
            "updated_at",
        )
        result = (
            {name: row[name] for name in fields}
            if row
            else {
                "version": 0,
                "profile_id": None,
                "profile_fingerprint": None,
                "enabled": False,
                "network_egress_approved": False,
                "mode": "organize",
                "max_memories": 4,
                "max_calls_per_day": 24,
                "interval_minutes": None,
                "next_run_at": None,
                "updated_at": None,
            }
        )
        result.update(
            space_id=space,
            calls_reserved_today=budget["calls_reserved"] if budget else 0,
            pending_proposals=pending,
            profile_available=bool(
                row and row["profile_fingerprint"] in self.registry.fingerprints
            ),
        )
        return json_value(result)

    def settings(self, identity, space):
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            return self._settings_output(conn, space, self._settings(conn, space))

    def configure(self, identity: Identity, space: UUID, command: LibrarianSettingsInput):
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 40, writing=True)
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                ("librarian-settings:" + str(space),),
            )
            row = self._settings(conn, space, lock=True)
            if command.expected_version != (row["version"] if row else 0):
                raise ServiceError(
                    409, "version_conflict", "Librarian settings changed; reload before saving."
                )
            provider = self.registry.providers.get(command.profile_id)
            # A removed/broken provider must never prevent stopping its schedule.
            if command.enabled:
                provider = self.registry.get(command.profile_id)
                if provider.profile.network_egress and not command.approve_network_egress:
                    raise ServiceError(
                        422,
                        "network_approval_required",
                        "Approve this space's outbound model processing.",
                    )
            elif not provider and (not row or command.profile_id != row["profile_id"]):
                raise ServiceError(
                    409, "librarian_profile_unavailable", "Select a configured profile."
                )
            fingerprint = provider.profile.fingerprint if provider else row["profile_fingerprint"]
            conn.execute(
                """INSERT INTO mnemion.librarian_settings
                (tenant_id,space_id,version,profile_id,profile_fingerprint,enabled,network_egress_approved,
                 mode,max_memories,max_calls_per_day,interval_minutes,next_run_at,created_by,key_id)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    CASE WHEN %s AND %s::integer IS NOT NULL THEN now()+interval '1 minute'*%s ELSE NULL END,%s,%s)
                ON CONFLICT(tenant_id,space_id) DO UPDATE SET version=excluded.version,
                    profile_id=excluded.profile_id,profile_fingerprint=excluded.profile_fingerprint,
                    enabled=excluded.enabled,network_egress_approved=excluded.network_egress_approved,
                    mode=excluded.mode,max_memories=excluded.max_memories,max_calls_per_day=excluded.max_calls_per_day,
                    interval_minutes=excluded.interval_minutes,next_run_at=excluded.next_run_at,
                    created_by=excluded.created_by,key_id=excluded.key_id,updated_at=now()""",
                (
                    identity.tenant_id,
                    space,
                    command.expected_version + 1,
                    command.profile_id,
                    fingerprint,
                    command.enabled,
                    command.enabled and command.approve_network_egress,
                    command.mode,
                    command.max_memories,
                    command.max_calls_per_day,
                    command.interval_minutes,
                    command.enabled,
                    command.interval_minutes,
                    command.interval_minutes,
                    identity.principal_id,
                    identity.key_id,
                ),
            )
            conn.execute(
                """UPDATE mnemion.librarian_runs SET state='cancelled',error_code='configuration_changed',
                    finished_at=now()
                    WHERE space_id=%s AND state IN ('queued','running')""",
                (space,),
            )
            conn.execute(
                "DELETE FROM mnemion.librarian_observations WHERE space_id=%s AND outcome='skipped'",
                (space,),
            )
            audit(
                conn,
                identity,
                "librarian.configured",
                space,
                space_id=space,
                details={
                    "version": command.expected_version + 1,
                    "enabled": command.enabled,
                    "profile_fingerprint": fingerprint,
                },
            )
            return self._settings_output(conn, space, self._settings(conn, space))

    def _active_settings(self, conn, space, *, lock=False):
        row = self._settings(conn, space, lock=lock)
        if not row or not row["enabled"]:
            raise ServiceError(
                409, "librarian_disabled", "A space administrator must enable the librarian first."
            )
        profile = self.registry.get(row["profile_id"]).profile
        if profile.fingerprint != row["profile_fingerprint"]:
            raise ServiceError(
                409,
                "configuration_changed",
                "Review and save the changed model configuration before running it.",
            )
        if profile.network_egress and not row["network_egress_approved"]:
            raise ServiceError(
                409, "configuration_changed", "Outbound model processing needs renewed approval."
            )
        return row

    def create_run(self, identity: Identity, space: UUID, command: LibrarianRunInput, key: str):
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30, writing=True)
            digest, previous = idempotency(
                conn,
                identity,
                space,
                key,
                {"kind": "librarian-run", **command.model_dump(mode="json")},
            )
            if previous:
                return self._run(conn, space, UUID(previous["run_id"]))
            conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                ("librarian-settings:" + str(space),),
            )
            settings = self._active_settings(conn, space)
            if len(command.memory_ids) > settings["max_memories"]:
                raise ServiceError(
                    422, "librarian_batch_limit", "The selection exceeds this space's memory limit."
                )
            if conn.execute(
                "SELECT id FROM mnemion.librarian_runs WHERE space_id=%s AND state IN ('queued','running')",
                (space,),
            ).fetchone():
                raise ServiceError(
                    409,
                    "librarian_active",
                    "A librarian run is already queued or running for this space.",
                )
            if self._settings_output(conn, space, settings)["pending_proposals"] > 188:
                raise ServiceError(
                    409,
                    "librarian_review_backlog",
                    "Review existing proposals before creating more.",
                )
            if command.memory_ids:
                records = [
                    memory_row(conn, identifier) for identifier in sorted(command.memory_ids)
                ]
                if any(record["space_id"] != space for record in records):
                    raise not_found()
            else:
                records = conn.execute(
                    """SELECT m.* FROM mnemion.memories m
                    WHERE m.space_id=%s AND m.deleted_at IS NULL AND m.review_state='ordinary'
                      AND NOT EXISTS(SELECT FROM mnemion.librarian_observations o
                        WHERE o.tenant_id=m.tenant_id AND o.space_id=m.space_id AND o.memory_id=m.id
                          AND o.profile_fingerprint=%s AND o.mode=%s AND o.memory_version=m.version)
                    ORDER BY m.updated_at,m.id LIMIT %s""",
                    (
                        space,
                        settings["profile_fingerprint"],
                        command.mode,
                        settings["max_memories"],
                    ),
                ).fetchall()
            run = uuid4()
            profile = self.registry.get(settings["profile_id"]).profile
            config = {
                **profile.describe(),
                "pipeline": PIPELINE_VERSION,
                "max_memories": settings["max_memories"],
                "max_calls_per_day": settings["max_calls_per_day"],
                "max_seconds": 600,
                "human_review_required": True,
                "automatic_provider_retries": False,
            }
            conn.execute(
                """INSERT INTO mnemion.librarian_runs
                    (tenant_id,space_id,id,profile_id,profile_fingerprint,settings_version,mode,configuration,
                     selected,created_by,key_id,state,finished_at)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s=0 THEN now() ELSE NULL END)""",
                (
                    identity.tenant_id,
                    space,
                    run,
                    profile.id,
                    profile.fingerprint,
                    settings["version"],
                    command.mode,
                    Jsonb(config),
                    len(records),
                    identity.principal_id,
                    identity.key_id,
                    "queued" if records else "completed",
                    len(records),
                ),
            )
            for position, record in enumerate(records):
                conn.execute(
                    """INSERT INTO mnemion.librarian_items
                        (tenant_id,space_id,run_id,position,memory_id,revision_id,memory_version)
                        VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        identity.tenant_id,
                        space,
                        run,
                        position,
                        record["id"],
                        record["current_revision_id"],
                        record["version"],
                    ),
                )
            remember_receipt(conn, identity, space, key, digest, {"run_id": str(run)})
            audit(
                conn,
                identity,
                "librarian.queued",
                run,
                space_id=space,
                details={"selected": len(records), "mode": command.mode},
            )
            return self._run(conn, space, run)

    @staticmethod
    def _run(conn, space, run):
        row = conn.execute(
            f"SELECT {RUN_COLUMNS} FROM mnemion.librarian_runs WHERE space_id=%s AND id=%s",
            (space, run),
        ).fetchone()
        if not row:
            raise not_found()
        return json_value(row)

    def run(self, identity, space, run):
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            return self._run(conn, space, run)

    def run_items(self, identity, space, run):
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            self._run(conn, space, run)
            rows = conn.execute(
                """SELECT memory_id,revision_id,memory_version,position,state,reason
                    FROM mnemion.librarian_items WHERE space_id=%s AND run_id=%s
                    ORDER BY position LIMIT 12""",
                (space, run),
            ).fetchall()
            return {"items": json_value(rows), "next_cursor": None}

    def runs(self, identity, space, *, cursor=None, limit=50):
        page = history_page(space, cursor, limit, 100)
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            rows = conn.execute(
                f"""SELECT {RUN_COLUMNS} FROM mnemion.librarian_runs WHERE space_id=%(space)s
                AND (%(at)s::timestamptz IS NULL OR (created_at,id)<(%(at)s,%(after)s))
                ORDER BY created_at DESC,id DESC LIMIT %(limit)s""",
                page,
            ).fetchall()
            return {
                "items": json_value(rows[:limit]),
                "next_cursor": history_cursor(space, rows, limit),
            }

    def cancel(self, identity, space, run):
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30, writing=True)
            self._run(conn, space, run)
            conn.execute(
                """UPDATE mnemion.librarian_runs SET state='cancelled',finished_at=now()
                    WHERE space_id=%s AND id=%s AND state IN ('queued','running')""",
                (space, run),
            )
            audit(conn, identity, "librarian.cancelled", run, space_id=space)
            return self._run(conn, space, run)

    @staticmethod
    def _proposal_output(conn, space, row):
        refs = reference_rows(conn, space, row["id"])
        available = row["state"] != "invalidated" and references_available(refs)
        stale = any(
            r["current_version"] != r["memory_version"]
            or r["current_revision_id"] != r["revision_id"]
            for r in refs
        )
        target = next((r for r in refs if r["memory_id"] == row["memory_id"]), None)
        if row["state"] == "accepted" and row["applied_version"] is not None:
            stale = not target or target["current_version"] != row["applied_version"]
        elif row["state"] == "accepted":
            stale = False  # Undoing an acknowledgement does not rewrite memory.
        return json_value(
            {
                "id": row["id"],
                "run_id": row["run_id"],
                "memory_id": row["memory_id"],
                "state": row["state"] if available else "invalidated",
                "version": row["version"],
                "suggestion": row["suggestion"] if available else None,
                "references": [
                    {field: ref[field] for field in ("memory_id", "revision_id", "memory_version")}
                    for ref in refs
                ]
                if available
                else [],
                "before": {
                    "subject": target["subject"],
                    "tags": target["metadata"].get("tags"),
                    "summary": target["metadata"].get("summary"),
                }
                if available and target
                else None,
                "applicable": available and not stale and row["state"] in {"pending", "accepted"},
                "unavailable_reason": "reference_unavailable"
                if not available
                else "revision_changed"
                if stale
                else None,
                "applied_revision_id": row["applied_revision_id"] if available else None,
                "created_at": row["created_at"],
                "decided_at": row["decided_at"],
            }
        )

    def proposals(self, identity, space, *, state=None, cursor=None, limit=20):
        page = {**history_page(space, cursor, limit, 50), "state": state}
        if state is not None and state not in {
            "pending",
            "accepted",
            "rejected",
            "undone",
            "invalidated",
        }:
            raise ServiceError(422, "invalid_state", "Choose a supported proposal state.")
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            rows = conn.execute(
                """SELECT * FROM mnemion.librarian_proposals WHERE space_id=%(space)s
                    AND (%(state)s::text IS NULL OR state=%(state)s)
                    AND (%(at)s::timestamptz IS NULL OR (created_at,id)<(%(at)s,%(after)s))
                    ORDER BY created_at DESC,id DESC LIMIT %(limit)s""",
                page,
            ).fetchall()
            return {
                "items": [self._proposal_output(conn, space, row) for row in rows[:limit]],
                "next_cursor": history_cursor(space, rows, limit),
            }

    def decide(self, identity, space, proposal, command: LibrarianDecision, key: str):
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30, writing=True)
            digest, previous = idempotency(
                conn,
                identity,
                space,
                key,
                {
                    "kind": "librarian-decision",
                    "proposal": str(proposal),
                    **command.model_dump(),
                },
            )
            if previous:
                return previous
            # Match the purge lock order: memory rows first, proposal second.
            for ref in reference_rows(conn, space, proposal):
                memory_row(conn, ref["memory_id"], review=True, deleted=True, lock=True)
            row = conn.execute(
                "SELECT * FROM mnemion.librarian_proposals WHERE space_id=%s AND id=%s FOR UPDATE",
                (space, proposal),
            ).fetchone()
            if not row:
                raise not_found()
            if row["version"] != command.expected_version:
                raise ServiceError(
                    409, "version_conflict", "This proposal changed; reload it before deciding."
                )
            output = self._proposal_output(conn, space, row)
            if output["state"] == "invalidated":
                raise ServiceError(
                    409,
                    "reference_unavailable",
                    "This proposal's source evidence is no longer available.",
                )
            expected_state = "accepted" if command.action == "undo" else "pending"
            if row["state"] != expected_state:
                raise ServiceError(
                    409, "proposal_already_decided", "This proposal already has a decision."
                )
            if command.action != "reject" and not output["applicable"]:
                raise ServiceError(
                    409, "revision_changed", "A source memory changed; run the librarian again."
                )
            suggestion = LibrarianSuggestion.model_validate(row["suggestion"])
            applied = row["applied_revision_id"]
            applied_version = row["applied_version"]
            before_revision = row["previous_revision_id"]
            if suggestion.kind == "organize" and command.action != "reject":
                memory = memory_row(conn, row["memory_id"], review=True, lock=True)
                revision = conn.execute(
                    "SELECT * FROM mnemion.memory_revisions WHERE space_id=%s AND id=%s",
                    (space, memory["current_revision_id"]),
                ).fetchone()
                metadata = dict(revision["metadata"])
                subject = revision["subject"]
                if command.action == "accept":
                    changes = suggestion.changes
                    if changes.subject is not None:
                        subject = changes.subject
                    if changes.tags is not None:
                        tags = metadata.get("tags", [])
                        if not isinstance(tags, list) or any(
                            not isinstance(tag, str) for tag in tags
                        ):
                            raise ServiceError(
                                409,
                                "metadata_conflict",
                                "Existing tags use a different format; edit this memory directly.",
                            )
                        merged = list(tags)
                        for tag in changes.tags:
                            if tag.casefold() not in {old.casefold() for old in merged}:
                                merged.append(tag)
                        metadata["tags"] = merged
                    if changes.summary is not None:
                        metadata["summary"] = changes.summary
                    before_revision = revision["id"]
                else:
                    original = conn.execute(
                        "SELECT subject,metadata FROM mnemion.memory_revisions WHERE space_id=%s AND id=%s",
                        (space, before_revision),
                    ).fetchone()
                    if not original:
                        raise ServiceError(
                            409,
                            "reference_unavailable",
                            "The original revision is no longer available.",
                        )
                    subject, metadata = original["subject"], original["metadata"]
                if subject != revision["subject"] or metadata != revision["metadata"]:
                    receipt = self.memory.revise_in_transaction(
                        conn,
                        identity,
                        row["memory_id"],
                        RevisionInput(
                            content=revision["content"],
                            subject=subject,
                            metadata=metadata,
                            expected_version=memory["version"],
                            reason=f"Librarian proposal {proposal}: {command.action}",
                        ),
                        None,  # The enclosing atomic decision owns its idempotency receipt.
                        preserve_evidence=True,
                    )
                    applied, applied_version = UUID(receipt["revision_id"]), receipt["version"]
                else:
                    applied, applied_version = revision["id"], memory["version"]
            state = {"accept": "accepted", "reject": "rejected", "undo": "undone"}[command.action]
            conn.execute(
                """UPDATE mnemion.librarian_proposals SET state=%s,version=version+1,decided_by=%s,decided_at=now(),
                    previous_revision_id=%s,applied_revision_id=%s,applied_version=%s WHERE space_id=%s AND id=%s""",
                (
                    state,
                    identity.principal_id,
                    before_revision,
                    applied,
                    applied_version,
                    space,
                    proposal,
                ),
            )
            audit(
                conn,
                identity,
                "librarian." + state,
                proposal,
                space_id=space,
                details={"memory_id": row["memory_id"], "version": row["version"] + 1},
            )
            return remember_receipt(
                conn,
                identity,
                space,
                key,
                digest,
                {
                    "proposal_id": proposal,
                    "state": state,
                    "version": row["version"] + 1,
                    "applied_revision_id": applied,
                },
            )
