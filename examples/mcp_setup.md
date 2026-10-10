# MCP Integration — Claude Code

> **Compatibility reference, reviewed 2026-10-10.** Legacy MCP setup below describe the optional v3-compatible backend. For shared-platform v1, use the [current service guide](../docs/service/agents.md) and `main`. These historical commands and claims are not the default service architecture or current performance measurements.

## Setup

Run the MCP server:

```bash
python -m mnemion.mcp_server
```

Or add it to Claude Code:

```bash
claude mcp add mnemion -- python -m mnemion.mcp_server
```

## Available Tools

The server exposes the full Mnemion MCP toolset. Common entry points include:

- **mnemion_status** — Anaktoron stats (wings, rooms, drawer counts)
- **mnemion_search** — semantic search across all memories
- **mnemion_list_wings** — list all projects in the Anaktoron

## Usage in Claude Code

Once configured, Claude Code can search your memories directly during conversations.
