"""Credential-free, provider-specific connection packages authored by Perseus XR."""

from __future__ import annotations

import argparse
import base64
import hashlib
from importlib.resources import files
from io import BytesIO
import json
from pathlib import Path
import sys
from typing import Literal
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .private_output import private_output
from .version import __version__

Provider = Literal["openai", "claude", "grok-build", "hermes", "openclaw", "grokbot"]
Kind = Literal["plugin", "configuration", "guide"]
AUTHOR = "Perseus XR"
WEBSITE = "https://www.perseusxr.com/mnemion"
REPOSITORY = "https://github.com/Perseusxrltd/mnemion"
DESCRIPTION = "Shared, permission-controlled memory for your agents and teams."
PROVIDERS = {
    "openai": ("OpenAI / Codex", "plugin"),
    "claude": ("Claude Code", "plugin"),
    "grok-build": ("Grok Build", "plugin"),
    "hermes": ("Hermes", "configuration"),
    "openclaw": ("OpenClaw", "configuration"),
    "grokbot": ("Grok Bot", "guide"),
}
GUIDES = {
    "openai": """Import this portable plugin through the client's supported plugin flow.
The package includes root plugin.json and mcp.json. It uses OAuth discovery;
there is no embedded client secret or personal app ID. In ChatGPT, a supported
alternative is Plugins → Add → Add custom MCP server, using the address below
and OAuth. Dot and other surfaces use their enabled account's supported plugin
flow; availability and administrator policy differ. Private cloud listings may
display the creating account despite package author metadata. This is not a
verified public directory listing.

Reference: https://developers.openai.com/plugins/build/plugins
""",
    "claude": """Extract the ZIP into a new folder. Load that folder through Claude Code's
plugin manager, or pass it as the argument to `claude --plugin-dir`. The
.claude-plugin/plugin.json declares the remote MCP server. Complete OAuth when
Claude requests it; inspect the connection with /mcp. Claude Desktop and hosted
Claude connectors have their own supported registration flow: use the MCP
address and OAuth there rather than assuming a Code plugin installs everywhere.

Reference: https://code.claude.com/docs/en/plugins-reference
""",
    "grok-build": """Extract the ZIP into a new folder. Install it with `grok plugin install`,
using the folder as a separate argument. Grok Build supports this Claude-compatible
plugin manifest. Open /mcps to authenticate and refresh tools, and use
`grok mcp doctor mnemion --json` to inspect the connection. Grok Bot's cloud
Connect apps catalog is a separate integration surface; this package does not
publish a Bot marketplace listing.

Reference: https://docs.x.ai/build/features/skills-plugins-marketplaces
""",
    "hermes": """Merge only mcp_servers.mnemion from config.yaml into the active Hermes
profile's config.yaml. Preserve the other settings and servers. The usual
location is $HERMES_HOME/config.yaml, or ~/.hermes/config.yaml. Run
`hermes mcp login mnemion`, then /reload-mcp in the intended session. The
gateway also watches its active configuration. This is native MCP configuration,
not an entry approved for the Nous catalog. Mnemion's app and mnemion-agent
also install a separate private stdio connection using the Hermes profile.

Reference: https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp
""",
    "openclaw": """Merge only mcp.servers.mnemion from openclaw.json into the active
OpenClaw configuration, or give that server object to `openclaw mcp set`.
Preserve existing configuration and includes. Run `openclaw mcp login mnemion`,
then `openclaw mcp probe mnemion` to check tools without a model turn. This
configuration uses operator-managed OAuth shared by that gateway. Give it a
dedicated account with the needed spaces; it is not each employee's identity.
Per-requester OAuth is a separate OpenClaw setting and currently has a documented
shared-channel sign-in-link limitation. Mnemion's native app also installs
private stdio connections for OpenClaw. This is not an OpenClaw SDK plugin.

Reference: https://docs.openclaw.ai/cli/mcp
""",
    "grokbot": """This is a connection guide and machine-readable connection card, not an
importable marketplace plugin. In a Grok surface that offers custom MCP
connectors, add the MCP address below and choose OAuth. Complete Mnemion sign-in
and permission review. Grok Bot's Connect apps catalog and custom connector
availability depend on the enabled account and provider policy. If only the
catalog is offered, do not treat this ZIP as an accepted catalog submission.
The host must stay reachable independently of the Bot's quota or computer.
An existing stable public HTTPS host needs no ngrok tunnel. Bot computer files
and installed connectors can be shared by all Bots on the same account.

References:
- https://docs.x.ai/grok-bot/computer-and-apps
- https://docs.x.ai/grok/connectors/custom-mcp-tunneling
""",
}


def mcp_address(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 2048:
        raise ValueError("Use the workspace's complete HTTPS MCP address")
    try:
        if any(ord(c) <= 32 or ord(c) == 127 for c in value):
            raise ValueError()
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or any(c in value for c in "\\<>\"'`")
        ):
            raise ValueError()
        url.port
    except ValueError:
        raise ValueError(
            "Use an HTTPS MCP address without credentials, query or fragment"
        ) from None
    return value


def catalog() -> dict:
    return {
        "author": AUTHOR,
        "version": __version__,
        "providers": [
            {"id": key, "name": label, "kind": kind} for key, (label, kind) in PROVIDERS.items()
        ],
        "authentication": "oauth",
        "contains_credentials": False,
        "public_directory_listing": False,
    }


def build(provider: str, mcp_url: str) -> dict:
    if provider not in PROVIDERS:
        raise ValueError("Choose a supported connection package")
    endpoint = mcp_address(mcp_url)
    label, kind = PROVIDERS[provider]
    author = {"name": AUTHOR, "url": "https://www.perseusxr.com"}
    manifest = {
        "name": "mnemion",
        "version": __version__,
        "description": DESCRIPTION,
        "author": author,
        "homepage": WEBSITE,
        "repository": REPOSITORY,
        "license": "MIT",
        "keywords": ["memory", "teams", "mcp"],
    }
    content = {}

    def add_json(path, value):
        content[path] = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()

    if provider == "openai":
        manifest["$schema"] = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
        manifest["extensions"] = {
            "com.openai": {
                "interface": {
                    "displayName": "Mnemion Shared Memory",
                    "shortDescription": DESCRIPTION,
                    "developerName": AUTHOR,
                    "category": "Productivity",
                    "capabilities": ["Read", "Write"],
                    "websiteURL": WEBSITE,
                    "brandColor": "#c49a55",
                    "composerIcon": "./assets/icon.png",
                    "logo": "./assets/icon.png",
                }
            }
        }
        add_json("plugin.json", manifest)
        add_json(
            "mcp.json",
            {
                "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
                "mcpServers": {"mnemion": {"type": "streamable-http", "url": endpoint}},
            },
        )
    elif provider in {"claude", "grok-build"}:
        manifest["mcpServers"] = {"mnemion": {"type": "http", "url": endpoint}}
        # Claude Code 2.1.59 rejects the newer directory-only icon field.
        # The canonical image remains in the package and its rendered guide.
        if provider == "grok-build":
            manifest["icon"] = "./assets/icon.png"
        add_json(".claude-plugin/plugin.json", manifest)
    elif provider == "hermes":
        # JSON-quoted URL is a YAML double-quoted scalar as well.
        content["config.yaml"] = (
            "mcp_servers:\n  mnemion:\n    url: " + json.dumps(endpoint) + "\n    auth: oauth\n"
        ).encode()
    elif provider == "openclaw":
        add_json(
            "openclaw.json",
            {
                "mcp": {
                    "servers": {
                        "mnemion": {
                            "url": endpoint,
                            "transport": "streamable-http",
                            "auth": "oauth",
                        }
                    }
                }
            },
        )
    add_json(
        "connection.json",
        {
            "schema": 1,
            "name": "Mnemion",
            "author": AUTHOR,
            "version": __version__,
            "provider": provider,
            "kind": kind,
            "mcp_url": endpoint,
            "authentication": "oauth",
            "website": WEBSITE,
            "contains_credentials": False,
        },
    )
    content["assets/icon.png"] = files("mnemion").joinpath("assets/connector-icon.png").read_bytes()
    content["README.md"] = (
        f"# Mnemion for {label}\n\n![Mnemion](assets/icon.png)\n\nBy {AUTHOR}. Version {__version__}.\n\n"
        + GUIDES[provider]
        + f"\nMCP address: {endpoint}\n\n"
        "The package contains no API key, password, OAuth token or personal app ID.\n"
        "After connecting, use memory_profile to verify the principal and workspace.\n"
        "The connection uses the signed-in account's actual permissions, including\n"
        "future changes. Use a separate account for narrower assistant access.\n"
        "MCP access and automatic conversation capture are separate settings.\n"
        "Cloud assistants need to reach the host over HTTPS; local-only addresses\n"
        "and an offline host are not made reachable by installing a package.\n\n"
        f"Setup, native agent controls and help: {WEBSITE}\n"
    ).encode()
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in sorted(content.items()):
            entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    raw = output.getvalue()
    if len(raw) > 128 * 1024:
        raise ValueError("The connection package exceeds its download bound")
    return {
        "provider": provider,
        "kind": kind,
        "author": AUTHOR,
        "version": __version__,
        "filename": f"mnemion-{provider}-{__version__}.zip",
        "media_type": "application/zip",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "content_base64": base64.b64encode(raw).decode("ascii"),
        "contains_credentials": False,
    }


def arguments(parser):
    parser.add_argument("--catalog", action="store_true", help="Discover package types as JSON")
    parser.add_argument("--provider", choices=sorted(PROVIDERS))
    parser.add_argument("--mcp-url", help="HTTPS workspace MCP address, with no credential")
    parser.add_argument("--output", type=Path, help="New ZIP destination; never replaces a file")


def dispatch(args) -> int:
    try:
        if args.catalog:
            if args.provider or args.mcp_url or args.output:
                raise ValueError("Use --catalog separately from package creation")
            print(json.dumps(catalog()))
            return 0
        if not args.provider or not args.mcp_url or not args.output:
            raise ValueError("Use --provider, --mcp-url and --output, or --catalog")
        result = build(args.provider, args.mcp_url)
        target = args.output.expanduser().absolute()
        with private_output(target) as stream:
            stream.write(base64.b64decode(result.pop("content_base64"), validate=True))
        print(json.dumps({**result, "path": str(target)}))
        return 0
    except (ValueError, OSError) as exc:
        print(
            json.dumps(
                {
                    "error": "agent_package_failed",
                    "message": str(exc)
                    if isinstance(exc, ValueError)
                    else "The new package could not be written; existing files were preserved",
                }
            ),
            file=sys.stderr,
        )
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    arguments(parser)
    return dispatch(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
