"""The journal publisher files notes only under the current approved space policy."""

from ..journal.format import JournalError
from ..journal.git import GitJournal
from ..local_state import LocalSetupError
from .db import require_space
from .errors import ServiceError
from .repository import audit


def organize(service, identity, space, *, expected_version=None):
    with service.db.transaction(identity) as conn:
        require_space(conn, space, 30, writing=True)
        settings = service._settings(conn, space)
        if settings is None or not settings["fold_enabled"]:
            raise ServiceError(
                409, "journal_folding_disabled", "Enable automatic filing for this journal first."
            )
        if expected_version is not None and settings["version"] != expected_version:
            raise ServiceError(
                409, "version_conflict", "The journal policy changed; refresh before retrying."
            )
        if settings["paused"]:
            raise ServiceError(
                409, "journal_paused", "Publication and filing are paused; local capture continues."
            )
        destination = service.destination(identity, space, settings)
        publisher = service._publisher(settings)

    def current():
        with service.db.transaction(publisher) as conn:
            require_space(conn, space, 30, writing=True)
            live = service._settings(conn, space)
            if (
                not live
                or live["version"] != settings["version"]
                or live["paused"]
                or not live["fold_enabled"]
            ):
                raise JournalError("journal_policy_changed")
            if conn.execute(
                """SELECT 1 FROM mnemion.writeback_events
                   WHERE space_id=%s AND state IN ('pending','local') LIMIT 1""",
                (space,),
            ).fetchone():
                raise JournalError("journal_pending_changes")

    try:
        current()
        report = GitJournal(destination, cancel=service._stop).fold(
            after_hours=settings["fold_after_hours"],
            before_push=current,
        )
        with service.db.transaction(publisher) as conn:
            conn.execute(
                """UPDATE mnemion.writeback_settings SET last_fold_at=clock_timestamp(),
                   last_fold_commit=%s,last_fold_error=NULL,last_fold_notes=%s,last_fold_archived_files=%s,
                   last_fold_pending_notes=%s,last_fold_pending_files=%s,last_fold_read_bytes=%s,last_fold_written_bytes=%s,
                   next_fold_at=clock_timestamp()+make_interval(secs=>CASE WHEN %s THEN 60 ELSE fold_interval_seconds END)
                   WHERE space_id=%s AND version=%s""",
                (
                    report["commit"],
                    report["notes"],
                    report["archived_files"],
                    report["pending_notes"],
                    report["pending_files"],
                    report["read_bytes"],
                    report["written_bytes"],
                    bool(report["pending_notes"] or report["pending_files"]),
                    space,
                    settings["version"],
                ),
            )
            # Keep the scheduling/status heartbeat above, but retain an activity
            # receipt only when filing actually changes the journal.
            if report["notes"] or report["archived_files"]:
                audit(
                    conn,
                    publisher,
                    "journal.organized",
                    space,
                    space_id=space,
                    details={
                        key: report[key]
                        for key in (
                            "commit",
                            "notes",
                            "archived_files",
                            "pending_notes",
                            "pending_files",
                        )
                    },
                )
        return report
    except (JournalError, OSError, LocalSetupError) as error:
        code = error.code if isinstance(error, JournalError) else "journal_storage_unavailable"
        with service.db.transaction(publisher) as conn:
            conn.execute(
                "UPDATE mnemion.writeback_settings SET last_fold_error=%s WHERE space_id=%s AND version=%s",
                (code, space, settings["version"]),
            )
        raise ServiceError(
            503,
            code,
            "Journal filing could not finish. Publish pending changes, then check the journal's filing status and repository.",
        ) from None
