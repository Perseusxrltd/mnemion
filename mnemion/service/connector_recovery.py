"""Current connector access and external deletion identities survive old backups."""

from uuid import UUID


def capture(conn) -> dict:
    from .capture_recovery import capture as capture_custody

    return {
        "version": 3,
        "custody": capture_custody(conn),
        "connections": conn.execute(
            "SELECT tenant_id,id,disabled_at FROM mnemion.connectors ORDER BY tenant_id,id"
        ).fetchall(),
        "bindings": conn.execute(
            "SELECT * FROM mnemion.connector_bindings ORDER BY tenant_id,connector_id,external_id,principal_id"
        ).fetchall(),
        "scopes": conn.execute(
            "SELECT tenant_id,connector_id,space_id,external_id,operator_paused FROM mnemion.connector_scopes ORDER BY tenant_id,space_id"
        ).fetchall(),
        "deletions": conn.execute("""SELECT i.tenant_id,i.space_id,i.external_id,i.memory_id,i.origin_revision,i.last_seen_run
            FROM mnemion.connector_items i LEFT JOIN mnemion.memories m ON m.tenant_id=i.tenant_id
              AND m.space_id=i.space_id AND m.id=i.memory_id
            WHERE i.state='deleted' OR m.deleted_at IS NOT NULL ORDER BY i.tenant_id,i.space_id,i.external_id""").fetchall(),
    }


def validate(state: dict, tenants: set[str]) -> None:
    if not isinstance(state, dict) or state.get("version") not in (1, 2, 3):
        raise ValueError("Unsupported connector recovery ledger")
    if state["version"] == 3:
        from .capture_recovery import validate as validate_custody

        validate_custody(state.get("custody"), tenants)
    for group, fields in (
        ("connections", ("id",)),
        ("bindings", ("connector_id", "principal_id")),
        ("scopes", ("connector_id", "space_id")),
        ("deletions", ("space_id", "last_seen_run")),
    ):
        if not isinstance(state.get(group), list):
            raise ValueError("Invalid connector recovery ledger")
        for row in state[group]:
            if str(UUID(row["tenant_id"])) not in tenants:
                raise ValueError("Unknown tenant in connector recovery ledger")
            for field in fields:
                UUID(row[field])
            if group == "bindings" and row["role"] not in {"reader", "reviewer"}:
                raise ValueError("Invalid connector recovery binding")
            if "external_id" in row and (
                not isinstance(row["external_id"], str) or not 1 <= len(row["external_id"]) <= 512
            ):
                raise ValueError("Invalid connector recovery source identity")
            if group == "deletions" and row["memory_id"] is not None:
                UUID(row["memory_id"])
            if (
                group == "scopes"
                and state["version"] >= 2
                and not isinstance(row.get("operator_paused"), bool)
            ):
                raise ValueError("Invalid connector recovery pause")


def restore(conn, ledger: dict) -> None:
    state = ledger.get("connector_state")
    if state is None:
        if conn.execute("SELECT 1 FROM mnemion.connectors LIMIT 1").fetchone():
            raise ValueError(
                "Obtain a current connector-aware deletion and access ledger before recovery"
            )
        return
    conn.execute("UPDATE mnemion.connectors SET disabled_at=coalesce(disabled_at,now())")
    for row in state["connections"]:
        conn.execute(
            "UPDATE mnemion.connectors SET disabled_at=%s WHERE tenant_id=%s AND id=%s",
            (row["disabled_at"], row["tenant_id"], row["id"]),
        )
    conn.execute("DELETE FROM mnemion.connector_bindings")
    for row in state["bindings"]:
        conn.execute(
            """INSERT INTO mnemion.connector_bindings(tenant_id,connector_id,external_id,principal_id,role)
            SELECT %s,%s,%s,%s,%s WHERE EXISTS(SELECT FROM mnemion.connectors WHERE tenant_id=%s AND id=%s)
              AND EXISTS(SELECT FROM mnemion.principals WHERE tenant_id=%s AND id=%s)""",
            (
                row["tenant_id"],
                row["connector_id"],
                row["external_id"],
                row["principal_id"],
                row["role"],
                row["tenant_id"],
                row["connector_id"],
                row["tenant_id"],
                row["principal_id"],
            ),
        )
    # A scope first observed after the backup may contain a deletion that still
    # must prevent the next provider scan from recreating its source identity.
    for row in state["scopes"]:
        if not conn.execute(
            "SELECT id FROM mnemion.connectors WHERE tenant_id=%s AND id=%s",
            (row["tenant_id"], row["connector_id"]),
        ).fetchone():
            continue
        if not conn.execute(
            "SELECT space_id FROM mnemion.connector_scopes WHERE tenant_id=%s AND space_id=%s",
            (row["tenant_id"], row["space_id"]),
        ).fetchone():
            conn.execute(
                "INSERT INTO mnemion.spaces(tenant_id,id,name,description) VALUES(%s,%s,'Recovered source scope','Awaiting source permission revalidation')",
                (row["tenant_id"], row["space_id"]),
            )
            conn.execute(
                """INSERT INTO mnemion.connector_scopes(tenant_id,connector_id,space_id,external_id,observed_at,access_valid_until)
                         VALUES(%s,%s,%s,%s,now(),now())""",
                (row["tenant_id"], row["connector_id"], row["space_id"], row["external_id"]),
            )
        conn.execute(
            """UPDATE mnemion.connector_scopes SET operator_paused=%s,suspended_at=now(),
                     suspension_reason='recovery_revalidation_required',access_valid_until=now()
                     WHERE tenant_id=%s AND space_id=%s""",
            (row.get("operator_paused", True), row["tenant_id"], row["space_id"]),
        )
    for row in state["deletions"]:
        if not conn.execute(
            "SELECT space_id FROM mnemion.connector_scopes WHERE tenant_id=%s AND space_id=%s",
            (row["tenant_id"], row["space_id"]),
        ).fetchone():
            continue
        memory = (
            row["memory_id"]
            if conn.execute(
                "SELECT id FROM mnemion.memories WHERE tenant_id=%s AND space_id=%s AND id=%s",
                (row["tenant_id"], row["space_id"], row["memory_id"]),
            ).fetchone()
            else None
        )
        conn.execute(
            """INSERT INTO mnemion.connector_items(tenant_id,space_id,external_id,memory_id,origin_revision,last_seen_run,state)
            VALUES(%s,%s,%s,%s,%s,%s,'deleted') ON CONFLICT(tenant_id,space_id,external_id)
            DO UPDATE SET state='deleted',content_hash=NULL,updated_at=now()""",
            (
                row["tenant_id"],
                row["space_id"],
                row["external_id"],
                memory,
                row["origin_revision"],
                row["last_seen_run"],
            ),
        )
    from .capture_recovery import restore as restore_custody

    restore_custody(conn, state.get("custody"))
