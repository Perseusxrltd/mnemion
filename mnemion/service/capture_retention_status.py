"""Permission-scoped, time-bounded observation of scheduled capture cleanup."""

from psycopg.errors import LockNotAvailable, QueryCanceled

from .errors import ServiceError, not_found
from .models import json_value


def observe(database, identity, connector_id, source_id):
    try:
        with database.transaction(identity, timeout=1) as conn:
            conn.execute("SET LOCAL statement_timeout='2000ms'")
            if not conn.execute(
                "SELECT 1 FROM mnemion.capture_sources WHERE connector_id=%s AND source_id=%s",
                (connector_id, source_id),
            ).fetchone():
                raise not_found()
            totals = conn.execute(
                """SELECT count(*) AS families,
                   count(*) FILTER(WHERE state<>'expired') AS pending_families,
                   count(*) FILTER(WHERE state<>'expired' AND expires_at<=clock_timestamp()) AS due_families,
                   count(*) FILTER(WHERE state='expired') AS expired_families,
                   count(*) FILTER(WHERE state<>'expired' AND error_code IS NOT NULL) AS failed_families,
                   min(expires_at) FILTER(WHERE state<>'expired') AS next_deadline,
                   max(completed_at) AS last_cleanup_at,clock_timestamp() AS observed_at
                   FROM mnemion.capture_expiries WHERE source_id=%s""",
                (source_id,),
            ).fetchone()
            pending = conn.execute(
                "SELECT mnemion.capture_purges_pending(%s) AS n",
                (source_id,),
            ).fetchone()["n"]
            error = conn.execute(
                """SELECT error_code FROM mnemion.capture_expiries WHERE source_id=%s
                   AND state<>'expired' AND error_code IS NOT NULL ORDER BY expires_at LIMIT 1""",
                (source_id,),
            ).fetchone()
            return json_value(
                {
                    "source_id": source_id,
                    **totals,
                    "purges_pending": pending,
                    "error_code": error["error_code"] if error else None,
                    "semantics": "scheduled_cleanup",
                    "backup_erasure": "not_included",
                }
            )
    except (LockNotAvailable, QueryCanceled):
        raise ServiceError(
            503,
            "capture_retention_busy",
            "Retention observations are busy; keep the last saved observation.",
        ) from None
