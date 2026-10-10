"""Preview or safely install an MCP connection without changing agent policies."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import tomlkit

CLIENTS = {
    "codex": ("toml", "mcp_servers"),
    "claude-code": ("json", "mcpServers"),
    "claude-desktop": ("json", "mcpServers"),
    "cursor": ("json", "mcpServers"),
    "windsurf": ("json", "mcpServers"),
    "devin": ("json", "mcpServers"),
    "gemini-cli": ("json", "mcpServers"),
    "zed": ("json", "context_servers"),
    "generic": ("json", "mcpServers"),
}


def default_path(client: str) -> Path:
    home = Path.home()
    if client == "codex":
        return Path(os.environ.get("CODEX_HOME", str(home / ".codex"))) / "config.toml"
    if client == "zed" and sys.platform == "win32":
        if not os.environ.get("APPDATA"):
            raise ValueError("Set an explicit config path for this Windows profile")
        return Path(os.environ["APPDATA"]) / "Zed/settings.json"
    if client == "devin":
        if sys.platform == "win32":
            if not os.environ.get("APPDATA"):
                raise ValueError("Set an explicit config path for this Windows profile")
            return Path(os.environ["APPDATA"]) / "devin/mcp_config.json"
        return (
            Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))) / "devin/mcp_config.json"
        )
    paths = {
        "claude-code": home / ".claude.json",
        "cursor": home / ".cursor/mcp.json",
        "windsurf": home / ".codeium/windsurf/mcp_config.json",
        "gemini-cli": home / ".gemini/settings.json",
        "zed": home / ".config/zed/settings.json",
    }
    if client == "claude-desktop":
        if sys.platform == "win32":
            if not os.environ.get("APPDATA"):
                raise ValueError("Set an explicit config path for this Windows profile")
            return Path(os.environ["APPDATA"]) / "Claude/claude_desktop_config.json"
        if sys.platform == "darwin":
            return home / "Library/Application Support/Claude/claude_desktop_config.json"
        raise ValueError("Choose an explicit config path for a third-party Linux desktop client")
    if client not in paths:
        raise ValueError("Provide --config for a generic MCP client")
    return paths[client]


def server_config(
    credentials: Path, *, python: str = sys.executable, legacy_space: str | None = None
) -> dict:
    args = [
        "-m",
        "mnemion.service.cli",
        "--credentials",
        str(credentials.expanduser().absolute()),
        "mcp",
    ]
    if legacy_space:
        args.extend(["--legacy-space", str(UUID(legacy_space))])
    return {"command": python, "args": args}


@dataclass(frozen=True)
class Plan:
    path: Path
    expected_hash: str | None
    content: bytes
    snippet: str
    replacing: bool


def plan(
    client: str,
    target: Path,
    credentials: Path,
    *,
    python=sys.executable,
    legacy_space=None,
    remove=False,
) -> Plan:
    fmt, key = CLIENTS[client]
    target = target.expanduser().absolute()
    if target.is_symlink():
        raise ValueError("Choose the actual configuration file instead of replacing a symlink")
    original = target.read_bytes() if target.exists() else None
    if original is not None and len(original) > 4_000_000:
        raise ValueError("Agent configuration exceeds 4 MB")
    node = server_config(credentials, python=python, legacy_space=legacy_space)
    if fmt == "toml":
        try:
            document = tomlkit.parse(original.decode("utf-8") if original else "")
        except Exception:
            raise ValueError("Existing TOML is invalid; no settings were changed") from None
        if key in document and not isinstance(document[key], dict):
            raise ValueError("The existing MCP configuration is not a table")
        if key not in document:
            document[key] = tomlkit.table()
        replacing = "mnemion" in document[key]
        if remove:
            document[key].pop("mnemion", None)
        else:
            document[key]["mnemion"] = node
        result = tomlkit.dumps(document)
        rendered = tomlkit.document()
        rendered[key] = {"mnemion": node}
        snippet = tomlkit.dumps(rendered)
        # Parsing the result catches unsupported escaping and malformed tables.
        tomlkit.parse(result)
    else:
        try:
            document = json.loads(original.decode("utf-8") if original else "{}")
        except (ValueError, UnicodeError):
            raise ValueError(
                "Existing JSON is invalid or uses comments; merge the preview manually"
            ) from None
        if not isinstance(document, dict) or (
            key in document and not isinstance(document[key], dict)
        ):
            raise ValueError("The existing MCP configuration is not an object")
        document.setdefault(key, {})
        replacing = "mnemion" in document[key]
        if remove:
            document[key].pop("mnemion", None)
        else:
            document[key]["mnemion"] = node
        result = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        snippet = json.dumps({key: {"mnemion": node}}, ensure_ascii=False, indent=2)
    if remove and not replacing:
        result = original.decode("utf-8") if original is not None else ""
    return Plan(
        target,
        hashlib.sha256(original).hexdigest() if original is not None else None,
        result.encode("utf-8"),
        "Remove only the mnemion MCP entry" if remove else snippet,
        replacing,
    )


def apply(plan: Plan) -> dict:
    target = plan.path
    if target.is_symlink():
        raise ValueError("The configuration became a symlink; preview it again")
    current = target.read_bytes() if target.exists() else None
    digest = hashlib.sha256(current).hexdigest() if current is not None else None
    if digest != plan.expected_hash:
        raise ValueError("Agent settings changed after preview; preview again before applying")
    if current == plan.content or (current is None and not plan.content):
        return {"changed": False, "path": str(target), "backup": None}
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if current is not None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = target.with_name(target.name + f".mnemion-backup-{stamp}")
        descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            file.write(current)
            file.flush()
            os.fsync(file.fileno())
    descriptor, temporary = tempfile.mkstemp(prefix=".mnemion-agent-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(plan.content)
            file.flush()
            os.fsync(file.fileno())
        # Compare once more after writing the backup/stage. Cooperating editors
        # can still race the final replace, so close the client during setup.
        latest = target.read_bytes() if target.exists() else None
        if latest != current:
            raise ValueError("Agent settings changed during setup; no replacement was made")
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {"changed": True, "path": str(target), "backup": str(backup) if backup else None}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Preview or install a Mnemion connection in an MCP client"
    )
    parser.add_argument("--client", choices=sorted(CLIENTS), required=True)
    parser.add_argument(
        "--config", type=Path, help="Explicit target; defaults to this operating-system profile"
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        required=True,
        help="Private application credentials; contents are not printed",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter containing the installed Mnemion client",
    )
    parser.add_argument("--legacy-space", help="Enable v3/Open Brain aliases within this space")
    parser.add_argument(
        "--apply", action="store_true", help="Apply the previewed entry and create a private backup"
    )
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove only Mnemion's entry; --apply is still required",
    )
    args = parser.parse_args(argv)
    try:
        planned = plan(
            args.client,
            args.config or default_path(args.client),
            args.credentials,
            python=args.python,
            legacy_space=args.legacy_space,
            remove=args.remove,
        )
        result = (
            apply(planned)
            if args.apply
            else {
                "changed": False,
                "preview": True,
                "path": str(planned.path),
                "replacing_mnemion": planned.replacing,
                "snippet": planned.snippet,
            }
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        # Configuration contents and tokens never enter diagnostics.
        print(
            json.dumps(
                {
                    "error": "agent_setup_failed",
                    "message": str(exc)
                    if isinstance(exc, ValueError)
                    else "The selected configuration file could not be accessed",
                }
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
