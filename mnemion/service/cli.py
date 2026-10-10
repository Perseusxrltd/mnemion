"""Explicit service, worker, migration, client, and Obsidian commands."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import threading
from pathlib import Path

from .model_registry import ModelRegistry


def _private_json(path: Path, data: dict) -> None:
    from ..archives import private_json

    private_json(path, data)


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Set {name}")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mnemion-service", description="Shared memory for applications and teams"
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        action="append",
        default=[],
        help="Load a private JSON credentials file; can be repeated",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "migrate", help="Apply checked database migrations with administration credentials"
    )
    logins = commands.add_parser("logins", help="Provision separate API and worker database logins")
    logins.add_argument("--prefix", default="mnemion")
    logins.add_argument("--output", type=Path, required=True)
    bootstrap = commands.add_parser(
        "bootstrap", help="Create an organization and a private owner space"
    )
    bootstrap.add_argument("--tenant", required=True)
    bootstrap.add_argument("--owner", required=True)
    bootstrap.add_argument("--space", default="Private memory")
    bootstrap.add_argument("--output", type=Path, required=True)
    serve = commands.add_parser("serve", help="Run the versioned HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=7892)
    serve.add_argument(
        "--concurrency", type=int, default=int(os.environ.get("MNEMION_HTTP_CONCURRENCY", "64"))
    )
    serve.add_argument(
        "--studio", type=Path, help="Serve a built Studio frontend from this directory"
    )
    worker = commands.add_parser("worker", help="Run durable indexing and deletion work")
    worker.add_argument("--once", action="store_true")
    prepare = commands.add_parser(
        "prepare-model", help="Prepare a configured local model or pinned endpoint tokenizer"
    )
    prepare.add_argument("--profile", default="e5-small")
    models = commands.add_parser(
        "models", help="List operator-approved embedding profiles without inference"
    )
    models.add_argument(
        "--register",
        action="store_true",
        help="Register generation identities with the owner database login",
    )
    schema = commands.add_parser(
        "schema", help="Write the versioned OpenAPI contract without connecting to a database"
    )
    schema.add_argument("--output", type=Path, required=True)
    backup = commands.add_parser("backup", help="Create a complete, consistent PostgreSQL archive")
    backup.add_argument("--output", type=Path, required=True)
    backup.add_argument("--pg-bin", type=Path)
    ledger = commands.add_parser(
        "recovery-ledger",
        help="Export current deletion denials and access grants separately from backups",
    )
    ledger.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser(
        "verify-backup", help="Verify all archive members without touching a database"
    )
    verify.add_argument("file", type=Path)
    restore = commands.add_parser(
        "restore",
        help="Verify and restore into a new database; reconcile current denials and rotate keys",
    )
    restore.add_argument("file", type=Path)
    restore.add_argument("--database", required=True)
    restore.add_argument("--ledger", type=Path, required=True)
    restore.add_argument("--credentials-output", type=Path, required=True)
    restore.add_argument("--pg-bin", type=Path)
    legacy_backup = commands.add_parser(
        "legacy-backup",
        help="Snapshot an offline v3 profile, source files, sidecars, and Obsidian vault",
    )
    legacy_backup.add_argument("--profile", type=Path, required=True)
    legacy_backup.add_argument("--output", type=Path, required=True)
    legacy_backup.add_argument("--vault", type=Path)
    legacy_backup.add_argument("--writers-stopped", action="store_true")
    legacy_ledger = commands.add_parser(
        "legacy-ledger", help="Export a v3 deletion ledger for migration and recovery"
    )
    legacy_ledger.add_argument("--profile", type=Path, required=True)
    legacy_ledger.add_argument("--output", type=Path, required=True)
    legacy_restore = commands.add_parser(
        "legacy-restore",
        help="Restore and reconcile a complete v3 archive into a new, paused profile",
    )
    legacy_restore.add_argument("file", type=Path)
    legacy_restore.add_argument("--path", type=Path, required=True)
    legacy_restore.add_argument("--ledger", type=Path, required=True)
    legacy_freeze = commands.add_parser(
        "legacy-freeze",
        help="Persist a migration pause for updated v3 writers; also stop older processes",
    )
    legacy_freeze.add_argument("--profile", type=Path, required=True)
    legacy_resume = commands.add_parser(
        "legacy-resume", help="Resume a verified legacy profile after recovery or rollback"
    )
    legacy_resume.add_argument("--profile", type=Path, required=True)
    legacy_resume.add_argument("--freeze-id", required=True)
    legacy_import = commands.add_parser(
        "import-v3", help="Import a verified v3 archive into an explicitly owned private space"
    )
    legacy_import.add_argument("file", type=Path)
    legacy_import.add_argument("--tenant", required=True)
    legacy_import.add_argument("--owner", required=True)
    legacy_import.add_argument("--ledger", type=Path)
    legacy_import.add_argument("--final", action="store_true")
    legacy_import.add_argument(
        "--accept-exceptions", help="SHA-256 of the reviewed exception report"
    )
    legacy_import.add_argument("--report", type=Path, required=True)
    pause = commands.add_parser(
        "pause-space", help="Wait for in-flight writes and pause a space for recovery"
    )
    pause.add_argument("--tenant", required=True)
    pause.add_argument("--space", required=True)
    pause.add_argument("--reason", required=True)
    resume = commands.add_parser(
        "resume-space", help="Resume a paused space using its exact pause token"
    )
    resume.add_argument("--tenant", required=True)
    resume.add_argument("--space", required=True)
    resume.add_argument("--token", required=True)
    rollback = commands.add_parser(
        "rollback-export", help="Pause a migrated space and preserve its complete v4 tail"
    )
    rollback.add_argument("--tenant", required=True)
    rollback.add_argument("--space", required=True)
    rollback.add_argument("--output", type=Path, required=True)
    replay = commands.add_parser(
        "rollback-restore", help="Replay a v4 tail into a new, paused legacy profile"
    )
    replay.add_argument("--legacy", type=Path, required=True)
    replay.add_argument("--tail", type=Path, required=True)
    replay.add_argument("--path", type=Path, required=True)
    mcp = commands.add_parser("mcp", help="Serve the compact MCP tool surface")
    mcp.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    mcp.add_argument("--host", default="127.0.0.1")
    mcp.add_argument("--port", type=int, default=7893)
    mcp.add_argument("--legacy-space", default=None)
    vault = commands.add_parser(
        "vault", help="Refresh a local Obsidian vault from authorized service data"
    )
    vault.add_argument("--path", type=Path, required=True)
    vault_scope = vault.add_mutually_exclusive_group(required=True)
    vault_scope.add_argument("--spaces", nargs="+")
    vault_scope.add_argument("--all-accessible", action="store_true")
    vault.add_argument("--review", action="store_true")
    vault.add_argument("--dry-run", action="store_true")
    vault.add_argument("--open", action="store_true")
    args = parser.parse_args(argv)
    for path in args.credentials:
        values = json.loads(path.read_text(encoding="utf-8"))
        for key, variable in (
            ("database_url", "MNEMION_DATABASE_URL"),
            ("worker_database_url", "MNEMION_WORKER_DATABASE_URL"),
            ("api_key", "MNEMION_API_KEY"),
            ("api_url", "MNEMION_API_URL"),
        ):
            if values.get(key):
                os.environ[variable] = values[key]
    if args.command == "import-v3":
        from uuid import UUID
        from .embeddings import DEFAULT_GENERATION
        from .legacy_import import import_v3

        if args.report.exists():
            raise FileExistsError("Migration report output already exists")
        result = import_v3(
            _required("MNEMION_ADMIN_DATABASE_URL"),
            args.file,
            tenant=UUID(args.tenant),
            owner=UUID(args.owner),
            generation=DEFAULT_GENERATION,
            deletion_ledger=args.ledger,
            final=args.final,
            accept_exceptions=args.accept_exceptions,
            report_sink=lambda report: _private_json(args.report, report),
        )
        print(
            json.dumps(
                {
                    "report_file": str(args.report),
                    "space_id": result["space_id"],
                    "counts": result["counts"],
                    "exceptions": len(result["exceptions"]),
                    "cutover_complete": result["cutover_complete"],
                }
            )
        )
        return 2 if args.final and not result["cutover_complete"] else 0
    elif args.command == "rollback-export":
        from uuid import UUID
        from .rollback import export_rollback

        print(
            json.dumps(
                export_rollback(
                    _required("MNEMION_ADMIN_DATABASE_URL"),
                    tenant=UUID(args.tenant),
                    space=UUID(args.space),
                    output=args.output,
                )
            )
        )
    elif args.command == "rollback-restore":
        from ..legacy_rollback import restore_rollback

        print(json.dumps(restore_rollback(args.legacy, args.tail, args.path)))
    elif args.command in {"pause-space", "resume-space"}:
        from uuid import UUID
        from .fences import pause_space, resume_space

        dsn = _required("MNEMION_ADMIN_DATABASE_URL")
        tenant, space = UUID(args.tenant), UUID(args.space)
        result = (
            pause_space(dsn, tenant, space, reason=args.reason)
            if args.command == "pause-space"
            else resume_space(dsn, tenant, space, UUID(args.token))
        )
        print(json.dumps(result))
    elif args.command == "migrate":
        from .db import migrate

        print(json.dumps({"applied": migrate(_required("MNEMION_ADMIN_DATABASE_URL"))}))
    elif args.command == "logins":
        import secrets
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import make_conninfo
        from .db import migrate

        if not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", args.prefix):
            raise ValueError("Use a lowercase database-role prefix of up to 31 characters")
        if args.output.exists():
            raise FileExistsError("Credentials output already exists")
        dsn = _required("MNEMION_ADMIN_DATABASE_URL")
        migrate(dsn)
        credentials = {}
        with psycopg.connect(dsn) as conn:
            for suffix, group, key in (
                ("api_login", "mnemion_app", "database_url"),
                ("worker_login", "mnemion_worker", "worker_database_url"),
            ):
                name, password = args.prefix + "_" + suffix, secrets.token_urlsafe(32)
                conn.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {} IN ROLE {}"
                    ).format(sql.Identifier(name), sql.Literal(password), sql.Identifier(group))
                )
                credentials[key] = make_conninfo(dsn, user=name, password=password)
            _private_json(args.output, credentials)
        print(json.dumps({"credentials_file": str(args.output), "roles_created": True}))
    elif args.command == "bootstrap":
        from .admin import bootstrap_tenant

        if args.output.exists():
            raise FileExistsError("Owner credentials output already exists")
        result = bootstrap_tenant(
            _required("MNEMION_ADMIN_DATABASE_URL"),
            tenant_name=args.tenant,
            administrator_name=args.owner,
            space_name=args.space,
            credentials_sink=lambda values: _private_json(args.output, values),
        )
        print(
            json.dumps(
                {
                    "credentials_file": str(args.output),
                    "tenant_id": result["tenant_id"],
                    "space_id": result["space_id"],
                }
            )
        )
    elif args.command == "serve":
        import uvicorn

        if not 1 <= args.concurrency <= 4096:
            raise ValueError("HTTP concurrency must be between 1 and 4096")
        if args.studio:
            os.environ["MNEMION_STUDIO_DIST"] = str(args.studio)
        uvicorn.run(
            "mnemion.service.api:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            access_log=False,
            proxy_headers=False,
            limit_concurrency=args.concurrency,
            timeout_keep_alive=5,
            timeout_graceful_shutdown=30,
        )
    elif args.command == "prepare-model":
        registry = ModelRegistry.from_environment()
        try:
            model = registry.profile(args.profile)
            model.prepare()
            print(
                json.dumps(
                    {
                        "generation_id": model.generation.id,
                        "dimensions": model.generation.dimensions,
                    }
                )
            )
        finally:
            registry.close()
    elif args.command == "models":
        registry = ModelRegistry.from_environment()
        if args.register:
            import psycopg
            from .admin import register_generation

            with psycopg.connect(_required("MNEMION_ADMIN_DATABASE_URL")) as conn:
                for generation in registry.generation_ids:
                    register_generation(conn, registry.get(generation).generation)
        print(json.dumps({"profiles": registry.describe(), "registered": args.register}))
    elif args.command == "schema":
        from .api import create_app
        from .db import Database

        schema = create_app(Database("dbname=mnemion_schema_only")).openapi()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps({"schema_file": str(args.output), "version": schema["info"]["version"]}))
    elif args.command == "backup":
        from .recovery import create_backup

        print(
            json.dumps(
                create_backup(
                    _required("MNEMION_ADMIN_DATABASE_URL"), args.output, pg_bin=args.pg_bin
                ),
                indent=2,
            )
        )
    elif args.command == "recovery-ledger":
        from .recovery import export_ledger

        print(json.dumps(export_ledger(_required("MNEMION_ADMIN_DATABASE_URL"), args.output)))
    elif args.command == "verify-backup":
        from ..archives import verified_archive
        from .recovery import BACKUP_FORMAT, read_ledger

        with verified_archive(args.file, BACKUP_FORMAT) as (manifest, root):
            read_ledger(root / "deletions.json")
            print(
                json.dumps(
                    {
                        "verified": True,
                        "backup_id": manifest["backup_id"],
                        "snapshot_at": manifest["snapshot_at"],
                        "tables": manifest["tables"],
                    },
                    indent=2,
                )
            )
    elif args.command == "restore":
        from .recovery import restore_backup

        print(
            json.dumps(
                restore_backup(
                    _required("MNEMION_ADMIN_DATABASE_URL"),
                    args.file,
                    database_name=args.database,
                    deletion_ledger=args.ledger,
                    credentials_output=args.credentials_output,
                    pg_bin=args.pg_bin,
                ),
                indent=2,
            )
        )
    elif args.command == "legacy-backup":
        from ..legacy_archive import create_legacy_backup

        print(
            json.dumps(
                create_legacy_backup(
                    args.profile,
                    args.output,
                    writers_stopped=args.writers_stopped,
                    vault=args.vault,
                ),
                indent=2,
            )
        )
    elif args.command == "legacy-ledger":
        from ..legacy_archive import export_legacy_ledger

        print(json.dumps(export_legacy_ledger(args.profile, args.output)))
    elif args.command == "legacy-restore":
        from ..legacy_archive import restore_legacy_backup

        print(
            json.dumps(
                restore_legacy_backup(args.file, args.path, deletion_ledger=args.ledger), indent=2
            )
        )
    elif args.command == "legacy-freeze":
        from ..legacy_freeze import freeze_profile

        print(json.dumps(freeze_profile(args.profile)))
    elif args.command == "legacy-resume":
        from ..legacy_freeze import thaw_profile

        thaw_profile(args.profile, args.freeze_id)
        print(json.dumps({"profile": str(args.profile), "paused": False}))
    elif args.command == "worker":
        from .db import Database
        from .model_worker import ModelWorker
        from .telemetry import Telemetry

        database = Database(_required("MNEMION_WORKER_DATABASE_URL"), worker=True)
        database.open()
        telemetry = Telemetry(database)
        telemetry.start()
        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())
        try:
            registry = ModelRegistry.from_environment()
            process = ModelWorker(database, registry, telemetry=telemetry)
            if args.once:
                print(json.dumps({"processed": process.run_once()}))
            else:
                while not stop.is_set():
                    if not process.run_once():
                        stop.wait(0.5)
        finally:
            telemetry.stop()
            if "registry" in locals():
                registry.close()
            database.close()
    elif args.command == "mcp":
        from .mcp import create_mcp

        gateway = create_mcp(
            os.environ.get("MNEMION_API_URL", "http://127.0.0.1:7892"),
            stdio_token=_required("MNEMION_API_KEY") if args.transport == "stdio" else None,
            legacy_space=args.legacy_space,
        )
        if args.transport == "stdio":
            gateway.run("stdio")
        else:
            gateway.run(
                "streamable-http",
                host=args.host,
                port=args.port,
                stateless_http=True,
                json_response=True,
            )
    elif args.command == "vault":
        from ..sdk import Client

        with Client(
            os.environ.get("MNEMION_API_URL", "http://127.0.0.1:7892"), _required("MNEMION_API_KEY")
        ) as client:
            result = client.sync_obsidian(
                str(args.path),
                args.spaces,
                review=args.review,
                dry_run=args.dry_run,
                all_accessible=args.all_accessible,
            )
        if args.open and result["completed"] and not args.dry_run:
            from ..obsidian import open_obsidian_vault

            result["open"] = open_obsidian_vault(args.path)
        print(json.dumps(result, indent=2))
        if not result["completed"]:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
