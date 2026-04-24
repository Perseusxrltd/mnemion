# Mnemion Studio

A local web dashboard for Mnemion — visualise your Anaktoron, connect AI agents, and manage memories.

## Views

| View | Path | Description |
|------|------|-------------|
| **Dashboard** | `/dashboard` | Overview, trust health, recent drawers, quick capture, agent activity |
| **Graph** | `/graph` | Force-directed Wing Map + Knowledge Graph with Obsidian-style hover highlight |
| **Browser** | `/browse` | Wing → Room → Drawer tree with pagination |
| **Search** | `/search` | Hybrid semantic + keyword search, supports `wing:` / `room:` operators |
| **Agents** | `/agents` | Live heartbeat status of connected MCP agents |
| **Connect** | `/connect` | One-click install of Mnemion into every MCP-capable client on your system |
| **Settings** | `/settings` | LLM backend config, Anaktoron path, vault export |

## Quick start (Windows)

```bat
cd C:\path\to\mnemion
studio\start.bat
```

Then open **http://localhost:5173** — or whichever port Vite picked if 5173 was busy (the terminal prints it).

## Manual start

**Backend (FastAPI):**
```bash
uv sync --extra studio
uv run uvicorn studio.backend.main:app --host 127.0.0.1 --port 7891 --reload
```

**Frontend (Vite + React):**
```bash
cd studio/frontend
npm ci
npm run dev
```

## Connecting AI agents

The **Connect Agents** view (`/connect`, keyboard shortcut `G C`) detects installed MCP-capable clients and wires Mnemion into each one's config file with a single click. Every install writes a timestamped backup to `.mnemion_backups/` next to the edited config.

Supported out of the box:

| Vendor | Client | Config | Format |
|---|---|---|---|
| Anthropic | Claude Code (user) | `~/.claude.json` | JSON |
| Anthropic | Claude Code (project) | `./.mcp.json` | JSON |
| Anthropic | Claude Desktop | `%APPDATA%/Claude/claude_desktop_config.json` (Win)<br>`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) | JSON |
| OpenAI | Codex CLI | `~/.codex/config.toml` | TOML |
| Google | Gemini CLI | `~/.gemini/settings.json` | JSON |
| Cursor | Cursor | `~/.cursor/mcp.json` | JSON |
| Codeium | Windsurf | `~/.codeium/windsurf/mcp_config.json` | JSON |
| Zed Industries | Zed | `~/.config/zed/settings.json` | JSON |

Legacy `mempalace` entries (from the v3.4.x rename) are detected and auto-replaced. The command installed into each config uses the absolute path of the Python interpreter that Studio itself is running in, so there are no PATH-resolution issues.

Any client that speaks MCP but isn't in the list (OpenClaw, Nemoclaw, Hermes, Cline, custom agents…) can connect using the universal JSON snippet shown at the bottom of the Connect view:

```json
{
  "mcpServers": {
    "mnemion": {
      "command": "<absolute path to your Python>",
      "args": ["-m", "mnemion.mcp_server"]
    }
  }
}
```

## Architecture

```
studio/
├── backend/
│   ├── main.py         FastAPI — imports mnemion.* directly
│   └── connectors.py   Registry + safe JSON/TOML install/uninstall
├── electron/           Desktop packaging (probes Vite port at 5173–5179)
└── frontend/
    └── src/
        ├── views/        Lazy-loaded Dashboard, GraphView, Browser, Search, DrawerDetail,
        │                 Agents, ConnectorsView, Settings
        ├── components/   Layout, Ribbon, LeftSidebar, StatusBar, ErrorBoundary,
        │                 CommandPalette, ShortcutModal, DrawerCreateModal,
        │                 ToastProvider, WingBadge, TrustBadge
        └── api/          Typed client for all backend endpoints
```

**Backend port:** 7891  
**Frontend port:** 5173 by default — Vite auto-bumps to 5174/5175/… if busy. CORS allows only the expected local dev surface: `localhost`/`127.0.0.1` ports 5173-5179 and 7891, plus `file://`/`null` for Electron.

## Local API security

Read-only `GET` endpoints stay open for the local dashboard. If `MNEMION_STUDIO_TOKEN` is set, every mutating `/api` request (`POST`, `PUT`, `PATCH`, `DELETE`) must include:

```http
X-Mnemion-Studio-Token: <token>
```

Packaged Electron generates or inherits this token, passes it to the backend process as `MNEMION_STUDIO_TOKEN`, and exposes it to the frontend through the preload bridge. Browser-only development can leave the env var unset, or set it and provide the same header from local tooling.

## Build checks

```bash
cd studio/frontend
npm ci
npm run build
npm audit --audit-level=high

cd ../electron
npm ci
npm run build
npm audit --audit-level=high
```

## Agent heartbeats

Each MCP server process writes `~/.mnemion/heartbeats/<pid>.json` on every tool call.
Studio reads these to show live connection status in the **Agents** view. Set `MNEMION_AGENT_ID=your-agent-name` in the MCP server environment to display a friendly name.

## Keyboard shortcuts

| Keys | Action |
|------|--------|
| `Ctrl+K` | Command palette |
| `?` | Show all shortcuts |
| `C` | New drawer |
| `G D` / `G G` / `G B` / `G S` / `G A` / `G C` | Navigate to Dashboard / Graph / Browse / Search / Agents / Connect |
| `Esc` | Close any open modal |

## API surface

All endpoints under `/api`; typed client in `frontend/src/api/client.ts`. Mutating endpoints require `X-Mnemion-Studio-Token` when `MNEMION_STUDIO_TOKEN` is configured.

- **Drawers:** `/status`, `/taxonomy`, `/drawers`, `/drawers/recent`, `/drawer/{id}` (GET/DELETE/POST)
- **Search:** `/search?q=...&wing=...&room=...&limit=...`
- **Knowledge Graph:** `/kg/graph`, `/kg/entity/{name}`, `/kg/entities`
- **Trust:** `/trust/stats`, `/trust/contested`, `/trust/{id}/verify`, `/trust/{id}/challenge`
- **Agents:** `/agents`
- **Connectors:** `/connectors`, `/connectors/{id}`, `/connectors/{id}/install`, `/connectors/{id}/uninstall`
- **Config:** `/config` (GET), `/config/llm` (PUT)
- **Export:** `/export/vault?wing=...` — streams an Obsidian-compatible ZIP

OpenAPI docs at **http://127.0.0.1:7891/api/docs**.
