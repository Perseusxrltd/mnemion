"""Scoped withdrawal checks shared by memory details and the write boundary."""

from .db import require_space
from .errors import ServiceError, not_found


def allowed(conn, identity, memory: dict) -> bool:
    grants = conn.execute(
        "SELECT mnemion.authorized(%s,20) AS contributor, mnemion.authorized(%s,30) AS reviewer",
        (memory["space_id"], memory["space_id"]),
    ).fetchone()
    if grants["reviewer"]:
        return True
    if (
        not grants["contributor"]
        or memory["review_state"] != "ordinary"
        or memory["created_by"] != identity.principal_id
    ):
        return False
    if memory["deleted_at"]:
        # Revision history is intentionally erased by physical purge. A prior
        # deletion cannot become author-authorized merely because it is empty.
        return bool(
            conn.execute(
                "SELECT 1 FROM mnemion.deletion_receipts WHERE memory_id=%s AND requested_by=%s",
                (memory["id"], identity.principal_id),
            ).fetchone()
        )
    current = conn.execute(
        "SELECT claim_status FROM mnemion.memory_revisions WHERE memory_id=%s AND id=%s",
        (memory["id"], memory["current_revision_id"]),
    ).fetchone()
    if not current or current["claim_status"] == "verified":
        return False
    return not conn.execute(
        "SELECT 1 FROM mnemion.memory_revisions WHERE memory_id=%s AND created_by IS DISTINCT FROM %s LIMIT 1",
        (memory["id"], identity.principal_id),
    ).fetchone()


def target(conn, identity, memory_id, *, lock=False) -> dict:
    row = conn.execute(
        "SELECT * FROM mnemion.memories WHERE id=%s" + (" FOR UPDATE" if lock else ""),
        (memory_id,),
    ).fetchone()
    if not row:
        raise not_found()
    require_space(conn, row["space_id"], 20)
    if (
        row["review_state"] != "ordinary"
        and not conn.execute(
            "SELECT mnemion.authorized(%s,30) AS reviewer", (row["space_id"],)
        ).fetchone()["reviewer"]
    ):
        raise not_found()
    if not allowed(conn, identity, row):
        raise ServiceError(
            403,
            "requires_reviewer",
            "Reviewer access is required. Contributors can withdraw only their own ordinary, unverified memories with no revisions by another identity.",
        )
    return row
