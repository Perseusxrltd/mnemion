"""Durable source wakeups; only the source's own runner reports completion."""

from uuid import UUID

from .connector_models import SyncReportInput, SyncRequestInput
from .db import Identity
from .errors import ServiceError, not_found
from .models import json_value
from .repository import audit


def _authorize(conn, connector: UUID, *, write=False, runner=False):
    row = conn.execute(
        """SELECT disabled_at,mnemion.administrator() AS administrator,
                  mnemion.owns_connector(id) AS runner
           FROM mnemion.connectors WHERE id=%s""",
        (connector,),
    ).fetchone()
    if not row or not (row["administrator"] or row["runner"]):
        raise not_found()
    if runner and not row["runner"]:
        raise ServiceError(
            403, "connector_identity", "Only this connector's runner can report a scan."
        )
    if write and row["disabled_at"] is not None:
        raise ServiceError(
            409, "connector_disabled", "Enable this connector before requesting a scan."
        )


def _state(conn, connector: UUID) -> dict:
    row = conn.execute(
        "SELECT * FROM mnemion.connector_sync_control WHERE connector_id=%s", (connector,)
    ).fetchone()
    if row is None:
        row = dict(
            connector_id=connector,
            requested_generation=0,
            completed_generation=0,
            requested_at=None,
            completed_at=None,
            last_attempt_at=None,
            last_successful=None,
            last_duration_seconds=None,
            last_changed=0,
            last_removed=0,
            last_unchanged=0,
            last_error_code=None,
        )
    row.pop("tenant_id", None)
    row["pending"] = row["requested_generation"] > row["completed_generation"]
    return json_value(row)


def _prepare(conn, identity: Identity, connector: UUID):
    conn.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
        (f"connector-sync:{identity.tenant_id}:{connector}",),
    )
    conn.execute(
        """INSERT INTO mnemion.connector_sync_control(tenant_id,connector_id)
           VALUES(%s,%s) ON CONFLICT DO NOTHING""",
        (identity.tenant_id, connector),
    )


class ConnectorSyncControls:
    def sync_status(self, identity: Identity, connector: UUID) -> dict:
        with self.db.transaction(identity) as conn:
            _authorize(conn, connector)
            return _state(conn, connector)

    def request_sync(self, identity: Identity, connector: UUID, command: SyncRequestInput) -> dict:
        with self.db.transaction(identity) as conn:
            _authorize(conn, connector, write=True)
            _prepare(conn, identity, connector)
            state = _state(conn, connector)
            if state["requested_generation"] != command.expected_generation:
                raise ServiceError(
                    409,
                    "sync_request_changed",
                    "Read the current sync status before requesting again.",
                )
            if command.expected_generation == 9007199254740991:
                raise ServiceError(
                    409, "sync_generation_limit", "This connector has reached its request limit."
                )
            conn.execute(
                """UPDATE mnemion.connector_sync_control SET requested_generation=requested_generation+1,
                   requested_at=now() WHERE connector_id=%s""",
                (connector,),
            )
            audit(
                conn,
                identity,
                "connector.sync_requested",
                connector,
                details={"generation": command.expected_generation + 1},
            )
            return _state(conn, connector)

    def report_sync(self, identity: Identity, connector: UUID, command: SyncReportInput) -> dict:
        with self.db.transaction(identity) as conn:
            _authorize(conn, connector, write=True, runner=True)
            _prepare(conn, identity, connector)
            state = _state(conn, connector)
            if command.generation > state["requested_generation"]:
                raise ServiceError(
                    409, "sync_generation_unknown", "A scan cannot acknowledge a future request."
                )
            conn.execute(
                """UPDATE mnemion.connector_sync_control SET
                   completed_generation=CASE WHEN %s THEN greatest(completed_generation,%s) ELSE completed_generation END,
                   completed_at=CASE WHEN %s THEN now() ELSE completed_at END,
                   last_attempt_at=now(),last_successful=%s,last_duration_seconds=%s,
                   last_changed=%s,last_removed=%s,last_unchanged=%s,last_error_code=%s
                   WHERE connector_id=%s""",
                (
                    command.successful,
                    command.generation,
                    command.successful,
                    command.successful,
                    command.duration_seconds,
                    command.changed,
                    command.removed,
                    command.unchanged,
                    command.error_code,
                    connector,
                ),
            )
            return _state(conn, connector)
