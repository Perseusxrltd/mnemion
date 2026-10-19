"""Secret deletion reconciliation; historical grants never become current consent."""

from datetime import datetime
from uuid import UUID


def capture(conn):
    # Older supported installations can still create a pre-vault ledger.
    if not conn.execute("SELECT to_regclass('mnemion.vault_denials') AS relation").fetchone()[
        "relation"
    ]:
        return None
    return {
        "version": 1,
        "deletions": conn.execute(
            "SELECT tenant_id,entry_id,requested_at FROM mnemion.vault_denials ORDER BY tenant_id,entry_id"
        ).fetchall(),
    }


def validate(value, tenants):
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "deletions"}
        or type(value["version"]) is not int
        or value["version"] != 1
        or not isinstance(value["deletions"], list)
    ):
        raise ValueError("Invalid vault recovery ledger")
    seen = set()
    for row in value["deletions"]:
        if not isinstance(row, dict) or set(row) != {"tenant_id", "entry_id", "requested_at"}:
            raise ValueError("Invalid vault deletion entry")
        tenant, entry = str(UUID(row["tenant_id"])), str(UUID(row["entry_id"]))
        if (
            tenant not in tenants
            or (tenant, entry) in seen
            or datetime.fromisoformat(row["requested_at"]).tzinfo is None
        ):
            raise ValueError("Invalid vault deletion scope or date")
        seen.add((tenant, entry))


def restore(conn, ledger):
    value = ledger.get("vault_state")
    if value is None:
        if conn.execute("SELECT 1 AS present FROM mnemion.vault_entries LIMIT 1").fetchone():
            raise ValueError(
                "A backup containing credentials requires a current vault-aware recovery ledger"
            )
    else:
        tenants = {str(row["id"]) for row in conn.execute("SELECT id FROM mnemion.tenants")}
        for entry in value["deletions"]:
            if entry["tenant_id"] not in tenants:
                continue
            conn.execute(
                """INSERT INTO mnemion.vault_denials(tenant_id,entry_id,requested_at)
                VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",
                (entry["tenant_id"], entry["entry_id"], entry["requested_at"]),
            )
        mapping = (
            "keepass_nonce=NULL,keepass_ciphertext=NULL,"
            if conn.execute("""SELECT 1 FROM information_schema.columns WHERE table_schema='mnemion'
                AND table_name='vault_entries' AND column_name='keepass_nonce'""").fetchone()
            else ""
        )
        conn.execute(f"""UPDATE mnemion.vault_entries e SET
            deleted_at=coalesce(e.deleted_at,d.requested_at),nonce=NULL,ciphertext=NULL,
            {mapping}
            version=version+CASE WHEN e.deleted_at IS NULL THEN 1 ELSE 0 END
            FROM mnemion.vault_denials d WHERE d.tenant_id=e.tenant_id AND d.entry_id=e.id""")
    # New recovery keys and freshly reenrolled people need explicitly reviewed
    # vault grants. An old session/person grant is never silently resurrected.
    conn.execute("DELETE FROM mnemion.vault_grants")
    conn.execute("UPDATE mnemion.vault_entries SET access_version=access_version+1")
