"""
Agent connector system — detects and installs Mnemion into MCP-capable clients.

Each connector describes one AI tool (Claude Code, Cursor, Codex, …) and how
to read/write its MCP config safely. Supports JSON (most tools) and TOML (Codex).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SERVER_NAME = "mnemion"
LEGACY_NAMES = ("mempalace",)  # clean these up on install
PYTHON_CMD = sys.executable.replace("\\", "/")  # cross-platform absolute path
PYTHON_ARGS = ["-m", "mnemion.mcp_server"]


# ── Registry ──────────────────────────────────────────────────────────────────

@dataclass
class Connector:
    id: str
    name: str
    vendor: str
    category: str         # cli | app | ide
    description: str
    config_path: str      # can include $APPDATA or ~
    config_paths_os: Optional[dict] = None  # OS-specific override
    fmt: str = "json"     # json | toml
    mcp_key: str = "mcpServers"
    doc_url: str = ""
    install_note: str = ""


CONNECTORS: list[Connector] = [
    Connector(
        id="claude-code",
        name="Claude Code",
        vendor="Anthropic",
        category="cli",
        description="Anthropic's command-line coding agent. User-scope MCP config.",
        config_path="~/.claude.json",
        mcp_key="mcpServers",
        doc_url="https://docs.claude.com/en/docs/claude-code/mcp",
        install_note="Restart Claude Code after installing.",
    ),
    Connector(
        id="claude-code-project",
        name="Claude Code (project)",
        vendor="Anthropic",
        category="cli",
        description="Project-scope MCP config (.mcp.json in current directory).",
        config_path=".mcp.json",
        mcp_key="mcpServers",
        doc_url="https://docs.claude.com/en/docs/claude-code/mcp",
        install_note="Creates .mcp.json in the Studio launch directory.",
    ),
    Connector(
        id="claude-desktop",
        name="Claude Desktop",
        vendor="Anthropic",
        category="app",
        description="Anthropic's desktop app. Settings → Developer → Edit Config.",
        config_path="",  # resolved per-OS
        config_paths_os={
            "win32":  "%APPDATA%/Claude/claude_desktop_config.json",
            "darwin": "~/Library/Application Support/Claude/claude_desktop_config.json",
            "linux":  "~/.config/Claude/claude_desktop_config.json",
        },
        mcp_key="mcpServers",
        install_note="Quit Claude Desktop (not just close) after installing.",
    ),
    Connector(
        id="cursor",
        name="Cursor",
        vendor="Cursor",
        category="ide",
        description="AI-first code editor. Global user MCP config.",
        config_path="~/.cursor/mcp.json",
        mcp_key="mcpServers",
        doc_url="https://docs.cursor.com/context/model-context-protocol",
    ),
    Connector(
        id="windsurf",
        name="Windsurf",
        vendor="Codeium",
        category="ide",
        description="Agent-powered editor by Codeium.",
        config_path="~/.codeium/windsurf/mcp_config.json",
        mcp_key="mcpServers",
    ),
    Connector(
        id="codex",
        name="Codex CLI",
        vendor="OpenAI",
        category="cli",
        description="OpenAI's command-line coding agent. TOML config.",
        config_path="~/.codex/config.toml",
        fmt="toml",
        mcp_key="mcp_servers",
        doc_url="https://github.com/openai/codex",
        install_note="Restart Codex after installing.",
    ),
    Connector(
        id="gemini-cli",
        name="Gemini CLI",
        vendor="Google",
        category="cli",
        description="Google's Gemini command-line agent.",
        config_path="~/.gemini/settings.json",
        mcp_key="mcpServers",
        doc_url="https://github.com/google-gemini/gemini-cli",
    ),
    Connector(
        id="zed",
        name="Zed",
        vendor="Zed Industries",
        category="ide",
        description="High-performance code editor with MCP context servers.",
        config_path="~/.config/zed/settings.json",
        mcp_key="context_servers",
    ),
]


def get(conn_id: str) -> Optional[Connector]:
    return next((c for c in CONNECTORS if c.id == conn_id), None)


# ── Path resolution ───────────────────────────────────────────────────────────

def resolve_path(c: Connector) -> Path:
    raw = c.config_path
    if c.config_paths_os:
        raw = c.config_paths_os.get(sys.platform) or raw
    raw = os.path.expandvars(raw)
    raw = os.path.expanduser(raw)
    return Path(raw).resolve()


# ── JSON helpers ──────────────────────────────────────────────────────────────

def _read_json(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return {}


def _write_json(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ── TOML helpers (minimal writer for Codex format) ───────────────────────────

def _toml_has_block(text: str, block: str) -> bool:
    pattern = rf"^\s*\[{re.escape(block)}\]\s*$"
    return bool(re.search(pattern, text, re.MULTILINE))


def _toml_remove_block(text: str, block: str) -> str:
    """Remove [block] and its lines until the next [section] or EOF."""
    pattern = rf"(^\s*\[{re.escape(block)}\][^\n]*\n(?:(?!\s*\[).+\n?)*)"
    return re.sub(pattern, "", text, flags=re.MULTILINE)


def _toml_args_literal(args: list[str]) -> str:
    """Render a TOML array of strings."""
    quoted = [json.dumps(a) for a in args]  # json gives us the right escaping
    return "[" + ", ".join(quoted) + "]"


def _render_mnemion_toml_block(mcp_key: str) -> str:
    return (
        f"\n[{mcp_key}.{SERVER_NAME}]\n"
        f"command = {json.dumps(PYTHON_CMD)}\n"
        f"args = {_toml_args_literal(PYTHON_ARGS)}\n"
    )


# ── Backup ────────────────────────────────────────────────────────────────────

def _backup(p: Path) -> Optional[Path]:
    if not p.exists():
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    backup_dir = p.parent / ".mnemion_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    bpath = backup_dir / f"{p.name}.{ts}.bak"
    shutil.copy2(p, bpath)
    return bpath


# ── Public API ────────────────────────────────────────────────────────────────

def detect(c: Connector) -> dict:
    """Return status for a connector without modifying anything."""
    p = resolve_path(c)
    status = {
        "id": c.id,
        "name": c.name,
        "vendor": c.vendor,
        "category": c.category,
        "description": c.description,
        "doc_url": c.doc_url,
        "install_note": c.install_note,
        "config_path": str(p),
        "format": c.fmt,
        "installed": p.exists(),
        "mnemion_configured": False,
        "other_mcp_servers": [],
        "legacy_detected": False,
        "error": None,
    }
    if not p.exists():
        return status

    try:
        if c.fmt == "json":
            data = _read_json(p)
            servers = data.get(c.mcp_key) or {}
            if isinstance(servers, dict):
                status["mnemion_configured"] = SERVER_NAME in servers
                status["legacy_detected"] = any(n in servers for n in LEGACY_NAMES)
                status["other_mcp_servers"] = [
                    k for k in servers.keys()
                    if k != SERVER_NAME and k not in LEGACY_NAMES
                ]
        elif c.fmt == "toml":
            text = p.read_text(encoding="utf-8")
            status["mnemion_configured"] = _toml_has_block(text, f"{c.mcp_key}.{SERVER_NAME}")
            status["legacy_detected"] = any(
                _toml_has_block(text, f"{c.mcp_key}.{n}") for n in LEGACY_NAMES
            )
            # Extract other server names from [mcp_key.XXX] blocks
            other_pattern = rf"^\s*\[{re.escape(c.mcp_key)}\.([^\]]+)\]"
            names = re.findall(other_pattern, text, re.MULTILINE)
            status["other_mcp_servers"] = [
                n for n in set(names)
                if n != SERVER_NAME and n not in LEGACY_NAMES
            ]
    except Exception as exc:
        status["error"] = str(exc)

    return status


def install(c: Connector) -> dict:
    """Add Mnemion to the connector's MCP config. Backs up first. Removes legacy entries."""
    p = resolve_path(c)
    backup_path: Optional[Path] = _backup(p)

    try:
        if c.fmt == "json":
            data = _read_json(p)
            data.setdefault(c.mcp_key, {})
            if not isinstance(data[c.mcp_key], dict):
                raise ValueError(
                    f"{c.mcp_key} is not an object (got {type(data[c.mcp_key]).__name__})"
                )
            # Drop legacy entries
            for legacy in LEGACY_NAMES:
                data[c.mcp_key].pop(legacy, None)
            # Add Mnemion
            data[c.mcp_key][SERVER_NAME] = {
                "command": PYTHON_CMD,
                "args": PYTHON_ARGS,
            }
            _write_json(p, data)

        elif c.fmt == "toml":
            text = p.read_text(encoding="utf-8") if p.exists() else ""
            # Remove legacy blocks
            for legacy in LEGACY_NAMES:
                text = _toml_remove_block(text, f"{c.mcp_key}.{legacy}")
            # Remove existing mnemion block to rewrite cleanly
            text = _toml_remove_block(text, f"{c.mcp_key}.{SERVER_NAME}")
            text = text.rstrip() + _render_mnemion_toml_block(c.mcp_key)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text + "\n" if not text.endswith("\n") else text, encoding="utf-8")

        else:
            raise ValueError(f"Unsupported format: {c.fmt}")

        return {
            "success": True,
            "config_path": str(p),
            "backup_path": str(backup_path) if backup_path else None,
            "note": c.install_note,
        }

    except Exception as exc:
        # Restore from backup on failure
        if backup_path and backup_path.exists():
            shutil.copy2(backup_path, p)
        return {"success": False, "error": str(exc), "config_path": str(p)}


def uninstall(c: Connector) -> dict:
    p = resolve_path(c)
    if not p.exists():
        return {"success": True, "note": "Config file did not exist."}

    backup_path = _backup(p)
    try:
        if c.fmt == "json":
            data = _read_json(p)
            servers = data.get(c.mcp_key)
            if isinstance(servers, dict):
                for n in (SERVER_NAME, *LEGACY_NAMES):
                    servers.pop(n, None)
                if not servers:
                    data.pop(c.mcp_key, None)
            _write_json(p, data)

        elif c.fmt == "toml":
            text = p.read_text(encoding="utf-8")
            for n in (SERVER_NAME, *LEGACY_NAMES):
                text = _toml_remove_block(text, f"{c.mcp_key}.{n}")
            p.write_text(text, encoding="utf-8")

        return {"success": True, "backup_path": str(backup_path) if backup_path else None}

    except Exception as exc:
        if backup_path and backup_path.exists():
            shutil.copy2(backup_path, p)
        return {"success": False, "error": str(exc)}


def snippet(c: Connector) -> str:
    """Return a copy-pasteable MCP config snippet for manual setup."""
    if c.fmt == "json":
        body = json.dumps(
            {c.mcp_key: {SERVER_NAME: {"command": PYTHON_CMD, "args": PYTHON_ARGS}}},
            indent=2,
        )
        return body
    if c.fmt == "toml":
        return f"[{c.mcp_key}.{SERVER_NAME}]\ncommand = {json.dumps(PYTHON_CMD)}\nargs = {_toml_args_literal(PYTHON_ARGS)}"
    return ""


def detect_all() -> list[dict]:
    return [detect(c) for c in CONNECTORS]
