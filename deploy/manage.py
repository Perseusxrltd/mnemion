#!/usr/bin/env python3
"""Portable Docker Compose operator commands; requires Python 3.12+ and Docker.

State and one-time credentials remain in the selected private directory. Nothing
is installed into a personal AI client, and no secrets enter command arguments.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parent.parent


def private_directory(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("State directory cannot be a symlink")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "nt":
        identity = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"], check=True, capture_output=True, text=True
        )
        sid = next(csv.reader(io.StringIO(identity.stdout)))[1]
        if not re.fullmatch(r"S-1-\d+(?:-\d+)+", sid):
            raise ValueError("Could not determine the Windows account SID")
        # Replace the DACL, including pre-existing explicit grants. Merely
        # disabling inheritance could leave another account with access.
        script = """$ErrorActionPreference='Stop'
$acl = [System.IO.Directory]::GetAccessControl($env:MNEMION_SETUP_DIRECTORY, [System.Security.AccessControl.AccessControlSections]::Access)
$acl.SetAccessRuleProtection($true, $false)
foreach ($existing in @($acl.Access)) { $acl.RemoveAccessRuleSpecific($existing) }
foreach ($value in @($env:MNEMION_SETUP_SID, 'S-1-5-18')) {
  $identity = New-Object System.Security.Principal.SecurityIdentifier($value)
  $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
  $acl.AddAccessRule($rule)
}
[System.IO.Directory]::SetAccessControl($env:MNEMION_SETUP_DIRECTORY, $acl)
"""
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            env={**os.environ, "MNEMION_SETUP_DIRECTORY": str(path), "MNEMION_SETUP_SID": sid},
            check=True,
            capture_output=True,
        )
    else:
        path.chmod(0o700)
        if path.stat().st_mode & 0o077:
            raise ValueError("Choose a filesystem that supports private directory permissions")


def write_private(path: Path, value: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def settings(state: Path) -> dict:
    path = state / "deployment.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise ValueError("Initialize this state directory first")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("version") != 1 or not re.fullmatch(
        r"[a-z][a-z0-9_-]{0,40}", value.get("project", "")
    ):
        raise ValueError("Invalid deployment settings")
    if not isinstance(value.get("port"), int) or not 1024 <= value["port"] <= 65535:
        raise ValueError("Invalid service port")
    return value


def compose(state: Path, config: dict, arguments: list[str], *, capture=False):
    executable = shutil.which(os.environ.get("MNEMION_DOCKER", "docker"))
    if not executable:
        raise ValueError("Install Docker Engine/Desktop and its Compose plugin first")
    environment = {
        **os.environ,
        "MNEMION_PASSWORD_FILE": (state / "database.password").as_posix(),
        "MNEMION_BACKUP_DIR": (state / "backups").as_posix(),
        "MNEMION_PORT": str(config["port"]),
        "MNEMION_PUBLIC_URL": config["public_url"],
        "MNEMION_TENANT": config["tenant"],
        "MNEMION_OWNER": config["owner"],
        "MNEMION_OPERATOR_UID": str(os.getuid() if hasattr(os, "getuid") else 1000),
        "MNEMION_OPERATOR_GID": str(os.getgid() if hasattr(os, "getgid") else 1000),
    }
    return subprocess.run(
        [
            executable,
            "compose",
            "--project-name",
            config["project"],
            "--file",
            str(ROOT / "compose.yaml"),
            *arguments,
        ],
        env=environment,
        cwd=ROOT,
        check=True,
        capture_output=capture,
        text=True,
    )


def copy_owner(state: Path, config: dict, *, replace: bool = False) -> None:
    output = state / "owner.mnemion-credentials.json"
    if output.exists() and not replace:
        return
    with tempfile.TemporaryDirectory(prefix=".owner-", dir=state) as directory:
        copied = Path(directory) / "owner.json"
        compose(
            state,
            config,
            ["cp", "initialize:/state/operator/owner.json", str(copied)],
            capture=True,
        )
        value = json.loads(copied.read_text(encoding="utf-8"))
        if not isinstance(value.get("api_key"), str) or not value["api_key"].startswith("mnm_"):
            raise ValueError("The initializer did not produce valid owner credentials")
        if output.is_symlink():
            raise ValueError("Owner credential file cannot be a symlink")
        if replace and output.exists():
            write_private(
                state / ("owner.previous-" + uuid4().hex + ".mnemion-credentials.json"),
                output.read_text(encoding="utf-8"),
            )
            staged = Path(directory) / "published.json"
            write_private(staged, json.dumps(value, indent=2) + "\n")
            os.replace(staged, output)
        else:
            write_private(output, json.dumps(value, indent=2) + "\n")
    print(f"Owner credential file: {output}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "init",
            "up",
            "stop",
            "status",
            "logs",
            "credentials",
            "operator",
            "adopt-restored",
        ),
    )
    parser.add_argument("--state-dir", type=Path, default=ROOT / ".mnemion-run")
    parser.add_argument("--project", default="mnemion")
    parser.add_argument("--tenant", default="My organization")
    parser.add_argument("--owner", default="Owner")
    parser.add_argument("--port", type=int, default=7892)
    parser.add_argument("--public-url")
    parser.add_argument("--database", help="Verified restore database to activate")
    parser.add_argument(
        "--recovery-file", help="Recovery credential filename inside the backups directory"
    )
    parser.add_argument(
        "--tenant-id", help="Organization to select from a multi-organization recovery"
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Create private setup files without starting containers",
    )
    args, remaining = parser.parse_known_args(argv)
    if remaining and args.command != "operator":
        parser.error("Unexpected command arguments")
    try:
        # Test before resolve so a selected symlink is not silently followed.
        private_directory(args.state_dir.expanduser().absolute())
        state = args.state_dir.expanduser().resolve()
        if args.command == "init" and not (state / "deployment.json").exists():
            if not re.fullmatch(r"[a-z][a-z0-9_-]{0,40}", args.project):
                raise ValueError("Project must be a lowercase Compose project name")
            if not 1024 <= args.port <= 65535:
                raise ValueError("Choose a service port from 1024 through 65535")
            for name in (args.tenant, args.owner):
                if not 1 <= len(name.strip()) <= 200:
                    raise ValueError("Names must contain 1–200 characters")
            from urllib.parse import urlsplit

            public_url = args.public_url or f"http://127.0.0.1:{args.port}"
            address = urlsplit(public_url)
            if (
                not address.hostname
                or address.username
                or address.password
                or address.query
                or address.fragment
                or (
                    address.scheme != "https"
                    and not (
                        address.scheme == "http"
                        and address.hostname in {"localhost", "127.0.0.1", "::1"}
                    )
                )
            ):
                raise ValueError("Use an HTTPS public URL or loopback HTTP address")
            if not (state / "database.password").exists():
                write_private(state / "database.password", secrets.token_urlsafe(48) + "\n")
            write_private(
                state / "deployment.json",
                json.dumps(
                    {
                        "version": 1,
                        "project": args.project,
                        "tenant": args.tenant,
                        "owner": args.owner,
                        "port": args.port,
                        "public_url": public_url,
                    },
                    indent=2,
                )
                + "\n",
            )
        config = settings(state)
        private_directory(state / "backups")
        if args.prepare_only:
            if args.command != "init":
                raise ValueError("--prepare-only is an init option")
            print(f"Private deployment files prepared in {state}")
            return 0
        if args.command in {"init", "up"}:
            compose(
                state,
                config,
                [
                    "up",
                    "--build",
                    "--detach",
                    "--force-recreate",
                    "--wait",
                    "--wait-timeout",
                    "600",
                ],
            )
            copy_owner(state, config)
            print(f"Mnemion Studio: {config['public_url']}/workspace")
        elif args.command == "adopt-restored":
            if not args.database or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", args.database):
                raise ValueError("--database requires the verified restore database name")
            if not args.recovery_file or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._-]{0,200}\.json", args.recovery_file
            ):
                raise ValueError("--recovery-file requires a JSON filename inside backups")
            recovery_file = state / "backups" / args.recovery_file
            if recovery_file.is_symlink() or not recovery_file.is_file():
                raise ValueError("Recovery credentials must be a regular file inside backups")
            adoption = [
                "--database",
                args.database,
                "--credentials",
                "/backups/" + args.recovery_file,
            ]
            if args.tenant_id:
                adoption.extend(["--tenant-id", str(UUID(args.tenant_id))])
            compose(state, config, ["stop", "api", "worker"])
            compose(
                state, config, ["run", "--rm", "--no-deps", "activate", "adopt-restored", *adoption]
            )
            compose(
                state,
                config,
                [
                    "up",
                    "--detach",
                    "--no-build",
                    "--force-recreate",
                    "--wait",
                    "--wait-timeout",
                    "600",
                ],
            )
            copy_owner(state, config, replace=True)
            print("Restored database activated. Reconnect clients with newly issued credentials.")
        elif args.command == "credentials":
            copy_owner(state, config)
        elif args.command == "stop":
            compose(state, config, ["down"])
            print("Stopped. Database, model and credential volumes are retained.")
        elif args.command == "operator":
            arguments = remaining[1:] if remaining[:1] == ["--"] else remaining
            compose(state, config, ["run", "--rm", "operator", "operator", *arguments])
        else:
            compose(
                state, config, ["ps"] if args.command == "status" else ["logs", "--tail", "100"]
            )
        return 0
    except subprocess.CalledProcessError as exc:
        if "compose" not in exc.cmd:
            print(
                "Private directory setup failed. The current account could not apply the required file permissions.",
                file=sys.stderr,
            )
            return 1
        print(
            f"Docker command failed (exit {exc.returncode}). Inspect service status and the deployment guide; private state was retained.",
            file=sys.stderr,
        )
        return 1
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
