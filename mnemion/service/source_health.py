"""Source freshness for the caller's own grants, without provider paths or ACL leaks."""

from datetime import datetime, timezone
from uuid import UUID

from .errors import ServiceError
from .models import json_value


def source_health(conn, selected=None) -> dict:
    result = conn.execute("SELECT * FROM mnemion.source_health(%s::uuid[])", (selected,)).fetchone()
    attention = []
    if result["unavailable_scopes"]:
        attention.append("connector_scope_suspended")
    if result["incomplete_scopes"]:
        attention.append("connector_inventory_incomplete")
    return {**result, "attention": attention, "observed_at": datetime.now(timezone.utc).isoformat()}


def source_diagnostics(conn, *, after: UUID | None = None, limit: int = 20) -> dict:
    """Inspect operator-visible rows under their existing RLS, never a definer bypass."""
    if not 1 <= limit <= 100:
        raise ServiceError(422, "invalid_limit", "Limit must be between 1 and 100.")
    authority = conn.execute(
        """SELECT mnemion.administrator() AS administrator, EXISTS(
             SELECT FROM mnemion.connectors WHERE principal_id=mnemion.principal()
           ) AS registered_operator"""
    ).fetchone()
    visibility = (
        "tenant"
        if authority["administrator"]
        else "owned"
        if authority["registered_operator"]
        else "unavailable"
    )
    if visibility == "unavailable":
        return {"visibility": visibility, "items": [], "next_cursor": None}
    rows = conn.execute(
        """SELECT s.space_id,s.connector_id,c.principal_id AS operator_id,
                  CASE WHEN c.provider IN ('filesystem','git','conversations','gdrive','slack','rclone')
                       THEN c.provider ELSE 'other' END AS provider,
                  s.operator_paused,s.suspended_at IS NOT NULL AS suspended,s.suspension_reason,
                  s.access_valid_until<=now() AS expired,c.disabled_at IS NOT NULL AS disabled,
                  p.disabled_at IS NOT NULL AS operator_disabled,p.administrator AS unsafe_operator,
                  coalesce((latest.result->>'skipped_documents')::bigint,0) AS skipped_documents
           FROM mnemion.connector_scopes s
           JOIN mnemion.connectors c ON c.tenant_id=s.tenant_id AND c.id=s.connector_id
           JOIN mnemion.principals p ON p.tenant_id=c.tenant_id AND p.id=c.principal_id
           LEFT JOIN LATERAL (
             SELECT r.result FROM mnemion.connector_runs r
             WHERE r.tenant_id=s.tenant_id AND r.space_id=s.space_id AND r.state='completed'
             ORDER BY r.finished_at DESC,r.id DESC LIMIT 1
           ) latest ON true
           WHERE (%s::uuid IS NULL OR s.space_id>%s) AND (
             s.operator_paused OR s.suspended_at IS NOT NULL OR s.access_valid_until<=now()
             OR c.disabled_at IS NOT NULL OR p.disabled_at IS NOT NULL OR p.administrator
             OR coalesce((latest.result->>'skipped_documents')::bigint,0)>0)
           ORDER BY s.space_id LIMIT %s""",
        (after, after, limit + 1),
    ).fetchall()
    items = []
    for row in rows[:limit]:
        reasons = []
        for flag, reason in (
            ("disabled", "connector_disabled"),
            ("operator_disabled", "connector_identity_disabled"),
            ("unsafe_operator", "connector_identity_not_dedicated"),
            ("operator_paused", "operator_paused"),
            ("expired", "permissions_expired"),
        ):
            if row[flag]:
                reasons.append(reason)
        if row["suspended"] and not row["operator_paused"]:
            reasons.append(
                {
                    "access_lost": "source_access_lost",
                    "provider_unavailable": "provider_unavailable",
                }.get(row["suspension_reason"], "permissions_recheck_required")
            )
        if row["skipped_documents"]:
            reasons.append("inventory_incomplete")
        ready_identity = not (row["disabled"] or row["operator_disabled"] or row["unsafe_operator"])
        recovery = (
            "restore_connector_identity"
            if row["operator_disabled"] or row["unsafe_operator"]
            else "enable_connector"
            if row["disabled"]
            else "resume_source"
            if row["operator_paused"]
            else "request_source_sync"
            if row["suspended"] or row["expired"]
            else "repair_source_files"
        )
        items.append(
            {
                key: row[key]
                for key in (
                    "space_id",
                    "connector_id",
                    "operator_id",
                    "provider",
                    "operator_paused",
                    "skipped_documents",
                )
            }
            | {
                "reasons": reasons,
                "recovery": recovery,
                "can_resume": bool(
                    authority["administrator"] and row["operator_paused"] and ready_identity
                ),
                "can_request_sync": ready_identity and not row["operator_paused"],
            }
        )
    return {
        "visibility": visibility,
        "items": json_value(items),
        "next_cursor": str(rows[limit - 1]["space_id"]) if len(rows) > limit else None,
    }
