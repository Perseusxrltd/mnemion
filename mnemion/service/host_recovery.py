"""Journaled host restoration into a new database and private directory.

The source archive supplies data and settings, never executable commands.
Cluster credentials remain in the invoking process. A new restricted database
owner is saved for managed backups; source runners get only their own keys.
"""

from __future__ import annotations

from contextlib import nullcontext
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import sys
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from ..archives import canonical_json, private_json, publish_file
from ..connectors.config import GitConfig
from ..connectors.providers import GitProvider, ProviderError, _permission_denied
from ..private_output import private_output
from . import recovery, service_updates, supervision, update_state
from .db import new_token, token_hash
from .host_package import HostRecoveryError, opened, opened_ledger, public_plan, read_private


def _json(path):
    return json.loads(read_private(path))


def _once(path: Path, value: bytes):
    if path.exists() or path.is_symlink():
        if read_private(path, 8 * 1024**2) != value:
            raise HostRecoveryError(
                "A restored file changed; it was preserved. Review it before resuming."
            )
        return
    temporary = path.parent / (".host-" + uuid4().hex)
    try:
        with private_output(temporary) as stream:
            stream.write(value)
        publish_file(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _replace_paths(value, files, mappings):
    if isinstance(value, str):
        if value in files:
            return files[value]
        for before, after in mappings:
            if value == before or value.startswith(before + os.sep):
                return after + value[len(before) :]
        return value
    if isinstance(value, list):
        return [_replace_paths(item, files, mappings) for item in value]
    if isinstance(value, dict):
        return {key: _replace_paths(item, files, mappings) for key, item in value.items()}
    return value


_REMOTE_GIT_CACHE_CODES = frozenset(
    {
        "git_cache_ancestor_inaccessible",
        "git_cache_ancestor_unusable",
        "git_cache_ancestor_invalid",
        "git_cache_inaccessible",
        "git_cache_invalid",
        "git_cache_not_bare",
        "git_cache_remote_mismatch",
        "git_cache_mapping_invalid",
        "provider_command_unavailable",
        "provider_output_too_large",
    }
)


def _fixed_cache_code(code: str) -> str:
    if code not in _REMOTE_GIT_CACHE_CODES:
        return "git_cache_invalid"
    return code


def _cache_failure(code: str) -> HostRecoveryError:
    return HostRecoveryError("provider.path: " + _fixed_cache_code(code))


def _saved_connector_id(item) -> str | None:
    if not isinstance(item, dict):
        return None
    identifier = item.get("id")
    if not isinstance(identifier, str):
        return None
    try:
        return str(UUID(identifier))
    except (ValueError, AttributeError, TypeError):
        return None


def _classified_connector_ledger(ledger):
    """Map each connection id to whether that connection is explicitly disabled.

    None means this ledger cannot classify connectors, so a cache failure stays
    immediate. A classified map is the connection list recovery applies: a saved
    connection that is disabled or absent stays inactive. An enabled connection
    remains unresolved until its saved key is reviewed. This does not enable a
    connector, issue a key, or read a credential.
    """
    if not isinstance(ledger, dict):
        return None
    state = ledger.get("connector_state")
    if (
        not isinstance(state, dict)
        or state.get("version") not in (1, 2, 3)
        or not isinstance(state.get("connections"), list)
    ):
        return None
    classified = {}
    for row in state["connections"]:
        if not isinstance(row, dict) or "disabled_at" not in row:
            return None
        identifier = row.get("id")
        if not isinstance(identifier, str):
            return None
        try:
            key = str(UUID(identifier))
        except (ValueError, AttributeError, TypeError):
            return None
        if key in classified:
            return None
        classified[key] = row.get("disabled_at") is not None
    return classified


def _asset_targets(assets, root: Path) -> dict:
    """Same asset substitution restore will apply, without creating directories."""
    files = {}
    if not isinstance(assets, list):
        return files
    try:
        asset_root = (root / "assets").resolve()
    except OSError as exc:
        code = (
            "git_cache_ancestor_inaccessible"
            if _permission_denied(exc)
            else "git_cache_ancestor_invalid"
        )
        raise _cache_failure(code) from None
    except RuntimeError:
        raise _cache_failure("git_cache_ancestor_invalid") from None
    for item in assets:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            continue
        target = str(asset_root / item["id"])
        files["@" + item["id"]] = target
        source = item.get("source")
        if isinstance(source, str) and source:
            files[source] = target
    return files


def _remote_git_cache_code(item, files, mappings) -> str | None:
    """Fixed code for one saved remote Git cache, or None when this entry has none."""
    config = item.get("config")
    if not isinstance(config, dict):
        return None
    provider = _replace_paths(config, files, mappings).get("provider")
    if not isinstance(provider, dict) or provider.get("type") != "git":
        return None
    remote = provider.get("remote")
    if remote is None or remote == "":
        return None
    path_text = provider.get("path")
    if (
        not isinstance(remote, str)
        or not isinstance(path_text, str)
        or not path_text
        or any(ord(char) < 32 for char in remote + path_text)
        or not Path(path_text).is_absolute()
    ):
        return "git_cache_mapping_invalid"
    try:
        git_config = GitConfig(
            path=Path(path_text),
            remote=remote,
            scope_id="cache-preflight",
            name="cache-preflight",
            members=[],
            publish_to_mapped_members=True,
        )
    except ValueError:
        return "git_cache_mapping_invalid"
    try:
        GitProvider(git_config).inspect_remote_cache()
    except ProviderError as exc:
        return _fixed_cache_code(exc.code)
    except UnicodeDecodeError:
        return "git_cache_invalid"
    except OSError as exc:
        if _permission_denied(exc):
            return "git_cache_inaccessible"
        return "git_cache_invalid"
    return None


def require_remote_git_caches(connectors, assets, mappings, root: Path, ledger=None):
    """Read local Git caches without creating them or deciding key eligibility.

    Supervised restore runs as the invoking account and does not switch users.
    An absent remote cache is allowed when an existing ancestor can hold the
    provider's normal parent and cache creation. The leaf is not created here.
    An existing bare repository or working tree must match its configured
    origin and have writable Git metadata. On a classified connector ledger,
    a saved connection that is explicitly disabled or absent is skipped and is
    not enabled or rekeyed. An enabled connection whose key is still unresolved
    contributes a fixed code and does not abort restore. Passing does not
    clone, fetch, authorize the remote, or complete a scan. Local Git and other
    providers may still refer to storage created elsewhere.
    """
    if not isinstance(connectors, list):
        raise _cache_failure("git_cache_mapping_invalid")
    files = _asset_targets(assets, root)
    classified = _classified_connector_ledger(ledger)
    deferred = {}
    for item in connectors:
        if not isinstance(item, dict):
            raise _cache_failure("git_cache_mapping_invalid")
        identifier = _saved_connector_id(item)
        if (
            classified is not None
            and identifier is not None
            and (identifier not in classified or classified[identifier])
        ):
            continue
        code = _remote_git_cache_code(item, files, mappings)
        if code is None:
            continue
        if classified is not None and identifier is not None and not classified[identifier]:
            deferred[identifier] = code
            continue
        raise _cache_failure(code)
    return deferred


def _restored_database(dsn, name, owner_file: Path, plan):
    with psycopg.connect(dsn) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", (name,)
        ).fetchone()
    if not exists:
        return False
    if not owner_file.exists():
        raise HostRecoveryError(
            "The destination database already exists without this restore's credentials."
        )
    saved = _json(owner_file)
    if saved.get("backup_id") != plan["backup_id"]:
        raise HostRecoveryError("Existing recovery credentials belong to another backup.")
    with psycopg.connect(make_conninfo(dsn, dbname=name)) as connection:
        for item in saved["organizations"]:
            if not connection.execute(
                """SELECT 1 FROM mnemion.api_keys k JOIN mnemion.audit_events a
                ON a.tenant_id=k.tenant_id AND a.principal_id=k.principal_id
                WHERE k.tenant_id=%s AND k.id=%s AND k.token_hash=%s
                  AND a.action='recovery.completed' AND a.resource_id=%s""",
                (item["tenant_id"], item["key_id"], token_hash(item["api_key"]), plan["backup_id"]),
            ).fetchone():
                raise HostRecoveryError(
                    "The existing database does not match this journaled recovery."
                )
    return True


def _runtime_connection(dsn, name, host=None, port=None):
    # A cluster operator can authenticate with peer, a passfile or a client
    # certificate. New limited logins use their own passwords; never save the
    # operator's authentication material or session/role overrides with them.
    allowed = {
        "host",
        "hostaddr",
        "port",
        "sslmode",
        "sslrootcert",
        "sslcrl",
        "sslcrldir",
        "sslsni",
        "ssl_min_protocol_version",
        "ssl_max_protocol_version",
        "channel_binding",
        "gssencmode",
        "keepalives",
        "keepalives_idle",
        "keepalives_interval",
        "keepalives_count",
        "tcp_user_timeout",
        "target_session_attrs",
    }
    value = {key: item for key, item in conninfo_to_dict(dsn).items() if key in allowed}
    if host is not None:
        if not isinstance(host, str) or not host or any(ord(c) < 32 for c in host):
            raise HostRecoveryError("Use a PostgreSQL hostname, IP address or socket directory.")
        value["host"] = host
        value.pop("hostaddr", None)
    if port is not None:
        if type(port) is not int or not 1 <= port <= 65535:
            raise HostRecoveryError("Choose a PostgreSQL port from 1 to 65535.")
        value["port"] = str(port)
    return make_conninfo(dbname=name, connect_timeout="5", **value)


def _database_roles(dsn, runtime_dsn, name, root, request):
    output = root / "database-credentials.json"
    restore_id = UUID(request["restore_id"])
    prefix = "mnmh_" + restore_id.hex[:20]
    if not output.exists():
        credentials = {}
        for role, field in (
            ("owner", "admin_database_url"),
            ("api", "database_url"),
            ("worker", "worker_database_url"),
        ):
            credentials[field] = make_conninfo(
                runtime_dsn,
                dbname=name,
                user=prefix + "_" + role,
                password=secrets.token_urlsafe(32),
            )
        private_json(output, credentials)
    credentials = _json(output)
    owner = prefix + "_owner"
    marker = "mnemion-host-restore:" + str(restore_id)
    with psycopg.connect(make_conninfo(dsn, dbname=name), row_factory=dict_row) as connection:
        for role, field in (
            ("owner", "admin_database_url"),
            ("api", "database_url"),
            ("worker", "worker_database_url"),
        ):
            login = prefix + "_" + role
            saved = conninfo_to_dict(credentials[field])
            if saved.get("user") != login or service_updates._target(
                credentials[field]
            ) != service_updates._target(runtime_dsn):
                raise HostRecoveryError("The saved database logins do not belong to this recovery.")
            existing = connection.execute(
                """SELECT rolcanlogin,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,
                shobj_description(oid,'pg_authid') AS marker FROM pg_roles WHERE rolname=%s""",
                (login,),
            ).fetchone()
            if existing:
                if (
                    existing["marker"] != marker
                    or not existing["rolcanlogin"]
                    or any(
                        existing[key]
                        for key in ("rolsuper", "rolbypassrls", "rolcreatedb", "rolcreaterole")
                    )
                ):
                    raise HostRecoveryError(
                        "An unrelated or privileged database role occupies this recovery name."
                    )
            else:
                connection.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {}"
                    ).format(sql.Identifier(login), sql.Literal(saved["password"]))
                )
                connection.execute(
                    sql.SQL("COMMENT ON ROLE {} IS {}").format(
                        sql.Identifier(login), sql.Literal(marker)
                    )
                )
                if role in {"api", "worker"}:
                    group = "mnemion_app" if role == "api" else "mnemion_worker"
                    connection.execute(
                        sql.SQL("GRANT {} TO {}").format(
                            sql.Identifier(group), sql.Identifier(login)
                        )
                    )
        connection.execute(
            sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
                sql.Identifier(name), sql.Identifier(owner)
            )
        )
        connection.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(name))
        )
        for role in ("api", "worker"):
            connection.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(name), sql.Identifier(prefix + "_" + role)
                )
            )
        connection.execute(
            sql.SQL("ALTER SCHEMA mnemion OWNER TO {}").format(sql.Identifier(owner))
        )
        # Reassign only this schema's objects. REASSIGN OWNED would also affect
        # unrelated databases/tablespaces owned by the cluster administrator.
        relations = connection.execute(
            """SELECT c.relname,c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='mnemion' AND c.relkind IN ('r','p','S','v','m','f')"""
        ).fetchall()
        for item in relations:
            kind = {
                "S": "SEQUENCE",
                "v": "VIEW",
                "m": "MATERIALIZED VIEW",
                "f": "FOREIGN TABLE",
            }.get(item["relkind"], "TABLE")
            connection.execute(
                sql.SQL("ALTER {} mnemion.{} OWNER TO {}").format(
                    sql.SQL(kind), sql.Identifier(item["relname"]), sql.Identifier(owner)
                )
            )
        functions = connection.execute(
            """SELECT format('ALTER %%s %%s OWNER TO %%I',
              CASE p.prokind WHEN 'a' THEN 'AGGREGATE' WHEN 'p' THEN 'PROCEDURE' ELSE 'FUNCTION' END,
              p.oid::regprocedure,%s::text) AS command FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
              WHERE n.nspname='mnemion'""",
            (owner,),
        ).fetchall()
        for item in functions:
            connection.execute(item["command"])
    return credentials, output


def _ledger_key_index(ledger):
    state = ledger.get("application_key_state", {"keys": []}) if isinstance(ledger, dict) else {}
    keys = state.get("keys", []) if isinstance(state, dict) else []
    if not isinstance(keys, list):
        return {}
    return {(item["tenant_id"], item["id"]): item for item in keys if isinstance(item, dict)}


def _connector_access(connection, item, old_token, ledger_keys, preserve):
    """Read-only prefix of source-key issuance.

    The predicates stay in issuance order: an enabled application principal,
    the backed-up token hash, the reviewed ledger key, a retained active key,
    the preserve_applications refusal, then the bounded expiry used by
    rotate_all. A reviewed key that the database has already revoked stays
    eligible under rotate_all; that mode replaces it after this prefix.
    Nothing here writes a credential receipt or inserts a key.
    """
    identifier = str(UUID(item["id"]))
    principal = connection.execute(
        """SELECT c.tenant_id,c.principal_id FROM mnemion.connectors c
        JOIN mnemion.principals p ON p.tenant_id=c.tenant_id AND p.id=c.principal_id
        WHERE c.id=%s AND c.disabled_at IS NULL AND p.disabled_at IS NULL
          AND p.kind='application' AND NOT p.administrator""",
        (identifier,),
    ).fetchone()
    if principal is None:
        return None
    original = connection.execute(
        """SELECT id,expires_at FROM mnemion.api_keys
        WHERE tenant_id=%s AND principal_id=%s AND token_hash=%s""",
        (principal["tenant_id"], principal["principal_id"], token_hash(old_token)),
    ).fetchone()
    reviewed = (
        ledger_keys.get((str(principal["tenant_id"]), str(original["id"]))) if original else None
    )
    if reviewed is None:
        return None
    kept = connection.execute(
        """SELECT id FROM mnemion.api_keys WHERE tenant_id=%s AND principal_id=%s
        AND token_hash=%s AND revoked_at IS NULL AND NOT session_key
        AND (expires_at IS NULL OR expires_at>clock_timestamp())""",
        (principal["tenant_id"], principal["principal_id"], token_hash(old_token)),
    ).fetchone()
    if kept:
        return {"reuse": old_token}
    if preserve:
        return None
    expiry = connection.execute(
        "SELECT least(%s::timestamptz,%s::timestamptz) AS value",
        (original["expires_at"], reviewed["expires_at"]),
    ).fetchone()["value"]
    if (
        expiry is not None
        and not connection.execute(
            "SELECT %s::timestamptz>clock_timestamp() AS active",
            (expiry,),
        ).fetchone()["active"]
    ):
        return None
    return {"principal": principal, "expiry": expiry}


def _reject_eligible_git_cache(deferred, connectors, paths, mappings, dsn, ledger_keys, preserve):
    """Drop cache failures for omitted candidates and stop before issuing a source key.

    The token is the authenticated package's ``@asset-*`` reference after the
    existing path substitution. Its read uses the same 16385-byte private-file
    bound as issuance. The token and its hash are not logged.
    """
    if not deferred:
        return
    failure = None
    seen = set()
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        for item in connectors if isinstance(connectors, list) else ():
            identifier = _saved_connector_id(item)
            if identifier is None or identifier not in deferred:
                continue
            seen.add(identifier)
            try:
                config = _replace_paths(item["config"], paths, mappings)
                token = read_private(Path(config["service_token"]["file"]), 16385).decode().strip()
            except (
                HostRecoveryError,
                UnicodeDecodeError,
                OSError,
                KeyError,
                TypeError,
                AttributeError,
            ):
                failure = failure or deferred[identifier]
                continue
            if _connector_access(connection, item, token, ledger_keys, preserve) is not None:
                failure = failure or deferred[identifier]
    missing = [identifier for identifier in deferred if identifier not in seen]
    if missing:
        raise _cache_failure(deferred[missing[0]])
    if failure is not None:
        raise _cache_failure(failure)


def _connector_key(dsn, root, item, old_token, ledger_keys, preserve):
    identifier = str(UUID(item["id"]))
    output = root / ("connector-" + identifier + "-credentials.json")
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        # Issuance revalidates the read-only prefix before it writes a receipt or a key.
        decision = _connector_access(connection, item, old_token, ledger_keys, preserve)
        if decision is None:
            return None
        if "reuse" in decision:
            return decision["reuse"]
        principal = decision["principal"]
        expiry = decision["expiry"]
        if not output.exists():
            token, _ = new_token()
            private_json(
                output, {"connector_id": identifier, "key_id": str(uuid4()), "api_key": token}
            )
        saved = _json(output)
        if saved.get("connector_id") != identifier:
            raise HostRecoveryError("The saved source credential belongs to another connector.")
        existing = connection.execute(
            """SELECT token_hash,principal_id,revoked_at,session_key,expires_at,
            expires_at IS NULL OR expires_at>clock_timestamp() AS active
            FROM mnemion.api_keys WHERE tenant_id=%s AND id=%s""",
            (principal["tenant_id"], saved["key_id"]),
        ).fetchone()
        if existing:
            if (
                existing["token_hash"] != token_hash(saved["api_key"])
                or existing["revoked_at"] is not None
                or existing["principal_id"] != principal["principal_id"]
                or existing["session_key"]
                or not existing["active"]
                or existing["expires_at"] != expiry
            ):
                raise HostRecoveryError(
                    "The restored source credential changed or was revoked; it was preserved."
                )
        else:
            connection.execute(
                """INSERT INTO mnemion.api_keys(tenant_id,id,principal_id,name,token_hash,prefix,expires_at)
                VALUES(%s,%s,%s,'Restored source runner',%s,%s,%s)""",
                (
                    principal["tenant_id"],
                    saved["key_id"],
                    principal["principal_id"],
                    token_hash(saved["api_key"]),
                    saved["api_key"][:12],
                    expiry,
                ),
            )
        return saved["api_key"]


def restore(
    package: Path,
    secret_file: Path,
    destination: Path,
    *,
    operator_dsn: str,
    database_name: str,
    expected_sha256: str,
    database_host: str | None = None,
    database_port: int | None = None,
    database_locale: str | None = None,
    access_policy="rotate_all",
    managed=True,
    uv: Path | None = None,
    pg_bin: Path | None = None,
    host: str | None = None,
    port: int | None = None,
    public_url: str | None = None,
    start=False,
    path_mappings: list[tuple[str, str]] = (),
    latest_ledger: Path | None = None,
    ledger_sha256: str | None = None,
) -> dict:
    supervision._unix()
    recovery._database_locale(database_locale)
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", database_name) or not re.fullmatch(
        r"[a-f0-9]{64}", expected_sha256
    ):
        raise HostRecoveryError(
            "Use a new lowercase database name and the inspected package SHA-256."
        )
    if access_policy not in {"rotate_all", "preserve_applications"}:
        raise HostRecoveryError("Choose rotate_all or preserve_applications for restored access.")
    runtime_dsn = _runtime_connection(operator_dsn, database_name, database_host, database_port)
    if (latest_ledger is None) != (ledger_sha256 is None) or (
        ledger_sha256 is not None and not re.fullmatch(r"[a-f0-9]{64}", ledger_sha256)
    ):
        raise HostRecoveryError("Provide the newer encrypted ledger together with its SHA-256.")
    root = destination.expanduser().absolute()
    if root.is_symlink():
        raise HostRecoveryError("The restored host directory cannot be a symbolic link.")
    mappings = []
    for before, after in path_mappings:
        if not Path(before).is_absolute() or not Path(after).is_absolute():
            raise HostRecoveryError("Path mappings require absolute source and destination paths.")
        mappings.append((str(Path(before)), str(Path(after))))
    mappings.sort(key=lambda item: len(item[0]), reverse=True)
    with (
        opened(package, secret_file, expected_sha256) as (saved, unpacked, digest),
        (
            opened_ledger(latest_ledger, secret_file, ledger_sha256)
            if latest_ledger is not None
            else nullcontext(
                (unpacked / "ledger.json", recovery.read_ledger(unpacked / "ledger.json"))
            )
        ) as (current_ledger_path, current_ledger),
    ):
        plan = public_plan(saved["plan"])
        if recovery._time(current_ledger["snapshot_at"]) < recovery._time(
            plan["snapshot_at"]
        ) or not set(plan["tenant_ids"]) <= set(current_ledger["tenant_ids"]):
            raise HostRecoveryError(
                "The access ledger must cover this entire backup and be at least as recent."
            )
        listen = host if host is not None else saved["host"]
        ipaddress.ip_address(listen)
        listen_port = port if port is not None else saved["port"]
        if type(listen_port) is not int or not 1024 <= listen_port <= 65535:
            raise HostRecoveryError("Choose a service port from 1024 to 65535.")
        origin = public_url if public_url is not None else saved["public_url"]
        if origin:
            from .oauth import https_url

            origin = https_url(origin)
        selected = {
            "package_sha256": digest,
            "database_name": database_name,
            "host": listen,
            "port": listen_port,
            "public_url": origin,
            "access_policy": access_policy,
            "managed": managed,
            "ledger_sha256": ledger_sha256,
            "mappings": [list(item) for item in mappings],
            "database_target": list(
                service_updates._target(make_conninfo(operator_dsn, dbname=database_name))
            ),
            "runtime_database_target": list(service_updates._target(runtime_dsn)),
            **({"database_locale": database_locale} if database_locale is not None else {}),
        }
        # Read-only inspection before the destination directory, journal, or
        # database. A classified ledger omits disabled and absent connections.
        # Enabled connections keep fixed codes until their saved keys are reviewed.
        deferred_cache_failures = require_remote_git_caches(
            saved["connectors"], saved["assets"], mappings, root, current_ledger
        )
        update_state.directory(root)
        with update_state.lock(root):
            record = root / "restore.json"
            if record.exists():
                request = _json(record)
                if request.get("selection") != selected:
                    raise HostRecoveryError(
                        "This destination belongs to a different reviewed recovery. Use a new directory."
                    )
            else:
                if set(item.name for item in root.iterdir()) != {"operation.lock"}:
                    raise HostRecoveryError(
                        "Choose an empty private host directory; existing installation files are preserved."
                    )
                request = {
                    "format": "mnemion-host-recovery-state",
                    "version": 1,
                    "restore_id": str(uuid4()),
                    "selection": selected,
                    "phase": "planned",
                    "snapshot_at": plan["snapshot_at"],
                    "ledger_at": current_ledger["snapshot_at"],
                }
                update_state.write(record, request, replace=False)
            state = root / "service"
            credentials_file = root / "recovery-credentials.json"
            database_present = _restored_database(
                operator_dsn, database_name, credentials_file, plan
            )
            if request["phase"] == "complete":
                _, installed = supervision.settings(state)
                runtime_present = (
                    Path(installed["python"]).is_file() and Path(installed["directory"]).is_dir()
                )
                if managed:
                    active = _json(state / "updates/active.json")
                    runtime_present = runtime_present and (
                        Path(active["python"]).is_file() and Path(active["directory"]).is_dir()
                    )
                if database_present and runtime_present:
                    if deferred_cache_failures:
                        published = {}
                        published_root = root / "assets"
                        for asset in saved["assets"]:
                            target = str(published_root / asset["id"])
                            published["@" + asset["id"]] = target
                            if asset["source"]:
                                published[asset["source"]] = target
                        role_file = root / "database-credentials.json"
                        if not role_file.is_file():
                            raise _cache_failure(next(iter(deferred_cache_failures.values())))
                        _reject_eligible_git_cache(
                            deferred_cache_failures,
                            saved["connectors"],
                            published,
                            mappings,
                            _json(role_file)["admin_database_url"],
                            _ledger_key_index(current_ledger),
                            access_policy == "preserve_applications",
                        )
                    current = supervision.start(state) if start else supervision.status(state)
                    return {
                        "restored": True,
                        "already_restored": True,
                        "host_directory": str(root),
                        "startup": supervision.startup_instructions(state, installed),
                        "startup_registration_restored": False,
                        "external_transport_restored": False,
                        "status": current,
                    }
                if not supervision.stop(state).get("stopped"):
                    raise HostRecoveryError(
                        "Stop the previous host processes before repairing its lost runtime or database."
                    )
                if managed:
                    request["saved_update_enabled"] = supervision.configuration_status(
                        state, installed
                    )["updates"]["enabled"]
                state.rename(root / ("retired-service-" + uuid4().hex))
                request["phase"] = "repairing"
                update_state.write(record, request)
            if not database_present:
                if credentials_file.exists():
                    # The restore committed no destination database. Preserve a
                    # previous attempt's unused credential receipt before retry.
                    credentials_file.rename(root / ("unused-owner-" + uuid4().hex + ".json"))
                recovery.restore_backup(
                    operator_dsn,
                    unpacked / "database.mnemion",
                    database_name=database_name,
                    deletion_ledger=current_ledger_path,
                    credentials_output=credentials_file,
                    pg_bin=pg_bin,
                    preserve_application_keys=access_policy == "preserve_applications",
                    database_locale=database_locale,
                )
            request["phase"] = "database_restored"
            update_state.write(record, request)
            credentials, roles_file = _database_roles(
                operator_dsn, runtime_dsn, database_name, root, request
            )
            if not _restored_database(
                credentials["admin_database_url"], database_name, credentials_file, plan
            ):
                raise HostRecoveryError(
                    "The service database endpoint does not identify this restored workspace."
                )
            asset_root = update_state.directory(root / "assets")
            paths = {}
            for item in saved["assets"]:
                target = str(asset_root / item["id"])
                paths["@" + item["id"]] = target
                if item["source"]:
                    paths[item["source"]] = target
            for item in saved["assets"]:
                content = (unpacked / "assets" / item["id"]).read_bytes()
                if item["json"]:
                    content = canonical_json(_replace_paths(json.loads(content), paths, mappings))
                _once(asset_root / item["id"], content)
            ledger_keys = _ledger_key_index(current_ledger)
            _reject_eligible_git_cache(
                deferred_cache_failures,
                saved["connectors"],
                paths,
                mappings,
                credentials["admin_database_url"],
                ledger_keys,
                access_policy == "preserve_applications",
            )
            environment = _replace_paths(saved["environment"], paths, mappings)
            # A journal registry can contain a local scanner executable and
            # Git/state paths. Restore its encrypted asset for inspection,
            # but never activate another host's executable configuration.
            # Database recovery pauses publication; the new operator enrolls
            # a destination before an administrator approves capture again.
            environment.pop("MNEMION_WRITEBACK_CONFIG", None)
            environment["MNEMION_MODEL_CACHE"] = str(update_state.directory(root / "models"))
            if origin:
                environment["MNEMION_PUBLIC_URL"] = origin
            environment_file = root / "host-secrets.json"
            _once(environment_file, canonical_json(environment))
            from .studio import source_root

            # A restored archive can predate the installed runtime's approved
            # model catalog. Register identities without inference, downloads,
            # changing a space's selection or reindexing retained memory.
            logs = update_state.directory(root / "logs")
            service_updates._command(
                [sys.executable, "-m", "mnemion.service.cli", "models", "--register"],
                cwd=source_root() or root,
                environment={
                    **service_updates._environment({"environment": environment}),
                    "MNEMION_ADMIN_DATABASE_URL": credentials["admin_database_url"],
                },
                log=logs / "model-registration.log",
                timeout=60,
            )
            sources = update_state.directory(root / "connectors")
            connector_paths = []
            inactive = []
            local_host = "127.0.0.1" if listen == "0.0.0.0" else "::1" if listen == "::" else listen
            local_host = "[" + local_host + "]" if ":" in local_host else local_host
            for item in saved["connectors"]:
                identifier = str(UUID(item["id"]))
                config = _replace_paths(item["config"], paths, mappings)
                old_token = (
                    read_private(Path(config["service_token"]["file"]), 16385).decode().strip()
                )
                token = _connector_key(
                    credentials["admin_database_url"],
                    sources,
                    item,
                    old_token,
                    ledger_keys,
                    access_policy == "preserve_applications",
                )
                if token is None:
                    inactive.append(identifier)
                    continue
                token_path = sources / (identifier + ".key")
                _once(token_path, (token + "\n").encode())
                config["service_token"] = {"file": str(token_path)}
                config["service_url"] = f"http://{local_host}:{listen_port}"
                path = sources / (identifier + ".json")
                _once(path, canonical_json(config))
                connector_paths.append(path)
            if not state.exists() or not any(state.iterdir()):
                if managed:
                    service_updates.setup(
                        state,
                        roles_file,
                        roles_file,
                        roles_file,
                        uv=uv,
                        pg_bin=pg_bin,
                        host=listen,
                        port=listen_port,
                        public_url=origin,
                        environment=environment_file,
                        connector_configs=tuple(connector_paths),
                        inherit_environment=False,
                    )
                    if request.get("saved_update_enabled") is False or (
                        "saved_update_enabled" not in request
                        and plan["source_updates"] == {"mode": "managed", "enabled": False}
                    ):
                        service_updates.preferences(state, False)
                else:
                    supervision.prepare(
                        state,
                        roles_file,
                        roles_file,
                        host=listen,
                        port=listen_port,
                        public_url=origin,
                        environment=environment_file,
                        connector_configs=tuple(connector_paths),
                        inherit_environment=False,
                    )
            else:
                # Setup may have committed just before interruption. Its files
                # must still identify these exact logins and source runners.
                _, prepared = supervision.settings(state)
                if (
                    _json(state / "api.json") != {"database_url": credentials["database_url"]}
                    or _json(state / "worker.json")
                    != {"worker_database_url": credentials["worker_database_url"]}
                    or bool(prepared.get("managed_updates")) != managed
                    or prepared["host"] != listen
                    or prepared["port"] != listen_port
                    or prepared.get("public_url") != origin
                    or prepared["environment"] != environment
                    or prepared.get("connectors", [])
                    != [{"id": path.stem, "config": str(path)} for path in connector_paths]
                ):
                    raise HostRecoveryError(
                        "Existing service settings differ from this recovery; they were preserved."
                    )
                if managed:
                    if _json(state / "updates/owner.json") != {
                        "admin_database_url": credentials["admin_database_url"]
                    }:
                        raise HostRecoveryError(
                            "The managed database owner differs from this recovery; it was preserved."
                        )
                    service_updates.resolved_runtime(state)
            request.update(
                phase="complete",
                connector_ids=[path.stem for path in connector_paths],
                inactive_connector_ids=inactive,
            )
            update_state.write(record, request)
            current = supervision.start(state) if start else supervision.status(state)
            return {
                "restored": True,
                "already_restored": False,
                "host_directory": str(root),
                "database_name": database_name,
                "tenant_ids": plan["tenant_ids"],
                "recovery_credentials_file": str(credentials_file),
                "access_policy": access_policy,
                "snapshot_at": plan["snapshot_at"],
                "ledger_at": current_ledger["snapshot_at"],
                "application_keys_preserved": len(
                    _json(credentials_file).get("preserved_application_keys", [])
                ),
                "supervised_connectors": len(connector_paths),
                "inactive_connector_ids": inactive,
                "external_transport_restored": False,
                "startup_registration_restored": False,
                "startup": supervision.startup_instructions(state, supervision.settings(state)[1]),
                "status": current,
            }


def status(destination: Path) -> dict:
    root = destination.expanduser().absolute()
    value = _json(root / "restore.json")
    result = {
        "phase": value["phase"],
        "package_sha256": value["selection"]["package_sha256"],
        "access_policy": value["selection"]["access_policy"],
        "host_directory": str(root),
        "snapshot_at": value.get("snapshot_at"),
        "ledger_at": value.get("ledger_at"),
    }
    if value["phase"] == "complete":
        state, settings = supervision.settings(root / "service")
        result["status"] = supervision.status(state)
        result["startup"] = supervision.startup_instructions(state, settings)
        result["startup_registration_restored"] = False
        result["external_transport_restored"] = False
    return result
