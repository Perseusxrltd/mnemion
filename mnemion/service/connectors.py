"""Permission-aware ingestion, durable page receipts, and source reconciliation.

Adapters run outside the API process. This service never fetches caller URLs or
stores provider credentials. Connector mutations share canonical transactions.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from .connector_models import (
    BatchInput,
    BindingInput,
    ConnectorInput,
    ConnectorItemInput,
    FinishInput,
    ResolveInput,
    RunInput,
    ScopeInput,
    utc_now,
)
from .db import Identity, require_administrator, require_space
from .errors import ServiceError, not_found
from .memory import MemoryService
from .models import RevisionInput, json_value
from .repository import audit, hydrate, memory_row


def _digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def _lock(conn, space: UUID) -> None:
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"connector:{space}",))


class ConnectorService:
    def __init__(self, memory: MemoryService):
        self.memory, self.db = memory, memory.db

    def create(self, identity: Identity, command: ConnectorInput) -> dict:
        with self.db.transaction(identity) as conn:
            require_administrator(conn)
            principal = conn.execute(
                "SELECT * FROM mnemion.principals WHERE id=%s AND disabled_at IS NULL",
                (command.principal_id,),
            ).fetchone()
            if not principal or principal["kind"] != "application" or principal["administrator"]:
                raise ServiceError(
                    422, "connector_identity", "Select a dedicated non-administrator application."
                )
            if conn.execute(
                "SELECT id FROM mnemion.connectors WHERE principal_id=%s", (command.principal_id,)
            ).fetchone():
                raise ServiceError(
                    409, "connector_identity_used", "This application already owns a connector."
                )
            row = conn.execute(
                """INSERT INTO mnemion.connectors(tenant_id,id,name,provider,principal_id,access_mode)
                   VALUES(%s,%s,%s,%s,%s,%s) RETURNING *""",
                (
                    identity.tenant_id,
                    uuid4(),
                    command.name,
                    command.provider,
                    command.principal_id,
                    command.access_mode,
                ),
            ).fetchone()
            audit(
                conn,
                identity,
                "connector.created",
                row["id"],
                details={"provider": command.provider},
            )
            return json_value(row)

    def list(self, identity: Identity) -> dict:
        with self.db.transaction(identity) as conn:
            return {
                "items": json_value(
                    conn.execute(
                        "SELECT * FROM mnemion.connectors ORDER BY created_at,id LIMIT 1000"
                    ).fetchall()
                )
            }

    def disable(self, identity: Identity, connector: UUID) -> dict:
        with self.db.transaction(identity) as conn:
            require_administrator(conn)
            row = conn.execute(
                "UPDATE mnemion.connectors SET disabled_at=coalesce(disabled_at,now()) WHERE id=%s RETURNING *",
                (connector,),
            ).fetchone()
            if not row:
                raise not_found()
            audit(conn, identity, "connector.disabled", connector)
            return json_value(row)

    def enable(self, identity: Identity, connector: UUID) -> dict:
        with self.db.transaction(identity) as conn:
            require_administrator(conn)
            row = conn.execute(
                "SELECT * FROM mnemion.connectors WHERE id=%s FOR UPDATE", (connector,)
            ).fetchone()
            if not row:
                raise not_found()
            if row["disabled_at"] is None:
                return json_value(row)
            for scope in conn.execute(
                "SELECT space_id FROM mnemion.connector_scopes WHERE connector_id=%s", (connector,)
            ).fetchall():
                conn.execute(
                    "SELECT mnemion.suspend_connector_scope(%s,'provider_unavailable')",
                    (scope["space_id"],),
                )
            row = conn.execute(
                "UPDATE mnemion.connectors SET disabled_at=NULL WHERE id=%s RETURNING *",
                (connector,),
            ).fetchone()
            audit(conn, identity, "connector.enabled", connector)
            return json_value(row)

    def binding(
        self, identity: Identity, connector: UUID, command: BindingInput, *, remove=False
    ) -> dict:
        with self.db.transaction(identity) as conn:
            require_administrator(conn)
            if not conn.execute(
                "SELECT id FROM mnemion.connectors WHERE id=%s AND disabled_at IS NULL",
                (connector,),
            ).fetchone():
                raise not_found()
            if not conn.execute(
                "SELECT id FROM mnemion.principals WHERE id=%s AND disabled_at IS NULL",
                (command.principal_id,),
            ).fetchone():
                raise not_found()
            if remove:
                conn.execute(
                    "DELETE FROM mnemion.connector_bindings WHERE connector_id=%s AND external_id=%s AND principal_id=%s",
                    (connector, command.external_id, command.principal_id),
                )
            else:
                conn.execute(
                    """INSERT INTO mnemion.connector_bindings(tenant_id,connector_id,external_id,principal_id,role)
                       VALUES(%s,%s,%s,%s,%s) ON CONFLICT(tenant_id,connector_id,external_id,principal_id)
                       DO UPDATE SET role=excluded.role WHERE connector_bindings.role<>excluded.role""",
                    (
                        identity.tenant_id,
                        connector,
                        command.external_id,
                        command.principal_id,
                        command.role,
                    ),
                )
            audit(
                conn,
                identity,
                "connector.binding_removed" if remove else "connector.binding_updated",
                connector,
                details={"principal_id": command.principal_id, "role": command.role},
            )
            return {
                "connector_id": str(connector),
                **command.model_dump(mode="json"),
                "removed": remove,
            }

    def bindings(self, identity: Identity, connector: UUID) -> dict:
        with self.db.transaction(identity) as conn:
            if not conn.execute(
                "SELECT id FROM mnemion.connectors WHERE id=%s", (connector,)
            ).fetchone():
                raise not_found()
            return {
                "items": json_value(
                    conn.execute(
                        "SELECT external_id,principal_id,role FROM mnemion.connector_bindings WHERE connector_id=%s ORDER BY external_id,principal_id",
                        (connector,),
                    ).fetchall()
                )
            }

    def refresh_scope(self, identity: Identity, connector: UUID, command: ScopeInput) -> dict:
        with self.db.transaction(identity) as conn:
            if not conn.execute(
                "SELECT mnemion.owns_connector(%s) AS allowed", (connector,)
            ).fetchone()["allowed"]:
                raise not_found()
            now = utc_now()
            if (
                command.observed_at > now + timedelta(seconds=30)
                or command.observed_at + timedelta(seconds=command.lease_seconds) <= now
            ):
                raise ServiceError(
                    422, "stale_access_snapshot", "Obtain a fresh provider permission snapshot."
                )
            existing = conn.execute(
                "SELECT space_id FROM mnemion.connector_scopes WHERE connector_id=%s AND external_id=%s",
                (connector, command.external_id),
            ).fetchone()
            if existing:
                _lock(conn, existing["space_id"])
            previous = conn.execute(
                "SELECT observed_at,operator_paused FROM mnemion.connector_scopes WHERE connector_id=%s AND external_id=%s",
                (connector, command.external_id),
            ).fetchone()
            if previous and previous["operator_paused"]:
                raise ServiceError(
                    409,
                    "connector_paused",
                    "An administrator must resume this source before permission checks can reopen it.",
                )
            if previous and previous["observed_at"] > command.observed_at:
                raise ServiceError(
                    409,
                    "stale_access_snapshot",
                    "A newer provider permission snapshot is already recorded.",
                )
            row = conn.execute(
                "SELECT mnemion.refresh_connector_scope(%s,%s,%s,%s,%s,%s) AS space",
                (
                    connector,
                    command.external_id,
                    command.name,
                    command.members,
                    command.observed_at,
                    command.lease_seconds,
                ),
            ).fetchone()
            scope = self._scope(conn, row["space"])
            audit(
                conn,
                identity,
                "connector.access_checked",
                row["space"],
                space_id=row["space"],
                details={"connector_id": connector, "external_members": len(set(command.members))},
            )
            return json_value(scope)

    def scopes(
        self, identity: Identity, connector: UUID, *, after: UUID | None = None, limit=100
    ) -> dict:
        with self.db.transaction(identity) as conn:
            if not conn.execute(
                "SELECT id FROM mnemion.connectors WHERE id=%s", (connector,)
            ).fetchone():
                raise not_found()
            rows = conn.execute(
                """SELECT s.*,p.name,s.suspended_at IS NULL AND s.access_valid_until>now() AS access_current
                   FROM mnemion.connector_scopes s JOIN mnemion.spaces p ON p.tenant_id=s.tenant_id AND p.id=s.space_id
                   WHERE s.connector_id=%s AND (%s::uuid IS NULL OR s.space_id>%s) ORDER BY s.space_id LIMIT %s""",
                (connector, after, after, limit + 1),
            ).fetchall()
            return {
                "items": json_value(rows[:limit]),
                "next_cursor": str(rows[limit - 1]["space_id"]) if len(rows) > limit else None,
            }

    def suspend(self, identity: Identity, space: UUID, reason: str) -> dict:
        with self.db.transaction(identity) as conn:
            row = conn.execute(
                "SELECT * FROM mnemion.connector_scopes WHERE space_id=%s", (space,)
            ).fetchone()
            if not row:
                raise not_found()
            conn.execute("SELECT mnemion.suspend_connector_scope(%s,%s)", (space, reason))
            audit(
                conn,
                identity,
                "connector.access_suspended",
                space,
                space_id=space,
                details={"reason_code": reason},
            )
            return {"space_id": str(space), "suspended": True, "reason": reason}

    def _scope(self, conn, space: UUID, *, active=True) -> dict:
        if not conn.execute(
            "SELECT mnemion.owns_connector_scope(%s) AS allowed", (space,)
        ).fetchone()["allowed"]:
            raise not_found()
        row = conn.execute(
            "SELECT *,access_valid_until>now() AS access_current FROM mnemion.connector_scopes WHERE space_id=%s",
            (space,),
        ).fetchone()
        if active and (row["suspended_at"] or not row["access_current"]):
            raise ServiceError(
                409, "connector_access_stale", "Refresh source permissions before ingestion."
            )
        return row

    def resume(self, identity: Identity, space: UUID) -> dict:
        with self.db.transaction(identity) as conn:
            require_administrator(conn)
            if not conn.execute(
                "SELECT space_id FROM mnemion.connector_scopes WHERE space_id=%s", (space,)
            ).fetchone():
                raise not_found()
            conn.execute("SELECT mnemion.resume_connector_scope(%s)", (space,))
            audit(conn, identity, "connector.operator_resumed", space, space_id=space)
            return {
                "space_id": str(space),
                "suspended": True,
                "reason": "provider_revalidation_required",
            }

    def begin(self, identity: Identity, space: UUID, command: RunInput) -> dict:
        with self.db.transaction(identity) as conn:
            _lock(conn, space)
            scope = self._scope(conn, space)
            require_space(conn, space, 20, writing=True)
            previous = conn.execute(
                "SELECT * FROM mnemion.connector_runs WHERE space_id=%s AND id=%s",
                (space, command.run_id),
            ).fetchone()
            if previous:
                if previous["mode"] != command.mode:
                    raise ServiceError(409, "run_conflict", "This run ID has a different mode.")
                return json_value(previous)
            conn.execute(
                """UPDATE mnemion.connector_runs SET state='aborted',finished_at=now()
                         WHERE space_id=%s AND state IN ('running','finalizing') AND lease_until<=now()""",
                (space,),
            )
            if conn.execute(
                "SELECT id FROM mnemion.connector_runs WHERE space_id=%s AND state IN ('running','finalizing')",
                (space,),
            ).fetchone():
                raise ServiceError(
                    409,
                    "connector_busy",
                    "Another agent has an active ingestion lease for this scope.",
                )
            row = conn.execute(
                """INSERT INTO mnemion.connector_runs(tenant_id,space_id,id,mode,checkpoint)
                   VALUES(%s,%s,%s,%s,%s) RETURNING *""",
                (identity.tenant_id, space, command.run_id, command.mode, scope["checkpoint"]),
            ).fetchone()
            return json_value(row)

    @staticmethod
    def _run(conn, space: UUID, run: UUID) -> dict:
        row = conn.execute(
            "SELECT *,lease_until>now() AS lease_current FROM mnemion.connector_runs WHERE space_id=%s AND id=%s FOR UPDATE",
            (space, run),
        ).fetchone()
        if not row:
            raise not_found()
        return row

    def page(self, identity: Identity, space: UUID, run: UUID, command: BatchInput) -> dict:
        with self.db.transaction(identity) as conn:
            _lock(conn, space)
            self._scope(conn, space)
            require_space(conn, space, 20, writing=True)
            current = self._run(conn, space, run)
            digest = _digest(command.model_dump(mode="json"))
            previous = conn.execute(
                "SELECT * FROM mnemion.connector_pages WHERE space_id=%s AND run_id=%s AND sequence=%s",
                (space, run, command.sequence),
            ).fetchone()
            if previous:
                if previous["request_hash"] != digest:
                    raise ServiceError(
                        409,
                        "page_conflict",
                        "This page was already committed with a different payload.",
                    )
                return previous["response"]
            if current["state"] != "running" or not current["lease_current"]:
                raise ServiceError(
                    409, "run_inactive", "Start a new run after an expired or finished lease."
                )
            if current["next_sequence"] != command.sequence:
                raise ServiceError(
                    409, "page_sequence", "Send pages in order without skipping a page."
                )
            results = [
                self._item(
                    conn, identity, space, run, item, f"connector:{run}:{command.sequence}:{i}"
                )
                for i, item in enumerate(command.items)
            ]
            response = {
                "run_id": str(run),
                "sequence": command.sequence,
                "next_sequence": command.sequence + 1,
                "items": results,
            }
            conn.execute(
                "INSERT INTO mnemion.connector_pages(tenant_id,space_id,run_id,sequence,request_hash,response) VALUES(%s,%s,%s,%s,%s,%s)",
                (identity.tenant_id, space, run, command.sequence, digest, Jsonb(response)),
            )
            conn.execute(
                """UPDATE mnemion.connector_runs SET next_sequence=next_sequence+1,checkpoint=%s,
                         lease_until=now()+interval '5 minutes' WHERE space_id=%s AND id=%s""",
                (command.checkpoint, space, run),
            )
            return response

    def _item(self, conn, identity, space, run, item: ConnectorItemInput, key: str) -> dict:
        current = conn.execute(
            "SELECT * FROM mnemion.connector_items WHERE space_id=%s AND external_id=%s FOR UPDATE",
            (space, item.external_id),
        ).fetchone()
        data = item.memory.model_dump(mode="json") if item.memory else None
        digest = _digest(data) if data else None
        memory = current["memory_id"] if current else None
        row = (
            conn.execute(
                "SELECT * FROM mnemion.memories WHERE id=%s FOR UPDATE", (memory,)
            ).fetchone()
            if memory
            else None
        )
        state, version, outcome = (
            "active",
            current["applied_version"] if current else None,
            "unchanged",
        )
        if (
            item.action == "delete"
            or (current and current["state"] == "deleted")
            or (row and row["deleted_at"])
        ):
            if row and not row["deleted_at"]:
                self._delete(conn, identity, row, key)
            state, digest = "deleted", None
            outcome = "deleted" if item.action == "delete" else "deletion_preserved"
        elif current and current["content_hash"] == digest:
            # A repeated observation never overwrites a local edit or review.
            state, outcome = (
                current["state"],
                "conflict" if current["state"] == "conflict" else "unchanged",
            )
        elif current and current["origin_revision"] == item.revision:
            raise ServiceError(
                409,
                "source_revision_conflict",
                "A source revision must identify immutable content and metadata.",
            )
        elif row and (
            row["version"] != version
            or row["review_state"] != "ordinary"
            or hydrate(conn, row)["claim_status"] != "observed"
        ):
            state, outcome = "conflict", "conflict"
        elif row:
            result = self.memory.revise_in_transaction(
                conn,
                identity,
                memory,
                RevisionInput(
                    **data, expected_version=row["version"], reason="Source connector update"
                ),
                key,
            )
            version, outcome = result["version"], "revised"
        else:
            result = self.memory.save_in_transaction(conn, identity, space, item.memory, key)
            memory, version, outcome = UUID(result["memory_id"]), result["version"], "created"
        conn.execute(
            """INSERT INTO mnemion.connector_items(tenant_id,space_id,external_id,memory_id,origin_revision,
                 content_hash,applied_version,last_seen_run,state) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT(tenant_id,space_id,external_id) DO UPDATE SET origin_revision=excluded.origin_revision,
                 content_hash=excluded.content_hash,applied_version=excluded.applied_version,last_seen_run=excluded.last_seen_run,
                 state=excluded.state,updated_at=now()""",
            (
                identity.tenant_id,
                space,
                item.external_id,
                memory,
                item.revision,
                digest,
                version,
                run,
                state,
            ),
        )
        if outcome == "conflict":
            payload = item.model_dump(mode="json")
            conn.execute(
                """INSERT INTO mnemion.connector_proposals(tenant_id,space_id,memory_id,proposal_hash,payload)
                         VALUES(%s,%s,%s,%s,%s) ON CONFLICT(tenant_id,space_id,memory_id)
                         DO UPDATE SET proposal_hash=excluded.proposal_hash,payload=excluded.payload,created_at=now()""",
                (identity.tenant_id, space, memory, _digest(payload), Jsonb(payload)),
            )
        return {
            "external_id": item.external_id,
            "memory_id": str(memory) if memory else None,
            "outcome": outcome,
        }

    def _delete(self, conn, identity, row, key):
        conn.execute(
            "DELETE FROM mnemion.connector_proposals WHERE space_id=%s AND memory_id=%s",
            (row["space_id"], row["id"]),
        )
        self.memory.forget_in_transaction(
            conn, identity, row["id"], expected_version=row["version"], key=key
        )

    def finish(self, identity: Identity, space: UUID, run: UUID, command: FinishInput) -> dict:
        with self.db.transaction(identity) as conn:
            _lock(conn, space)
            self._scope(conn, space)
            require_space(conn, space, 20, writing=True)
            current = self._run(conn, space, run)
            if (current["mode"] == "snapshot") != command.complete_inventory:
                raise ServiceError(
                    422,
                    "inventory_required",
                    "Only a complete authoritative snapshot may infer source deletions.",
                )
            if current["state"] == "completed":
                return current["result"]
            if current["state"] not in ("running", "finalizing") or not current["lease_current"]:
                raise ServiceError(409, "run_inactive", "The ingestion lease is no longer active.")
            if not current["next_sequence"]:
                raise ServiceError(
                    422,
                    "inventory_required",
                    "Commit at least one page, including for an empty inventory.",
                )
            missing = (
                conn.execute(
                    """SELECT * FROM mnemion.connector_items WHERE space_id=%s AND state<>'deleted'
                     AND last_seen_run<>%s ORDER BY external_id LIMIT 101 FOR UPDATE""",
                    (space, run),
                ).fetchall()
                if command.complete_inventory
                else []
            )
            for item in missing[:100]:
                row = conn.execute(
                    "SELECT * FROM mnemion.memories WHERE id=%s FOR UPDATE", (item["memory_id"],)
                ).fetchone()
                if row and not row["deleted_at"]:
                    self._delete(conn, identity, row, f"connector:{run}:missing:{row['id']}")
                conn.execute(
                    "UPDATE mnemion.connector_items SET state='deleted',content_hash=NULL,updated_at=now() WHERE space_id=%s AND external_id=%s",
                    (space, item["external_id"]),
                )
            state = "finalizing" if len(missing) > 100 else "completed"
            deleted = (current["result"] or {}).get("removed", 0) + min(len(missing), 100)
            result = {
                "run_id": str(run),
                "space_id": str(space),
                "state": state,
                "pages": current["next_sequence"],
                "removed": deleted,
                "checkpoint_committed": state == "completed",
            }
            conn.execute(
                """UPDATE mnemion.connector_runs SET state=%s,result=%s,
                         lease_until=now()+interval '5 minutes',finished_at=CASE WHEN %s='completed' THEN now() ELSE NULL END
                         WHERE space_id=%s AND id=%s""",
                (state, Jsonb(result), state, space, run),
            )
            if state == "completed":
                conn.execute(
                    "SELECT mnemion.commit_connector_cursor(%s,%s)", (space, current["checkpoint"])
                )
                audit(
                    conn,
                    identity,
                    "connector.synced",
                    run,
                    space_id=space,
                    details={"pages": current["next_sequence"], "inferred_deletions": deleted},
                )
            return result

    def proposals(self, identity: Identity, space: UUID) -> dict:
        with self.db.transaction(identity) as conn:
            require_space(conn, space, 30)
            return {
                "items": json_value(
                    conn.execute(
                        """SELECT p.memory_id,p.proposal_hash,p.payload,p.created_at,m.version
                   FROM mnemion.connector_proposals p JOIN mnemion.memories m
                     ON m.tenant_id=p.tenant_id AND m.space_id=p.space_id AND m.id=p.memory_id
                   WHERE p.space_id=%s AND m.deleted_at IS NULL ORDER BY p.created_at,p.memory_id LIMIT 100""",
                        (space,),
                    ).fetchall()
                )
            }

    def resolve(self, identity: Identity, memory: UUID, command: ResolveInput) -> dict:
        with self.db.transaction(identity) as conn:
            visible = memory_row(conn, memory, review=True)
            space = visible["space_id"]
            _lock(conn, space)
            require_space(conn, space, 30, writing=True)
            row = memory_row(conn, memory, review=True, lock=True)
            proposal = conn.execute(
                "SELECT * FROM mnemion.connector_proposals WHERE memory_id=%s FOR UPDATE", (memory,)
            ).fetchone()
            if not proposal:
                raise not_found()
            if (
                row["version"] != command.expected_version
                or proposal["proposal_hash"] != command.proposal_hash
            ):
                raise ServiceError(
                    409,
                    "proposal_changed",
                    "Refresh both the memory and incoming proposal before resolving.",
                )
            if command.resolution == "accept":
                source = ConnectorItemInput.model_validate(proposal["payload"])
                receipt = self.memory.revise_in_transaction(
                    conn,
                    identity,
                    memory,
                    RevisionInput(
                        **source.memory.model_dump(mode="json"),
                        expected_version=command.expected_version,
                        reason=command.reason,
                    ),
                    f"connector-resolve:{memory}:{command.proposal_hash}:{command.expected_version}",
                )
                conn.execute(
                    "UPDATE mnemion.connector_items SET applied_version=%s WHERE memory_id=%s",
                    (receipt["version"], memory),
                )
            else:
                audit(
                    conn,
                    identity,
                    "memory.reviewed",
                    memory,
                    space_id=space,
                    details={"reason": command.reason, "connector_resolution": "keep_local"},
                )
            conn.execute(
                "UPDATE mnemion.connector_items SET state='active',updated_at=now() WHERE memory_id=%s",
                (memory,),
            )
            conn.execute("DELETE FROM mnemion.connector_proposals WHERE memory_id=%s", (memory,))
            audit(
                conn,
                identity,
                "connector.proposal_resolved",
                memory,
                space_id=space,
                details={"resolution": command.resolution},
            )
            return {"memory_id": str(memory), "resolution": command.resolution}
