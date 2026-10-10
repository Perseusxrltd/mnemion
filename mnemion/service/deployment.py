"""Container entry points with separate runtime and operator credentials.

Only the short-lived initialize/operator containers receive the database-owner
secret. API and worker containers each mount a different private credentials
volume. These commands never print credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from ..archives import private_json
from .admin import bootstrap_tenant
from .db import Database, migrate
from .errors import ServiceError

RUNTIME_UID = 10001
RUNTIME_GID = 10001
SETUP_LOCK = 731293284010


class DeploymentError(ValueError):
    """An operator-facing diagnostic containing no provider or database secrets."""


def _read_json(path: Path, *, max_bytes: int = 65536) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        raise DeploymentError("Deployment state must be a small regular file")
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise DeploymentError("Invalid deployment state")
    return result


def _activation(state: Path) -> dict | None:
    path = state / "operator" / "active.json"
    if not path.exists() and not path.is_symlink():
        return None
    value = _read_json(path)
    if (
        value.get("version") != 1
        or not isinstance(value.get("database"), str)
        or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", value["database"])
        or not isinstance(value.get("owner"), dict)
    ):
        raise DeploymentError("Invalid database activation record; restore the operator state")
    return value


def _admin_dsn(database: str | None = None) -> str:
    secret = Path(
        os.environ.get("MNEMION_DATABASE_PASSWORD_FILE", "/run/secrets/database_password")
    )
    if not secret.is_file() or secret.stat().st_size > 4096:
        raise DeploymentError("A database password secret file is required")
    password = secret.read_text(encoding="utf-8").strip()
    if len(password) < 32 or "\x00" in password:
        raise DeploymentError("Use a database password of at least 32 characters")
    if database is None:
        active = _activation(Path(os.environ.get("MNEMION_DEPLOYMENT_STATE", "/state")))
        database = (
            active["database"] if active else os.environ.get("MNEMION_PG_DATABASE", "mnemion")
        )
    return make_conninfo(
        host=os.environ.get("MNEMION_PG_HOST", "database"),
        port=os.environ.get("MNEMION_PG_PORT", "5432"),
        dbname=database,
        user=os.environ.get("MNEMION_PG_USER", "postgres"),
        password=password,
        connect_timeout=10,
    )


def _directory(path: Path) -> None:
    if path.is_symlink():
        raise DeploymentError("Deployment state directories cannot be symlinks")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    if os.name == "posix" and os.geteuid() == 0:
        os.chown(path, RUNTIME_UID, RUNTIME_GID)


def _runtime_credentials(path: Path, values: dict) -> None:
    """Publish derived role credentials; never replace the operator's source keys."""
    if path.is_symlink():
        raise DeploymentError("Credentials cannot be symlinks")
    descriptor, name = tempfile.mkstemp(prefix=".credentials-", dir=path.parent)
    staged = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(values, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if os.name == "posix" and os.geteuid() == 0:
            os.chown(staged, RUNTIME_UID, RUNTIME_GID)
        os.replace(staged, path)
        if os.name == "posix":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        staged.unlink(missing_ok=True)


def _validate_url(api_url: str) -> None:
    address = urlsplit(api_url)
    if (
        address.scheme not in {"http", "https"}
        or not address.hostname
        or address.username
        or address.password
        or address.query
        or address.fragment
        or (address.scheme == "http" and address.hostname not in {"localhost", "127.0.0.1", "::1"})
    ):
        raise DeploymentError("Public URL requires HTTPS or a loopback HTTP address")


def initialize(dsn: str, state: Path, *, tenant: str, owner: str, api_url: str) -> dict:
    """Resume initialization without rotating keys or creating another tenant.

    The private role manifest is written before its transaction so an interrupted
    CREATE ROLE can replay using the same secrets. Existing roles must authenticate
    with those secrets; an unrelated or restored database is never silently adopted.
    """
    for name in (tenant, owner):
        if not 1 <= len(name.strip()) <= 200:
            raise DeploymentError("Tenant and owner names must contain 1–200 characters")
    _validate_url(api_url)
    for name in ("operator", "api", "worker"):
        _directory(state / name)
    roles_path = state / "operator" / "roles.json"
    owner_path = state / "operator" / "owner.json"
    active = _activation(state)
    if active and conninfo_to_dict(dsn).get("dbname") != active["database"]:
        raise DeploymentError("Database and activation record differ; use the active database")
    with psycopg.connect(dsn, autocommit=True) as lock:
        lock.execute("SELECT pg_advisory_lock(%s)", (SETUP_LOCK,))
        try:
            applied = migrate(dsn)
            if not roles_path.exists():
                if lock.execute("SELECT count(*) FROM mnemion.tenants").fetchone()[0]:
                    raise DeploymentError(
                        "Existing database needs its original operator state; see recovery instructions"
                    )
                names = ["mnemion_api_login", "mnemion_worker_login"]
                if lock.execute(
                    "SELECT 1 FROM pg_roles WHERE rolname=ANY(%s)", (names,)
                ).fetchone():
                    raise DeploymentError(
                        "Existing database roles need their original operator state"
                    )
                private_json(
                    roles_path,
                    {
                        "version": 1,
                        "passwords": {name: secrets.token_urlsafe(32) for name in names},
                    },
                )
            roles = _read_json(roles_path)
            passwords = roles.get("passwords", {})
            if roles.get("version") != 1 or set(passwords) != {
                "mnemion_api_login",
                "mnemion_worker_login",
            }:
                raise DeploymentError("Unrecognized operator role manifest")
            credentials = {}
            with lock.transaction():
                for name, group, key in (
                    ("mnemion_api_login", "mnemion_app", "database_url"),
                    ("mnemion_worker_login", "mnemion_worker", "worker_database_url"),
                ):
                    password = passwords[name]
                    if not isinstance(password, str) or not 32 <= len(password) <= 256:
                        raise DeploymentError("Invalid role credential in operator state")
                    if not lock.execute(
                        "SELECT 1 FROM pg_roles WHERE rolname=%s", (name,)
                    ).fetchone():
                        lock.execute(
                            sql.SQL(
                                "CREATE ROLE {} LOGIN NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {} IN ROLE {}"
                            ).format(
                                sql.Identifier(name), sql.Literal(password), sql.Identifier(group)
                            )
                        )
                    credentials[key] = make_conninfo(dsn, user=name, password=password)
            for key in ("database_url", "worker_database_url"):
                database = Database(credentials[key], worker=key.startswith("worker"))
                database.open()
                database.close()
            if active or owner_path.exists():
                existing = active["owner"] if active else _read_json(owner_path)
                if not lock.execute(
                    "SELECT 1 FROM mnemion.tenants t JOIN mnemion.principals p ON p.tenant_id=t.id WHERE t.id=%s AND p.id=%s",
                    (existing.get("tenant_id"), existing.get("principal_id")),
                ).fetchone():
                    raise DeploymentError(
                        "Owner state and database differ; reconcile the interrupted setup before starting"
                    )
                result = existing
            else:
                if lock.execute("SELECT count(*) FROM mnemion.tenants").fetchone()[0]:
                    raise DeploymentError(
                        "Owner state is missing for an existing database; restore it, do not bootstrap again"
                    )
                result = bootstrap_tenant(
                    dsn,
                    tenant_name=tenant,
                    administrator_name=owner,
                    credentials_sink=lambda values: private_json(
                        owner_path, {**values, "api_url": api_url}
                    ),
                )
            if active:
                # The activation record is the single commit point. A restart
                # repairs derived files after a crash between their publications.
                _runtime_credentials(owner_path, result)
            _runtime_credentials(
                state / "api" / "credentials.json", {"database_url": credentials["database_url"]}
            )
            _runtime_credentials(
                state / "worker" / "credentials.json",
                {"worker_database_url": credentials["worker_database_url"]},
            )
            return {
                "initialized": True,
                "tenant_id": result["tenant_id"],
                "applied_migrations": applied,
            }
        finally:
            lock.execute("SELECT pg_advisory_unlock(%s)", (SETUP_LOCK,))


def adopt_restored(
    dsn: str, state: Path, recovered: dict, *, api_url: str, tenant_id: str | None = None
) -> dict:
    """Activate a verified restore while preserving the previous operator state.

    The host must stop the API and workers before this explicit cutover. No
    database is renamed, dropped, bootstrapped, or given new grants here. A single
    fsynced activation record selects the database and owner credentials; all
    runtime files are derived from it by initialize, including after interruption.
    """
    _validate_url(api_url)
    database_name = conninfo_to_dict(dsn).get("dbname", "")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", database_name):
        raise DeploymentError("Use a lowercase PostgreSQL database name of up to 63 characters")
    backup_id = str(UUID(recovered.get("backup_id", "")))
    organizations = recovered.get("organizations")
    if not isinstance(organizations, list) or not organizations:
        raise DeploymentError("Use the credential file produced by a verified service restore")
    current = _activation(state)
    owner = current["owner"] if current else _read_json(state / "operator" / "owner.json")
    selected = str(UUID(tenant_id or owner.get("tenant_id", "")))
    matches = [
        item
        for item in organizations
        if isinstance(item, dict) and item.get("tenant_id") == selected
    ]
    if len(matches) != 1:
        raise DeploymentError(
            "Recovery credentials must contain the selected deployment organization"
        )
    candidate = {**matches[0], "api_url": api_url}
    roles = _read_json(state / "operator" / "roles.json")
    passwords = roles.get("passwords", {})
    if roles.get("version") != 1 or set(passwords) != {"mnemion_api_login", "mnemion_worker_login"}:
        raise DeploymentError("Original database role credentials are required for cutover")
    for name, worker in (("mnemion_api_login", False), ("mnemion_worker_login", True)):
        role_dsn = make_conninfo(dsn, user=name, password=passwords[name])
        checked = Database(role_dsn, worker=worker)
        checked.open()
        try:
            if not worker:
                try:
                    identity = checked.authenticate(candidate.get("api_key", ""))
                except ServiceError as exc:
                    raise DeploymentError(
                        "Recovery credentials do not authenticate against the destination"
                    ) from exc
                if str(identity.tenant_id) != selected or str(
                    identity.principal_id
                ) != candidate.get("principal_id"):
                    raise DeploymentError(
                        "Recovery credentials identify a different organization or owner"
                    )
                with checked.transaction(identity) as conn:
                    if not conn.execute("SELECT mnemion.administrator() AS allowed").fetchone()[
                        "allowed"
                    ]:
                        raise DeploymentError(
                            "Recovery credentials must belong to an active administrator"
                        )
                    if not conn.execute(
                        "SELECT 1 FROM mnemion.audit_events WHERE tenant_id=%s AND principal_id=%s AND action='recovery.completed' AND resource_id=%s",
                        (identity.tenant_id, identity.principal_id, backup_id),
                    ).fetchone():
                        raise DeploymentError(
                            "Destination has no matching completed recovery record"
                        )
        finally:
            checked.close()
    active = {"version": 1, "database": database_name, "backup_id": backup_id, "owner": candidate}
    if current != active:
        previous = current or {
            "version": 1,
            "database": conninfo_to_dict(
                _read_json(state / "api" / "credentials.json")["database_url"]
            )["dbname"],
            "owner": owner,
        }
        history = state / "operator" / "history"
        _directory(history)
        private_json(
            history / ("before-" + uuid4().hex + ".json"),
            previous,
        )
        _runtime_credentials(state / "operator" / "active.json", active)
    initialized = initialize(
        dsn, state, tenant="Recovered organization", owner="Recovery owner", api_url=api_url
    )
    return {
        "activated": True,
        "database": database_name,
        "backup_id": backup_id,
        "tenant_id": initialized["tenant_id"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("initialize", "api", "worker", "model", "operator", "adopt-restored")
    )
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        from .cli import main as service

        state = Path(os.environ.get("MNEMION_DEPLOYMENT_STATE", "/state"))
        if args.mode == "adopt-restored":
            adoption = argparse.ArgumentParser(description="Activate a verified restored database")
            adoption.add_argument("--database", required=True)
            adoption.add_argument("--credentials", type=Path, required=True)
            adoption.add_argument("--tenant-id")
            selected = adoption.parse_args(args.arguments)
            print(
                json.dumps(
                    adopt_restored(
                        _admin_dsn(selected.database),
                        state,
                        _read_json(selected.credentials, max_bytes=16 * 1024 * 1024),
                        api_url=os.environ.get("MNEMION_PUBLIC_URL", "http://127.0.0.1:7892"),
                        tenant_id=selected.tenant_id,
                    )
                )
            )
            return 0
        if args.mode == "initialize":
            _directory(Path(os.environ.get("MNEMION_MODEL_CACHE", "/models")))
            print(
                json.dumps(
                    initialize(
                        _admin_dsn(),
                        state,
                        tenant=os.environ.get("MNEMION_TENANT", "My organization"),
                        owner=os.environ.get("MNEMION_OWNER", "Owner"),
                        api_url=os.environ.get("MNEMION_PUBLIC_URL", "http://127.0.0.1:7892"),
                    )
                )
            )
            return 0
        if args.mode == "operator":
            os.environ["MNEMION_ADMIN_DATABASE_URL"] = _admin_dsn()
            # Linux bind-mounted backups must belong to the operator on the host.
            # The owner password is read before dropping the setup privileges.
            if os.name == "posix" and os.geteuid() == 0:
                uid = int(os.environ.get("MNEMION_OPERATOR_UID", "1000"))
                gid = int(os.environ.get("MNEMION_OPERATOR_GID", "1000"))
                if uid < 1 or gid < 1:
                    raise DeploymentError("Operator UID and GID must be non-root identities")
                os.setgroups([])
                os.setgid(gid)
                os.setuid(uid)
            return service(args.arguments)
        if os.name == "posix" and os.geteuid() == 0:
            raise DeploymentError(
                "Runtime containers must run as the unprivileged application user"
            )
        if args.mode == "model":
            return service(["prepare-model"])
        os.environ["MNEMION_MODEL_OFFLINE"] = "1"
        credentials = state / args.mode / "credentials.json"
        if args.mode == "worker":
            return service(["--credentials", str(credentials), "worker", *args.arguments])
        # Verify the pinned cache before serving a healthy application.
        from .cli import _model

        _model().prepare()
        return service(
            [
                "--credentials",
                str(credentials),
                "serve",
                "--host",
                "0.0.0.0",
                "--studio",
                "/opt/mnemion/studio",
                *args.arguments,
            ]
        )
    except DeploymentError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError, psycopg.Error):
        # Database exceptions can contain passwords/DSNs and source content.
        print(
            "Deployment command failed. Check service health, private state, database access and the deployment recovery guide.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
