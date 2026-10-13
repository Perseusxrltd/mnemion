"""Prevent access removal from stranding an organization without an administrator."""

from .errors import ServiceError


def retain_administrator_access(conn) -> None:
    """Called after an active administrator loses access, in the tenant boundary.

    Count usable credentials, not just administrator rows. OAuth bindings share
    the same revocable key anchors. This proves current database authorization;
    it cannot prove possession of another key or availability of an OAuth issuer.
    A failure rolls back the access removal and its recovery-ledger changes.
    """
    if not conn.execute(
        """SELECT EXISTS (
             SELECT FROM mnemion.principals p JOIN mnemion.api_keys k
               ON k.tenant_id=p.tenant_id AND k.principal_id=p.id
             WHERE p.tenant_id=mnemion.tenant() AND p.administrator
               AND p.disabled_at IS NULL AND k.revoked_at IS NULL
               AND NOT k.session_key
               AND (k.expires_at IS NULL OR k.expires_at > clock_timestamp())
           ) AS available"""
    ).fetchone()["available"]:
        raise ServiceError(
            409,
            "last_administrator_access",
            "Keep at least one active administrator credential. Create and verify "
            "replacement administrator access before removing this access.",
        )
