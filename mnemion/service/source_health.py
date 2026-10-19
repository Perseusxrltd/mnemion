"""Source freshness for the caller's own grants, without provider paths or ACL leaks."""

from datetime import datetime, timezone


def source_health(conn, selected=None) -> dict:
    result = conn.execute("SELECT * FROM mnemion.source_health(%s::uuid[])", (selected,)).fetchone()
    attention = []
    if result["unavailable_scopes"]:
        attention.append("connector_scope_suspended")
    if result["incomplete_scopes"]:
        attention.append("connector_inventory_incomplete")
    return {**result, "attention": attention, "observed_at": datetime.now(timezone.utc).isoformat()}
