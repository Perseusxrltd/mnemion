"""Native agent and OS-owner entry points; no memory API is required."""

import argparse
import asyncio
import json
from pathlib import Path
import sys

from ..private_input import read_private
from ..private_output import private_output
from . import HostControlError
from .protocol import MAX_REQUEST, Operator, parse
from .transport import Connection, call


def arguments(parser):
    commands = parser.add_subparsers(dest="host_control_action", required=True)
    commands.add_parser("capabilities", help="Inspect the native host-control protocol")
    commands.add_parser("schema", help="Inspect typed native host-control actions and grants")
    owner_status = commands.add_parser(
        "owner-status", help="Local OS owner: inspect independent authority without an operator key"
    )
    owner_status.add_argument("--state-dir", required=True, type=Path)
    recover = commands.add_parser(
        "recover-custodian",
        help="Local OS owner: recover a permanent custodian using an explicitly approved request",
    )
    recover.add_argument("--state-dir", required=True, type=Path)
    recover.add_argument("--request", required=True, type=Path)
    backup = commands.add_parser(
        "backup-setup", help="OS owner: configure independent encrypted backups"
    )
    backup.add_argument("--state-dir", required=True, type=Path)
    backup.add_argument("--config", required=True, type=Path)
    adopt = commands.add_parser("adopt", help="OS owner: prepare an independent host controller")
    adopt.add_argument("--state-dir", required=True, type=Path)
    adopt.add_argument("--service-state", required=True, type=Path)
    adopt.add_argument("--operator", required=True, type=Path, help="Public custodian JSON")
    adopt.add_argument("--bind", default="127.0.0.1")
    adopt.add_argument("--port", default=7893, type=int)
    adopt.add_argument("--advertised-host")
    adopt.add_argument("--approve-network", action="store_true")
    for name in (
        "start",
        "stop",
        "status",
        "startup",
        "serve",
        "service-policy",
        "memory-run",
        "memory-repair",
    ):
        item = commands.add_parser(name)
        item.add_argument("--state-dir", required=True, type=Path)
    worker = commands.add_parser("work", help=argparse.SUPPRESS)
    worker.add_argument("--state-dir", required=True, type=Path)
    worker.add_argument("--lock-fd", required=True, type=int)
    client = commands.add_parser("call", help="Send one typed JSON request from stdin")
    client.add_argument("--connection", type=Path, required=True)
    client.add_argument("--identity", type=Path, required=True)
    key = commands.add_parser("keygen", help="Create a private independent operator key")
    key.add_argument("--output", required=True, type=Path)


def execute(args):
    try:
        action = args.host_control_action
        if action == "capabilities":
            from .installation import CAPABILITIES

            result = CAPABILITIES
        elif action == "schema":
            from .protocol import REQUEST, ROLES
            from .owner import OwnerRecovery

            result = {
                "request": REQUEST.json_schema(),
                "connection": Connection.model_json_schema(),
                "local_owner_recovery": OwnerRecovery.model_json_schema(),
                "roles": {role: sorted(actions) for role, actions in ROLES.items()},
            }
        elif action == "owner-status":
            from .owner import status

            result = status(args.state_dir)
        elif action == "recover-custodian":
            from .owner import OwnerRecovery, recover

            result = recover(
                args.state_dir,
                OwnerRecovery.model_validate_json(read_private(args.request, maximum=16384)),
            )
        elif action == "backup-setup":
            from .backup import Configuration, configure

            result = configure(
                args.state_dir,
                Configuration.model_validate_json(read_private(args.config, maximum=65536)),
            )
        elif action == "keygen":
            import asyncssh

            key = asyncssh.generate_private_key("ssh-ed25519")
            with private_output(args.output) as stream:
                stream.write(key.export_private_key())
            result = {
                "public_key": key.export_public_key().decode().strip(),
                "fingerprint": key.get_fingerprint("sha256"),
            }
        elif action == "adopt":
            from .installation import adopt

            operator = Operator.model_validate_json(read_private(args.operator, maximum=16384))
            result = adopt(
                args.state_dir,
                args.service_state,
                operator,
                bind=args.bind,
                port=args.port,
                advertised_host=args.advertised_host,
                approve_network=args.approve_network,
            )
        elif action == "serve":
            from .daemon import serve

            return asyncio.run(serve(args.state_dir))
        elif action in {"service-policy", "memory-run", "memory-repair"}:
            from . import memory_lifecycle

            if action == "memory-run":
                return memory_lifecycle.run(args.state_dir)
            result = (
                memory_lifecycle.repair(args.state_dir)
                if action == "memory-repair"
                else memory_lifecycle.policy(args.state_dir)
            )
        elif action == "work":
            from .worker import work

            return work(args.state_dir, args.lock_fd)
        elif action == "call":
            connection = Connection.model_validate_json(
                read_private(args.connection, maximum=16384)
            )
            request = parse(sys.stdin.buffer.read(MAX_REQUEST + 1))
            result = asyncio.run(
                call(
                    connection,
                    read_private(args.identity, maximum=16384),
                    request,
                )
            )
        else:
            from . import lifecycle

            result = getattr(lifecycle, action)(args.state_dir)
        print(json.dumps(result, allow_nan=False))
        return 0
    except HostControlError as error:
        print(json.dumps({"ok": False, "error": {"code": error.code, "message": str(error)}}))
        return 2
    except Exception:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "host_control_unavailable",
                        "message": "Inspect this host's protected configuration and operation status.",
                    },
                }
            )
        )
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(prog="mnemion-service host-control")
    arguments(parser)
    return execute(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
