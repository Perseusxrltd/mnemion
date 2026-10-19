"""Explicit continuity for non-administrator application keys during recovery.

Only keys present both in the backup and the operator's reviewed current ledger
qualify. Human, session, administrator, revoked and expired keys never qualify.
This is separate from vault grants, which still require fresh approval.
"""

from datetime import datetime
from uuid import UUID

from psycopg import sql
from psycopg.types.json import Jsonb


def capture(conn) -> dict:
    sessions = conn.execute(
        """SELECT EXISTS(SELECT 1 FROM pg_attribute
        WHERE attrelid='mnemion.api_keys'::regclass AND attname='session_key'
          AND NOT attisdropped) AS present"""
    ).fetchone()["present"]
    return {
        "version": 1,
        "keys": conn.execute(
            sql.SQL("""SELECT k.tenant_id,k.id,k.principal_id,k.expires_at
            FROM mnemion.api_keys k JOIN mnemion.principals p
            ON p.tenant_id=k.tenant_id AND p.id=k.principal_id
            WHERE p.kind='application' AND NOT p.administrator AND p.disabled_at IS NULL
              AND {} AND k.revoked_at IS NULL
              AND (k.expires_at IS NULL OR k.expires_at>clock_timestamp())
            ORDER BY k.tenant_id,k.id""").format(
                sql.SQL("NOT k.session_key" if sessions else "TRUE")
            )
        ).fetchall(),
    }


def validate(value: dict, tenants: set[str]) -> None:
    if (
        not isinstance(value, dict)
        or type(value.get("version")) is not int
        or value["version"] != 1
        or not isinstance(value.get("keys"), list)
        or len(value["keys"]) > 1_000_000
    ):
        raise ValueError("Unsupported application-key recovery ledger")
    seen = set()
    for row in value["keys"]:
        if not isinstance(row, dict) or set(row) != {
            "tenant_id",
            "id",
            "principal_id",
            "expires_at",
        }:
            raise ValueError("Invalid application-key recovery entry")
        identity = (str(UUID(row["tenant_id"])), str(UUID(row["id"])))
        UUID(row["principal_id"])
        if identity[0] not in tenants or identity in seen:
            raise ValueError("Invalid or duplicate application-key recovery identity")
        seen.add(identity)
        if row["expires_at"] is not None:
            if datetime.fromisoformat(row["expires_at"]).tzinfo is None:
                raise ValueError("Application-key expiry must include its timezone")


def eligible(conn, ledger: dict) -> list[dict]:
    value = ledger.get("application_key_state")
    if value is None:
        raise ValueError("Preserving application keys requires an application-key-aware ledger")
    validate(value, set(ledger["tenant_ids"]))
    result = []
    for offset in range(0, len(value["keys"]), 512):
        rows = value["keys"][offset : offset + 512]
        accepted = conn.execute(
            """SELECT k.tenant_id,k.id FROM mnemion.api_keys k JOIN mnemion.principals p
            ON p.tenant_id=k.tenant_id AND p.id=k.principal_id
            JOIN jsonb_to_recordset(%s) AS reviewed(tenant_id uuid,id uuid,principal_id uuid,expires_at timestamptz)
            ON k.tenant_id=reviewed.tenant_id AND k.id=reviewed.id AND k.principal_id=reviewed.principal_id
            WHERE p.kind='application' AND NOT p.administrator AND p.disabled_at IS NULL
              AND NOT k.session_key AND k.revoked_at IS NULL
              AND (k.expires_at IS NULL OR k.expires_at>clock_timestamp())
              AND (reviewed.expires_at IS NULL OR reviewed.expires_at>clock_timestamp())""",
            (Jsonb(rows),),
        ).fetchall()
        identities = {(str(row["tenant_id"]), str(row["id"])) for row in accepted}
        result.extend(row for row in rows if (row["tenant_id"], row["id"]) in identities)
    return result


def retain(conn, selected: list[dict]) -> None:
    for offset in range(0, len(selected), 512):
        # Retention never extends the backed-up expiry. A newer, earlier expiry
        # is enforced; access grants and principal state were reconciled first.
        conn.execute(
            """UPDATE mnemion.api_keys k SET revoked_at=NULL,
            expires_at=least(k.expires_at,reviewed.expires_at)
            FROM jsonb_to_recordset(%s) AS reviewed(tenant_id uuid,id uuid,principal_id uuid,expires_at timestamptz)
            WHERE k.tenant_id=reviewed.tenant_id AND k.id=reviewed.id AND k.principal_id=reviewed.principal_id""",
            (Jsonb(selected[offset : offset + 512]),),
        )
