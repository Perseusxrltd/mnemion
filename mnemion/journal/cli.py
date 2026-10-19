"""Local operator enrollment; API principals cannot choose executable paths or hosts."""

import json
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from .. import local_state
from .config import Configuration, Destination, SshAuthentication
from .format import JournalError


def arguments(parser):
    commands = parser.add_subparsers(dest="journal_command", required=True)
    status = commands.add_parser(
        "status", help="Validate a private host registry without reading memory content"
    )
    status.add_argument("--config", type=Path, required=True)
    enroll = commands.add_parser(
        "enroll",
        help="Register a destination locally; an administrator approves publication in the app",
    )
    enroll.add_argument("--config", type=Path, required=True)
    enroll.add_argument("--id", required=True)
    enroll.add_argument("--label", required=True)
    enroll.add_argument("--tenant", type=UUID, required=True)
    enroll.add_argument("--space", type=UUID, required=True)
    enroll.add_argument("--state", type=Path, required=True)
    repository = enroll.add_mutually_exclusive_group(required=True)
    repository.add_argument(
        "--remote",
        help="HTTPS URL with Git credentials, or ssh://user@host/repository with dedicated key and host pins",
    )
    repository.add_argument(
        "--local-repository",
        type=Path,
        help="An explicit local bare repository, useful for offline setups",
    )
    enroll.add_argument("--branch", default="main")
    enroll.add_argument("--prefix", default="memory/buffer")
    enroll.add_argument(
        "--ssh-key-file", type=Path, help="Owner-only deploy key for this SSH repository"
    )
    enroll.add_argument(
        "--ssh-known-hosts-file",
        type=Path,
        help="Owner-only known-hosts file containing independently verified host keys",
    )
    enroll.add_argument(
        "--expected-fingerprint", help="Required when replacing an existing registration"
    )


def execute(args):
    try:
        path = args.config.absolute()
        if args.journal_command == "status":
            config = Configuration.from_file(path)
        else:
            destination = Destination(
                id=args.id,
                label=args.label,
                tenant_id=args.tenant,
                space_id=args.space,
                state_directory=args.state.absolute(),
                remote=args.remote,
                local_repository=args.local_repository.absolute()
                if args.local_repository
                else None,
                branch=args.branch,
                prefix=args.prefix,
                ssh=SshAuthentication(
                    identity_file=args.ssh_key_file, known_hosts_file=args.ssh_known_hosts_file
                )
                if args.ssh_key_file is not None or args.ssh_known_hosts_file is not None
                else None,
            )
            if destination.ssh:
                from .ssh import credential_bytes

                credential_bytes(destination.ssh)
            local_state.directory(path.parent)
            with local_state.lock(path.parent):
                existing = path.exists() or path.is_symlink()
                config = Configuration.from_file(path) if existing else Configuration()
                old = next((d for d in config.destinations if d.id == destination.id), None)
                if (old.fingerprint if old else None) != args.expected_fingerprint:
                    raise JournalError("journal_registration_changed")
                config = Configuration(
                    destinations=[d for d in config.destinations if d.id != destination.id]
                    + [destination]
                )
                local_state.write(
                    path, config.model_dump(mode="json", exclude_none=True), replace=existing
                )
        print(
            json.dumps(
                {
                    "configured": True,
                    "destinations": [
                        {
                            "id": d.id,
                            "label": d.label,
                            "tenant_id": str(d.tenant_id),
                            "space_id": str(d.space_id),
                            "fingerprint": d.fingerprint,
                            "destination_kind": d.kind,
                        }
                        for d in config.destinations
                    ],
                    "next": "Set MNEMION_WRITEBACK_CONFIG to this private file for the API host, restart it, and approve the destination in Studio > Git journal.",
                }
            )
        )
        return 0
    except (JournalError, OSError, ValueError, local_state.LocalSetupError) as error:
        # Validation errors can contain the raw proposed remote URL. Never
        # reflect inputs that might have included an accidental credential.
        code = (
            error.code
            if isinstance(error, JournalError)
            else "journal_registration_invalid"
            if isinstance(error, ValidationError)
            else "journal_registration_unavailable"
        )
        print(
            json.dumps(
                {
                    "error": code,
                    "message": "Check the private registry, scope IDs, safe Git URL, SSH credential files if selected, and current registration fingerprint.",
                }
            )
        )
        return 1
