"""Preview or safely install an MCP connection without changing agent policies."""

from __future__ import annotations

import argparse
from collections.abc import MutableMapping
from copy import deepcopy
import hashlib
from io import StringIO
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from .private_output import private_output

CLIENTS = {
    "codex": ("toml", "mcp_servers"),
    "grok-build": ("toml", "mcp_servers"),
    "hermes": ("yaml", "mcp_servers"),
    "openclaw": ("json5", "mcp.servers"),
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
    if client == "hermes":
        return (
            Path(os.environ.get("HERMES_HOME", str(home / ".hermes"))).expanduser() / "config.yaml"
        )
    if client == "openclaw":
        override = os.environ.get("OPENCLAW_HOME", "").strip()
        if override and override not in {"undefined", "null"}:
            home = Path(override).expanduser()

        def path(value):
            return (
                home / value[2:]
                if value.startswith(("~/", "~\\"))
                else home
                if value == "~"
                else Path(value)
            )

        if value := os.environ.get("OPENCLAW_CONFIG_PATH", "").strip():
            return path(value)
        if value := os.environ.get("OPENCLAW_STATE_DIR", "").strip():
            return path(value) / "openclaw.json"
        profile = os.environ.get("OPENCLAW_PROFILE", "default").strip() or "default"
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", profile):
            raise ValueError("Choose an explicit configuration path for this OpenClaw profile")
        suffix = "" if profile.lower() == "default" else "-" + profile
        return home / (".openclaw" + suffix) / "openclaw.json"
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
        "grok-build": home / ".grok/config.toml",
        "claude-code": home / ".claude.json",
        "cursor": home / ".cursor/mcp.json",
        "windsurf": home / ".codeium/windsurf/mcp_config.json",
        "gemini-cli": home / ".gemini/settings.json",
        "zed": Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))) / "zed/settings.json",
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
    credentials: Path,
    *,
    python: str = sys.executable,
    legacy_space: str | None = None,
    standalone: bool = False,
) -> dict:
    args = ([] if standalone else ["-m", "mnemion.service.cli"]) + [
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


def configuration(path: Path) -> bytes | None:
    if path.is_symlink():
        raise ValueError("Choose the actual configuration file instead of replacing a symlink")
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Choose an ordinary agent configuration file")
        with path.open("rb") as stream:
            content = stream.read(4_000_001)
    except FileNotFoundError:
        return None
    if len(content) > 4_000_000:
        raise ValueError("Agent configuration exceeds 4 MB")
    return content


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate configuration key")
        result[key] = value
    return result


def _yaml():
    from ruamel.yaml import YAML

    parser = YAML(typ="rt", pure=True)
    parser.preserve_quotes = True
    parser.allow_duplicate_keys = False
    return parser


def document(client: str, content: bytes | None):
    """Read authored settings without following includes or exposing parse values."""
    fmt, _ = CLIENTS[client]
    try:
        source = content.decode("utf-8") if content else ""
        if fmt == "toml":
            import tomlkit

            value = tomlkit.parse(source)
        elif fmt == "yaml":
            value = _yaml().load(source)
            if value is None:
                value = {}
        elif fmt == "json5":
            import json5

            value = json5.loads(source or "{}", allow_duplicate_keys=False)
        else:
            value = json.loads(source or "{}", object_pairs_hook=_unique_object)
    except Exception:
        label = {"toml": "TOML", "yaml": "YAML", "json5": "JSON5", "json": "JSON"}[fmt]
        raise ValueError(
            f"Existing {label} is invalid or ambiguous; no settings were changed"
        ) from None
    if not isinstance(value, MutableMapping):
        raise ValueError("The existing agent configuration is not an object")
    return value


def servers(client: str, value, *, editing=False):
    """Only detach the edited path; YAML aliases must not change other settings."""
    for key in CLIENTS[client][1].split("."):
        if key not in value:
            if not editing:
                return {}
            value[key] = {}
        if not isinstance(value[key], MutableMapping):
            raise ValueError("The existing MCP configuration is not an object")
        if editing:
            value[key] = deepcopy(value[key])
        value = value[key]
    return value


def render(client: str, value) -> str:
    fmt, _ = CLIENTS[client]
    if fmt == "toml":
        import tomlkit

        return tomlkit.dumps(value)
    if fmt == "yaml":
        stream = StringIO()
        _yaml().dump(value, stream)
        return stream.getvalue()
    # Ordinary JSON is also valid JSON5. The exact authored file is backed up.
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def plan(
    client: str,
    target: Path,
    credentials: Path,
    *,
    python=sys.executable,
    legacy_space=None,
    remove=False,
    server_name="mnemion",
    standalone=False,
    server=None,
) -> Plan:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", server_name):
        raise ValueError(
            "Use a short MCP connection name with letters, digits, underscores or hyphens"
        )
    target = target.expanduser().absolute()
    if target.is_symlink():
        raise ValueError("Choose the actual configuration file instead of replacing a symlink")
    original = configuration(target)
    node = (
        server
        if server is not None
        else server_config(
            credentials, python=python, legacy_space=legacy_space, standalone=standalone
        )
    )
    value = document(client, original)
    section = servers(client, value, editing=True)
    replacing = server_name in section
    unchanged = (remove and not replacing) or (not remove and section.get(server_name) == node)
    if remove:
        section.pop(server_name, None)
    else:
        section[server_name] = node
    result = (
        original.decode("utf-8")
        if unchanged and original is not None
        else ""
        if unchanged
        else render(client, value)
    )
    if not unchanged and document(client, result.encode("utf-8")) != value:
        raise ValueError(
            "Agent settings cannot be preserved in this format; merge the preview manually"
        )
    sample = document(client, None)
    servers(client, sample, editing=True)[server_name] = node
    snippet = render(client, sample)
    return Plan(
        target,
        hashlib.sha256(original).hexdigest() if original is not None else None,
        result.encode("utf-8"),
        f"Remove only the {server_name} MCP entry" if remove else snippet,
        replacing,
    )


def apply(plan: Plan) -> dict:
    target = plan.path
    if target.is_symlink():
        raise ValueError("The configuration became a symlink; preview it again")
    current = configuration(target)
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
        with private_output(backup) as file:
            file.write(current)
    temporary = target.with_name(".mnemion-agent-" + uuid4().hex)
    staged_identity = None
    try:
        with private_output(temporary) as file:
            info = os.fstat(file.fileno())
            staged_identity = info.st_dev, info.st_ino
            file.write(plan.content)
        # Compare once more after writing the backup/stage. Cooperating editors
        # can still race the final replace, so close the client during setup.
        latest = configuration(target)
        if latest != current:
            raise ValueError("Agent settings changed during setup; no replacement was made")
        os.replace(temporary, target)
    finally:
        # An exclusive-creation failure never gives us ownership of that path.
        # Preserve any file that replaced our staging object during cleanup.
        if staged_identity is not None:
            try:
                info = temporary.lstat()
                if (info.st_dev, info.st_ino) == staged_identity:
                    temporary.unlink()
            except FileNotFoundError:
                pass
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
        "--server-name", default="mnemion", help="Distinct MCP name for this workspace"
    )
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="The selected executable is the standalone Mnemion engine",
    )
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
            server_name=args.server_name,
            standalone=args.standalone,
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
