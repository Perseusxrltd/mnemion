"""Administrative PostgreSQL snapshots and isolated, verified recovery.

No HTTP route imports this module. The database owner performs recovery into a
new database, reconciles a current external denial/access ledger, rotates API
keys, and only then publishes the requested database name.
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import os
import re
import shutil
import subprocess
import time
import threading
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Callable
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..archives import canonical_json, private_json, verified_archive, write_archive
from ..local_state import temporary_directory as private_temporary_directory
from ..version import __version__
from .db import migrate, new_token
from .lifecycle import purge_memory
from .models import json_value

BACKUP_FORMAT = "mnemion-postgres-backup"
LEDGER_FORMAT = "mnemion-recovery-ledger"


class RecoveryCancelled(RuntimeError):
    pass


def _cancel(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise RecoveryCancelled("The backup or recovery operation was cancelled.")


@contextmanager
def _cancel_queries(conn, cancelled):
    """Cancel only this operation's SQL connection, including a long sort."""
    if cancelled is None:
        yield
        return
    done = threading.Event()

    def observe():
        while not done.wait(0.25):
            if cancelled():
                try:
                    conn.cancel_safe(timeout=5)
                except psycopg.Error:
                    pass
                return

    observer = threading.Thread(target=observe, name="mnemion-recovery-cancel", daemon=True)
    observer.start()
    try:
        _cancel(cancelled)
        yield
        _cancel(cancelled)
    except psycopg.errors.QueryCanceled:
        _cancel(cancelled)
        raise
    finally:
        done.set()
        observer.join(timeout=6)


def _pg_environment(dsn: str) -> dict[str, str]:
    # Credentials belong in the child environment, never its command line or
    # error message. Preserve libpq connection options used by hosted Postgres.
    options = {
        "dbname": "PGDATABASE",
        "user": "PGUSER",
        "password": "PGPASSWORD",
        "host": "PGHOST",
        "hostaddr": "PGHOSTADDR",
        "port": "PGPORT",
        "service": "PGSERVICE",
        "passfile": "PGPASSFILE",
        "options": "PGOPTIONS",
        "connect_timeout": "PGCONNECT_TIMEOUT",
        "client_encoding": "PGCLIENTENCODING",
        "application_name": "PGAPPNAME",
        "sslmode": "PGSSLMODE",
        "sslcert": "PGSSLCERT",
        "sslkey": "PGSSLKEY",
        "sslrootcert": "PGSSLROOTCERT",
        "sslcrl": "PGSSLCRL",
        "sslcrldir": "PGSSLCRLDIR",
        "sslpassword": "PGSSLPASSWORD",
        "gssencmode": "PGGSSENCMODE",
        "krbsrvname": "PGKRBSRVNAME",
        "target_session_attrs": "PGTARGETSESSIONATTRS",
        "channel_binding": "PGCHANNELBINDING",
        "load_balance_hosts": "PGLOADBALANCEHOSTS",
    }
    environment = os.environ.copy()
    for name, value in conninfo_to_dict(dsn).items():
        if name not in options:
            raise ValueError(f"Unsupported backup connection option: {name}")
        environment[options[name]] = value
    environment.setdefault("PGCONNECT_TIMEOUT", "10")
    return environment


def _pg_tool(name: str, pg_bin: Path | None) -> str:
    if pg_bin is None and os.environ.get("MNEMION_PG_BIN"):
        pg_bin = Path(os.environ["MNEMION_PG_BIN"])
    result = (
        str(pg_bin / (name + (".exe" if os.name == "nt" else ""))) if pg_bin else shutil.which(name)
    )
    if not result or not Path(result).is_file():
        raise ValueError(f"Install PostgreSQL client tools or set --pg-bin; {name} was not found")
    return result


def _run_pg(
    name: str,
    dsn: str,
    arguments: list[str],
    pg_bin: Path | None,
    *,
    cancelled: Callable[[], bool] | None = None,
    maximum_seconds: float = 3600,
    timezone: str | None = None,
) -> None:
    _cancel(cancelled)
    started = time.monotonic()
    environment = _pg_environment(dsn)
    if timezone is not None:
        environment["PGTZ"] = timezone
    process = subprocess.Popen(
        [_pg_tool(name, pg_bin), *arguments],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        while True:
            _cancel(cancelled)
            remaining = maximum_seconds - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("The database backup or recovery tool exceeded its time limit.")
            try:
                code = process.wait(timeout=min(0.25, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
    if code:
        # pg_dump/restore can include source text in diagnostic SQL. Do not emit
        # it into ordinary logs or leak a database connection string.
        raise RuntimeError(
            f"{name} failed (exit {code}); check the PostgreSQL server log and client/server versions"
        )


def _restore_permissions(conn) -> None:
    # ACLs in a pg_dump can refer to the old cluster owner's account. Restore
    # without those ACLs and replay this release's fixed role permissions. Only
    # top-level GRANT/REVOKE statements in packaged, checked migrations apply.
    for path in sorted(
        files("mnemion.service").joinpath("migrations").iterdir(), key=lambda p: p.name
    ):
        if path.name.endswith(".sql"):
            for statement in re.findall(
                r"(?ms)^(?:GRANT|REVOKE)\b.*?;", path.read_text(encoding="utf-8")
            ):
                conn.execute(statement)
    conn.execute("REVOKE ALL ON mnemion.schema_migrations FROM mnemion_app, mnemion_worker")
    conn.execute("GRANT SELECT ON mnemion.schema_migrations TO mnemion_app, mnemion_worker")


def inventory(conn) -> dict:
    """Deterministic content hashes and counts, including all derived state."""
    conn.execute("SET LOCAL timezone='UTC'")
    tables = conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='mnemion' ORDER BY tablename"
    ).fetchall()
    result = {}
    for row in tables:
        table = row["tablename"]
        digest, count = hashlib.sha256(), 0
        # Ordering the complete JSON representation handles every table without
        # assuming a particular primary key, including future schema additions.
        with conn.cursor(name="inventory_" + uuid4().hex) as cursor:
            cursor.execute(
                sql.SQL(
                    'SELECT to_jsonb(t)::text AS row FROM mnemion.{} t ORDER BY to_jsonb(t)::text COLLATE "C"'
                ).format(sql.Identifier(table))
            )
            for item in cursor:
                digest.update(item["row"].encode() + b"\n")
                count += 1
        result[table] = {"count": count, "sha256": digest.hexdigest()}
    return result


def _ledger(conn) -> dict:
    from .application_key_recovery import capture as capture_application_keys
    from .connector_recovery import capture
    from .journal_recovery_ledger import capture as capture_journal
    from .vault_recovery import capture as capture_vault

    journal = capture_journal(conn)
    payload = json_value(
        {
            "format": LEDGER_FORMAT,
            # Older readers must not silently discard a newer quarantine.
            "version": 2 if journal and journal["quarantines"] else 1,
            "snapshot_at": conn.execute("SELECT transaction_timestamp() AS time").fetchone()[
                "time"
            ],
            "tenant_ids": [
                r["id"] for r in conn.execute("SELECT id FROM mnemion.tenants ORDER BY id")
            ],
            "deletions": conn.execute(
                "SELECT * FROM mnemion.recovery_denials ORDER BY tenant_id, memory_id"
            ).fetchall(),
            "principals": conn.execute(
                "SELECT tenant_id, id, disabled_at, administrator FROM mnemion.principals ORDER BY tenant_id, id"
            ).fetchall(),
            "grants": conn.execute(
                "SELECT tenant_id, space_id, principal_id, role, created_at FROM mnemion.space_grants ORDER BY tenant_id, space_id, principal_id"
            ).fetchall(),
            "connector_state": capture(conn),
            "vault_state": capture_vault(conn),
            "application_key_state": capture_application_keys(conn),
            "journal_recovery_state": journal,
        }
    )
    return {**payload, "sha256": hashlib.sha256(canonical_json(payload)).hexdigest()}


def export_ledger(dsn: str, output: Path, *, cancelled=None) -> dict:
    with psycopg.connect(dsn, row_factory=dict_row) as conn, _cancel_queries(conn, cancelled):
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        payload = _ledger(conn)
    _cancel(cancelled)
    private_json(output, payload)
    return {
        "ledger_file": str(output),
        "snapshot_at": payload["snapshot_at"],
        "deletions": len(payload["deletions"]),
    }


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Recovery timestamps must include a timezone")
    return parsed


def read_ledger(path: Path) -> dict:
    if path.stat().st_size > 256 * 1024**2:
        raise ValueError("Recovery ledger exceeds 256 MiB")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("format") != LEDGER_FORMAT
        or type(payload.get("version")) is not int
        or payload["version"] not in (1, 2)
    ):
        raise ValueError("Unsupported recovery ledger")
    digest = payload.pop("sha256", None)
    if hashlib.sha256(canonical_json(payload)).hexdigest() != digest:
        raise ValueError("Recovery ledger checksum mismatch")
    _time(payload["snapshot_at"])
    tenants = {str(UUID(value)) for value in payload["tenant_ids"]}
    for group, id_fields in (
        ("deletions", ("space_id", "memory_id")),
        ("principals", ("id",)),
        ("grants", ("space_id", "principal_id")),
    ):
        if not isinstance(payload[group], list):
            raise ValueError("Invalid recovery ledger entries")
        for row in payload[group]:
            if str(UUID(row["tenant_id"])) not in tenants:
                raise ValueError("Recovery ledger has an unknown tenant")
            for field in id_fields:
                UUID(row[field])
            if group == "deletions":
                _time(row["requested_at"])
            if group == "grants" and row["role"] not in {
                "reader",
                "contributor",
                "reviewer",
                "administrator",
            }:
                raise ValueError("Invalid recovery grant")
    if payload.get("vault_state") is not None:
        from .vault_recovery import validate as validate_vault

        validate_vault(payload["vault_state"], tenants)
    if "connector_state" in payload:
        from .connector_recovery import validate

        validate(payload["connector_state"], tenants)
    if "application_key_state" in payload:
        from .application_key_recovery import validate as validate_application_keys

        validate_application_keys(payload["application_key_state"], tenants)
    if payload.get("journal_recovery_state") is not None:
        from .journal_recovery_ledger import validate as validate_journal

        validate_journal(payload["journal_recovery_state"], tenants)
        if payload["journal_recovery_state"]["quarantines"] and payload["version"] != 2:
            raise ValueError("Journal quarantines require a version 2 recovery ledger")
    elif payload["version"] == 2:
        raise ValueError("A version 2 recovery ledger requires journal quarantine state")
    return {**payload, "sha256": digest}


def create_backup(
    dsn: str,
    output: Path,
    *,
    pg_bin: Path | None = None,
    context: dict | None = None,
    temporary_directory: Path | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict:
    started = time.monotonic()
    _pg_tool("pg_dump", pg_bin)
    if output.exists():
        raise FileExistsError("Backup output already exists")
    if context is not None and (
        not isinstance(context, dict) or len(canonical_json(context)) > 16 * 1024
    ):
        raise ValueError("Backup context must be a bounded metadata object")
    _cancel(cancelled)
    with private_temporary_directory(prefix="mnemion-backup-", dir=temporary_directory) as root:
        with psycopg.connect(dsn, row_factory=dict_row) as conn, _cancel_queries(conn, cancelled):
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            database_timezone = conn.execute(
                "SELECT current_setting('TimeZone') AS zone"
            ).fetchone()["zone"]
            snapshot = conn.execute("SELECT pg_export_snapshot() AS id").fetchone()["id"]
            ledger = _ledger(conn)
            tables = inventory(conn)
            schema = json_value(
                conn.execute(
                    "SELECT name, sha256 FROM mnemion.schema_migrations ORDER BY name"
                ).fetchall()
            )
            server_version = conn.info.server_version
            _run_pg(
                "pg_dump",
                dsn,
                [
                    "--format=custom",
                    "--schema=mnemion",
                    "--no-owner",
                    "--snapshot=" + snapshot,
                    "--file=" + str(root / "database.dump"),
                ],
                pg_bin,
                **({"cancelled": cancelled} if cancelled is not None else {}),
            )
        _cancel(cancelled)
        (root / "deletions.json").write_bytes(canonical_json(ledger))
        manifest = write_archive(
            output,
            {
                "database.dump": root / "database.dump",
                "deletions.json": root / "deletions.json",
            },
            {
                "format": BACKUP_FORMAT,
                "version": 1,
                "application_version": __version__,
                "backup_id": str(uuid4()),
                "snapshot_at": ledger["snapshot_at"],
                "server_version": server_version,
                "database_timezone": database_timezone,
                "schema": schema,
                "tables": tables,
                "tenant_ids": ledger["tenant_ids"],
                **({"context": context} if context is not None else {}),
            },
            check_cancelled=lambda: _cancel(cancelled),
            temporary_directory=root,
        )
    return {
        "backup_file": str(output),
        "backup_id": manifest["backup_id"],
        "snapshot_at": manifest["snapshot_at"],
        "tables": {name: value["count"] for name, value in tables.items()},
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def _reconcile_deletions(conn, ledger: dict) -> int:
    tenants = {str(r["id"]) for r in conn.execute("SELECT id FROM mnemion.tenants")}
    applied = 0
    for entry in ledger["deletions"]:
        if entry["tenant_id"] not in tenants:
            continue
        tenant, space, memory = (UUID(entry[k]) for k in ("tenant_id", "space_id", "memory_id"))
        conn.execute(
            """INSERT INTO mnemion.recovery_denials (tenant_id, space_id, memory_id, requested_at)
               VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""",
            (tenant, space, memory, entry["requested_at"]),
        )
        row = conn.execute(
            "SELECT * FROM mnemion.memories WHERE tenant_id=%s AND id=%s FOR UPDATE",
            (tenant, memory),
        ).fetchone()
        if not row:
            continue  # A deletion of a memory created after the backup is still denied.
        if row["space_id"] != space:
            raise ValueError("Recovery ledger memory scope mismatch")
        conn.execute(
            """UPDATE mnemion.memories SET version=version+CASE WHEN deleted_at IS NULL THEN 1 ELSE 0 END,
               deleted_at=coalesce(deleted_at,%s), updated_at=now() WHERE tenant_id=%s AND id=%s""",
            (entry["requested_at"], tenant, memory),
        )
        conn.execute(
            """UPDATE mnemion.jobs SET state='cancelled', lease_id=NULL, lease_until=NULL
               WHERE tenant_id=%s AND operation_id IN
                 (SELECT id FROM mnemion.operations WHERE tenant_id=%s AND memory_id=%s)
                 AND state IN ('pending','leased','failed')""",
            (tenant, tenant, memory),
        )
        conn.execute(
            """UPDATE mnemion.operations SET state='cancelled', updated_at=now()
               WHERE tenant_id=%s AND memory_id=%s AND state IN ('accepted','indexing','failed')""",
            (tenant, memory),
        )
        receipt = conn.execute(
            "SELECT operation_id FROM mnemion.deletion_receipts WHERE tenant_id=%s AND memory_id=%s",
            (tenant, memory),
        ).fetchone()
        if receipt:
            operation = receipt["operation_id"]
        else:
            operation = uuid4()
            conn.execute(
                """INSERT INTO mnemion.operations (tenant_id, space_id, id, memory_id, kind, state, created_by)
                   VALUES (%s,%s,%s,%s,'delete','ready',%s)""",
                (tenant, space, operation, memory, row["created_by"]),
            )
            conn.execute(
                """INSERT INTO mnemion.deletion_receipts
                   (tenant_id, space_id, memory_id, operation_id, requested_by, requested_at)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (tenant, space, memory, operation, row["created_by"], entry["requested_at"]),
            )
        purge_memory(conn, tenant, space, memory)
        conn.execute(
            "UPDATE mnemion.operations SET state='ready', error_code=NULL, updated_at=now() WHERE tenant_id=%s AND id=%s",
            (tenant, operation),
        )
        applied += 1
    return applied


def _recover_access(conn, ledger: dict, backup_id: str, *, preserve_application_keys=False) -> dict:
    from collections import Counter

    from .application_key_recovery import eligible, retain
    from .connector_recovery import restore
    from .journal_recovery_ledger import restore as restore_journal
    from .vault_recovery import restore as restore_vault

    original_eligible = (
        {(row["tenant_id"], row["id"]) for row in eligible(conn, ledger)}
        if preserve_application_keys
        else set()
    )

    restore(conn, ledger)
    restore_vault(conn, ledger)
    restore_journal(conn, ledger)
    # Git history and restored credentials are not current publication consent.
    # Reapprove the host destination and repair its publisher explicitly.
    conn.execute("""UPDATE mnemion.writeback_settings SET paused=true,version=version+1,
        last_error='recovery_revalidation_required',updated_at=clock_timestamp()""")
    conn.execute("""UPDATE mnemion.writeback_events e SET state='suppressed'
        FROM mnemion.memories m WHERE e.tenant_id=m.tenant_id AND e.space_id=m.space_id
          AND e.memory_id=m.id AND e.action='upsert' AND m.deleted_at IS NOT NULL
          AND e.state IN ('pending','local')""")
    # A restored schedule or key is not current consent to send text to a model.
    conn.execute("""UPDATE mnemion.librarian_settings SET enabled=false,
        network_egress_approved=false,next_run_at=NULL,version=version+1,updated_at=now()""")
    conn.execute("""UPDATE mnemion.librarian_runs SET state='cancelled',
        error_code='recovery_revalidation_required',lease_id=NULL,lease_until=NULL,finished_at=now()
        WHERE state IN ('queued','running')""")
    # A backup is not evidence of current consent for outbound model calls.
    conn.execute("""UPDATE mnemion.space_embedding_settings s SET inference_paused=true,
        version=version+1,updated_at=now() FROM mnemion.embedding_generations g
        WHERE g.id=s.active_generation_id AND g.configuration->>'runtime' IN ('http-openai','http-ollama')""")
    conn.execute("""UPDATE mnemion.reindex_runs SET state='paused',network_egress_approved=false,
        lease_id=NULL,lease_until=NULL,updated_at=now() WHERE state IN ('running','paused')""")
    # Reconcile current grants before issuing new keys; an old backup must not
    # restore a revoked team grant or resurrect a disabled administrator.
    # Provider permissions and checkpoints in an old backup are not proof of
    # current access. Reconnection requires a fresh provider ACL observation.
    conn.execute("""UPDATE mnemion.connector_scopes SET suspended_at=now(),
                 suspension_reason='recovery_revalidation_required',access_valid_until=now()""")
    conn.execute("""UPDATE mnemion.connector_runs SET state='aborted',finished_at=now()
                 WHERE state IN ('running','finalizing')""")
    for principal in ledger["principals"]:
        conn.execute(
            "UPDATE mnemion.principals SET disabled_at=%s, administrator=%s WHERE tenant_id=%s AND id=%s",
            (
                principal["disabled_at"],
                principal["administrator"],
                principal["tenant_id"],
                principal["id"],
            ),
        )
    conn.execute("DELETE FROM mnemion.space_grants")
    for grant in ledger["grants"]:
        conn.execute(
            """INSERT INTO mnemion.space_grants (tenant_id, space_id, principal_id, role, created_at)
               SELECT %s,%s,%s,%s,%s WHERE EXISTS
                 (SELECT FROM mnemion.spaces WHERE tenant_id=%s AND id=%s) AND EXISTS
                 (SELECT FROM mnemion.principals WHERE tenant_id=%s AND id=%s)""",
            (
                grant["tenant_id"],
                grant["space_id"],
                grant["principal_id"],
                grant["role"],
                grant["created_at"],
                grant["tenant_id"],
                grant["space_id"],
                grant["tenant_id"],
                grant["principal_id"],
            ),
        )
    retained = (
        [
            row
            for row in eligible(conn, ledger)
            if (row["tenant_id"], row["id"]) in original_eligible
        ]
        if preserve_application_keys
        else []
    )
    conn.execute("UPDATE mnemion.api_keys SET revoked_at=coalesce(revoked_at,now())")
    retain(conn, retained)
    # A historical snapshot must not revive a password changed after backup.
    # Recovery administrators reenroll people with fresh one-use invitations.
    conn.execute("UPDATE mnemion.password_accounts SET reset_required=true")
    conn.execute(
        "UPDATE mnemion.company_links SET revoked_at=coalesce(revoked_at,clock_timestamp())"
    )
    conn.execute("DELETE FROM mnemion.company_login_requests")
    conn.execute("UPDATE mnemion.sign_in_invitations SET revoked_at=coalesce(revoked_at,now())")
    conn.execute("DELETE FROM mnemion.spent_refresh_tokens")
    conn.execute("DELETE FROM mnemion.oauth_local_requests")
    credentials = []
    retained_by_tenant = Counter(row["tenant_id"] for row in retained)
    for tenant in conn.execute("SELECT id, name FROM mnemion.tenants ORDER BY id").fetchall():
        retained_count = retained_by_tenant[str(tenant["id"])]
        owner = conn.execute(
            """SELECT id FROM mnemion.principals WHERE tenant_id=%s AND administrator
               AND disabled_at IS NULL ORDER BY created_at, id LIMIT 1""",
            (tenant["id"],),
        ).fetchone()
        principal = owner["id"] if owner else uuid4()
        if not owner:
            conn.execute(
                """INSERT INTO mnemion.principals (tenant_id, id, name, kind, administrator)
                   VALUES (%s,%s,'Recovery administrator','human',true)""",
                (tenant["id"], principal),
            )
        key, (token, digest) = uuid4(), new_token()
        conn.execute(
            """INSERT INTO mnemion.api_keys (tenant_id,id,principal_id,name,token_hash,prefix)
               VALUES (%s,%s,%s,'Recovery owner',%s,%s)""",
            (tenant["id"], key, principal, digest, token[:12]),
        )
        conn.execute(
            """INSERT INTO mnemion.audit_events (tenant_id,id,principal_id,action,resource_id,details)
               VALUES (%s,%s,%s,'recovery.completed',%s,%s)""",
            (
                tenant["id"],
                uuid4(),
                principal,
                backup_id,
                Jsonb(
                    {
                        "ledger_sha256": ledger["sha256"],
                        "keys_rotated": not retained_count,
                        "application_keys_preserved": retained_count,
                    }
                ),
            ),
        )
        credentials.append(
            {
                "tenant_id": str(tenant["id"]),
                "tenant_name": tenant["name"],
                "principal_id": str(principal),
                "key_id": str(key),
                "api_key": token,
            }
        )
    result = {"backup_id": backup_id, "organizations": credentials}
    if preserve_application_keys:
        result["preserved_application_keys"] = [
            {"tenant_id": row["tenant_id"], "key_id": row["id"]} for row in retained
        ]
    if len(credentials) == 1:
        result.update(credentials[0])
    return result


def restore_backup(
    dsn: str,
    archive: Path,
    *,
    database_name: str,
    deletion_ledger: Path,
    credentials_output: Path,
    pg_bin: Path | None = None,
    temporary_directory: Path | None = None,
    cancelled: Callable[[], bool] | None = None,
    preserve_application_keys: bool = False,
) -> dict:
    started = time.monotonic()
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", database_name):
        raise ValueError("Use a lowercase PostgreSQL database name of up to 63 characters")
    if credentials_output.exists():
        raise FileExistsError("Recovery credentials output already exists")
    _pg_tool("pg_restore", pg_bin)
    ledger = read_ledger(deletion_ledger)
    if preserve_application_keys:
        from .application_key_recovery import validate as validate_application_keys

        validate_application_keys(ledger.get("application_key_state"), set(ledger["tenant_ids"]))
    with verified_archive(
        archive,
        BACKUP_FORMAT,
        temporary_directory=temporary_directory,
        check_cancelled=lambda: _cancel(cancelled),
    ) as (manifest, root):
        if set(manifest["files"]) != {"database.dump", "deletions.json"}:
            raise ValueError("Incomplete database backup")
        if _time(ledger["snapshot_at"]) < _time(manifest["snapshot_at"]):
            raise ValueError(
                "Recovery requires a deletion/access ledger at least as recent as the backup"
            )
        if not set(manifest["tenant_ids"]) <= set(ledger["tenant_ids"]):
            raise ValueError("Recovery ledger does not cover every backed-up organization")
        expected = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files("mnemion.service").joinpath("migrations").iterdir()
            if p.name.endswith(".sql")
        }
        if not manifest.get("schema") or any(
            expected.get(row["name"]) != row["sha256"] for row in manifest["schema"]
        ):
            raise ValueError(
                "Backup schema is newer than or incompatible with this service release"
            )
        # Validate the embedded ledger too, even when the newer external ledger
        # supersedes it. Archive corruption is never tolerated selectively.
        read_ledger(root / "deletions.json")
        temporary = "mnemion_restore_" + uuid4().hex
        staged_dsn = make_conninfo(dsn, dbname=temporary)
        created = published = False
        with (
            psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as administration,
            _cancel_queries(administration, cancelled),
        ):
            if administration.execute(
                "SELECT 1 FROM pg_database WHERE datname=%s", (database_name,)
            ).fetchone():
                raise ValueError(
                    "Restore only into a new database name; the destination already exists"
                )
            if administration.info.server_version // 10000 < manifest["server_version"] // 10000:
                raise ValueError("Restore requires the same or a newer PostgreSQL major version")
            try:
                administration.execute(
                    sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                        sql.Identifier(temporary)
                    )
                )
                created = True
                # Calendar-day constraints (including session expiry across DST)
                # must be replayed with the source database's timezone. Content
                # inventory still canonicalizes timestamps to UTC separately.
                zone = manifest.get("database_timezone")
                if zone is not None:
                    if (
                        not isinstance(zone, str)
                        or not 1 <= len(zone) <= 100
                        or any(ord(c) < 32 for c in zone)
                    ):
                        raise ValueError("Invalid backup database timezone")
                    administration.execute(
                        sql.SQL("ALTER DATABASE {} SET TimeZone TO {}").format(
                            sql.Identifier(temporary), sql.Literal(zone)
                        )
                    )
                    # A restore operator may also have PGTZ or a timezone in
                    # libpq options. Pin this restore connection explicitly,
                    # retaining other options and escaping libpq whitespace.
                    escaped_zone = "".join(
                        "\\" + c if c.isspace() or c == "\\" else c for c in zone
                    )
                    previous_options = conninfo_to_dict(staged_dsn).get("options", "")
                    staged_dsn = make_conninfo(
                        staged_dsn, options=previous_options + " -c TimeZone=" + escaped_zone
                    )
                with psycopg.connect(staged_dsn) as conn, _cancel_queries(conn, cancelled):
                    conn.execute("CREATE EXTENSION vector")
                    for role in ("mnemion_app", "mnemion_worker"):
                        if not conn.execute(
                            "SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)
                        ).fetchone():
                            conn.execute(
                                sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role))
                            )
                _run_pg(
                    "pg_restore",
                    staged_dsn,
                    [
                        "--exit-on-error",
                        "--single-transaction",
                        "--no-owner",
                        "--no-acl",
                        "--dbname=" + temporary,
                        str(root / "database.dump"),
                    ],
                    pg_bin,
                    timezone=zone,
                    **({"cancelled": cancelled} if cancelled is not None else {}),
                )
                with (
                    psycopg.connect(staged_dsn, row_factory=dict_row) as conn,
                    _cancel_queries(conn, cancelled),
                ):
                    if inventory(conn) != manifest["tables"]:
                        raise ValueError(
                            "Restored table counts or content hashes do not match the backup"
                        )
                migrate(staged_dsn)
                with (
                    psycopg.connect(staged_dsn, row_factory=dict_row) as conn,
                    _cancel_queries(conn, cancelled),
                ):
                    if zone is not None:
                        conn.execute("SELECT set_config('TimeZone', %s, true)", (zone,))
                    _restore_permissions(conn)
                    denied = _reconcile_deletions(conn, ledger)
                    conn.execute(
                        "UPDATE mnemion.jobs SET state='pending', lease_id=NULL, lease_until=NULL, available_at=now() WHERE state='leased'"
                    )
                    conn.execute(
                        "UPDATE mnemion.operations SET state='accepted', updated_at=now() WHERE state='indexing'"
                    )
                    credentials = _recover_access(
                        conn,
                        ledger,
                        manifest["backup_id"],
                        preserve_application_keys=preserve_application_keys,
                    )
                    private_json(credentials_output, credentials)
                administration.execute(
                    sql.SQL("ALTER DATABASE {} RENAME TO {}").format(
                        sql.Identifier(temporary), sql.Identifier(database_name)
                    )
                )
                published = True
            finally:
                if created and not published:
                    administration.execute(
                        sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                            sql.Identifier(temporary)
                        )
                    )
                    # Retain a successfully written private credentials file on
                    # an uncertain rename/connection failure. The operator can
                    # inspect the database outcome without losing its only key.
    return {
        "database_name": database_name,
        "backup_id": manifest["backup_id"],
        "verified_tables": len(manifest["tables"]),
        "deletions_reconciled": denied,
        "credentials_file": str(credentials_output),
        "ledger_at": ledger["snapshot_at"],
        "keys_rotated": not credentials.get("preserved_application_keys"),
        **(
            {"application_keys_preserved": len(credentials["preserved_application_keys"])}
            if preserve_application_keys
            else {}
        ),
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
