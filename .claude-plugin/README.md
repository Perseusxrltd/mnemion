# Mnemion Claude Code Plugin

A Claude Code plugin that gives your AI a persistent memory system. Mine projects and conversations into a searchable Anaktoron backed by ChromaDB, with 29 MCP tools, auto-save hooks, and 5 guided skills.

## Prerequisites

- Python 3.9+

## Installation

### Claude Code Marketplace

```bash
claude plugin marketplace add Perseusxrltd/mnemion
claude plugin install --scope user mnemion
```

### Local Clone

```bash
claude plugin add /path/to/mnemion
```

## Post-Install Setup

After installing the plugin, run the init command to complete setup (pip install, MCP configuration, etc.):

```
/mnemion:init
```

## Available Slash Commands

| Command | Description |
|---------|-------------|
| `/mnemion:help` | Show available tools, skills, and architecture |
| `/mnemion:init` | Set up Mnemion -- install, configure MCP, onboard |
| `/mnemion:search` | Search your memories across the Anaktoron |
| `/mnemion:mine` | Mine projects and conversations into the Anaktoron |
| `/mnemion:status` | Show Anaktoron overview -- wings, rooms, drawer counts |

## Hooks

Mnemion registers two hooks that run automatically:

- **Stop** -- Saves conversation context every 15 messages.
- **PreCompact** -- Preserves important memories before context compaction.

Set the `MNEMION_DIR` environment variable to a directory path to automatically run `mnemion mine` on that directory during each save trigger.

## MCP Server

The plugin automatically configures a local MCP server with 25 tools for storing, searching, and managing memories. No manual MCP setup is required -- `/mnemion:init` handles everything.

## Full Documentation

See the main [README](../README.md) for complete documentation, architecture details, and advanced usage.
