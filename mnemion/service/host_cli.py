"""Agent-readable host custody commands; secret values only use private files."""

import argparse
import json
import os
from pathlib import Path
import sys

from .host_package import (
    HostRecoveryError,
    create_key,
    export_ledger,
    inspect,
    read_private,
    snapshot,
)
from .host_recovery import restore, status


def arguments(parser: argparse.ArgumentParser):
    parser.add_argument(
        "action", choices=("key", "snapshot", "ledger", "inspect", "restore", "status")
    )
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--plan-output", type=Path)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--admin-credentials", type=Path)
    parser.add_argument("--operator-credentials", type=Path)
    parser.add_argument("--connector-config", type=Path, action="append", default=[])
    parser.add_argument("--include-file", type=Path, action="append", default=[])
    parser.add_argument("--pg-bin", type=Path)
    parser.add_argument("--uv", type=Path)
    parser.add_argument("--database")
    parser.add_argument("--database-host")
    parser.add_argument("--database-port", type=int)
    parser.add_argument("--expect-sha256")
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--ledger-sha256")
    parser.add_argument(
        "--access-policy", choices=("rotate_all", "preserve_applications"), default="rotate_all"
    )
    parser.add_argument("--manual-updates", action="store_true")
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--public-url")
    parser.add_argument("--path-map", action="append", default=[])


def execute(args):
    try:
        required = {
            "key": ("output",),
            "snapshot": ("state_dir", "output", "key_file"),
            "ledger": ("state_dir", "output", "key_file"),
            "inspect": ("package", "key_file"),
            "restore": ("package", "key_file", "destination", "database", "expect_sha256"),
            "status": ("destination",),
        }[args.action]
        if any(getattr(args, name) is None for name in required):
            raise HostRecoveryError(
                "Missing host command options; use mnemion-service host --help."
            )
        if args.action == "key":
            result = create_key(args.output)
        elif args.action == "ledger":
            result = export_ledger(
                args.state_dir, args.output, args.key_file, admin=args.admin_credentials
            )
        elif args.action == "snapshot":
            result = snapshot(
                args.state_dir,
                args.output,
                args.key_file,
                admin=args.admin_credentials,
                connector_configs=args.connector_config,
                include_files=args.include_file,
                pg_bin=args.pg_bin,
                plan_output=args.plan_output,
            )
        elif args.action == "inspect":
            result = inspect(args.package, args.key_file)
        elif args.action == "status":
            result = status(args.destination)
        else:
            dsn = (
                json.loads(read_private(args.operator_credentials)).get("admin_database_url")
                if args.operator_credentials
                else os.environ.get(
                    "MNEMION_RESTORE_DATABASE_URL", os.environ.get("MNEMION_ADMIN_DATABASE_URL")
                )
            )
            if not isinstance(dsn, str) or not dsn:
                raise HostRecoveryError(
                    "Supply a private cluster-operator connection with database, role and pgvector provisioning authority."
                )
            mappings = []
            for item in args.path_map:
                if "=" not in item:
                    raise HostRecoveryError(
                        "Each --path-map uses absolute-source=absolute-destination."
                    )
                mappings.append(tuple(item.split("=", 1)))
            result = restore(
                args.package,
                args.key_file,
                args.destination,
                operator_dsn=dsn,
                database_name=args.database,
                database_host=args.database_host,
                database_port=args.database_port,
                expected_sha256=args.expect_sha256,
                access_policy=args.access_policy,
                managed=not args.manual_updates,
                uv=args.uv,
                pg_bin=args.pg_bin,
                host=args.host,
                port=args.port,
                public_url=args.public_url,
                start=args.start,
                path_mappings=mappings,
                latest_ledger=args.ledger,
                ledger_sha256=args.ledger_sha256,
            )
        print(json.dumps(result))
        if args.action == "restore" and args.start and not result.get("status", {}).get("ready"):
            return 2
        return 0
    except Exception as error:
        from ..local_diagnostics import failure_diagnostic
        from .update_state import OperationBusy
        from ..backup_encryption import EncryptionError

        print(
            json.dumps(
                {
                    "error": "host_operation_busy"
                    if isinstance(error, OperationBusy)
                    else "host_recovery_failed",
                    "message": str(error)
                    if isinstance(error, (HostRecoveryError, EncryptionError))
                    else "Host recovery failed. Check the private inputs, supported database tools and journal; no existing installation was overwritten.",
                    "diagnostic": failure_diagnostic(error),
                }
            ),
            file=sys.stderr,
        )
        return 75 if isinstance(error, OperationBusy) else 2
