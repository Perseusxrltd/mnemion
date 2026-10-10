# Mnemion Studio

Mnemion Studio is the local desktop UI for Mnemion. It is designed to feel like a normal app: a live memory dashboard, guided AI-app connections, visual browsing/search, and a Windows installer that bundles the Python memory service.

## Desktop App

The packaged Windows app includes:

- `Mnemion Studio.exe`, the Electron desktop shell.
- `resources/backend/backend.exe`, the PyInstaller memory service.
- Built frontend assets under `resources/frontend/dist`.
- A system tray icon and tray menu.
- A per-install API token passed from Electron to the local memory service.
- App data rooted under Electron's user-data folder, not a random shell working directory.

The window can be closed without quitting. Closing hides Mnemion Studio to the tray; use the tray menu or app menu to show it again.

## Main Views

| View | Path | Description |
| --- | --- | --- |
| Live Memory | `/dashboard` | Health, recent activity, first-run guidance, and quick capture. |
| Graph | `/graph` | Visual memory relationships and topic clusters. |
| Browse Memories | `/browse` | Memory areas, topics, and saved entries. |
| Search | `/search` | Keyword and semantic memory search. |
| Agents | `/agents` | Live AI-app connections and recent activity. |
| Connect AI Apps | `/connect` | Guided setup for supported AI tools. |
| Core Memory | `/corememory` | Live working memory blocks shared with connected AI apps. |
| Settings | `/settings` | Local store, optional AI helper, markdown backup, and app health. |

## Quick Start For Development

```bat
cd C:\path\to\mnemion
studio\start.bat
```

The dev script starts the backend service and Vite frontend. Vite normally serves the UI at `http://127.0.0.1:5173`; if that port is busy, use the port printed by Vite.

## Manual Development Start

Backend:

```bash
uv sync --extra studio
uv run uvicorn studio.backend.main:app --host 127.0.0.1 --port 7891 --reload
```

Frontend:

```bash
cd studio/frontend
npm ci
npm run dev
```

Electron shell:

```bash
cd studio/electron
npm ci
npm run build
npm run dev
```

In dev mode, Electron probes `127.0.0.1:5173` through `5179` and only accepts a Vite server.

## Connecting AI Apps

The Connect AI Apps view detects supported tools and can install Mnemion into each tool's local config with one click. Every install writes a timestamped backup beside the edited config.

Supported out of the box:

| Vendor | Client | Config | Format |
| --- | --- | --- | --- |
| Anthropic | Claude Code, user | `~/.claude.json` | JSON |
| Anthropic | Claude Code, project | `./.mcp.json` | JSON |
| Anthropic | Claude Desktop | `%APPDATA%/Claude/claude_desktop_config.json` on Windows | JSON |
| OpenAI | Codex CLI | `~/.codex/config.toml` | TOML |
| Google | Gemini CLI | `~/.gemini/settings.json` | JSON |
| Cursor | Cursor | `~/.cursor/mcp.json` | JSON |
| Codeium | Windsurf | `~/.codeium/windsurf/mcp_config.json` | JSON |
| Zed Industries | Zed | `~/.config/zed/settings.json` | JSON |

Old `mempalace` entries are detected and replaced. The installed command uses the absolute Python executable path that Studio is running with, which avoids PATH-resolution issues.

Advanced tools that accept a local command can use the JSON snippet shown in the Connect view.

## Local API Security

When `MNEMION_STUDIO_TOKEN` is set, every non-OPTIONS `/api/*` request must include:

```http
X-Mnemion-Studio-Token: <token>
```

Packaged Electron generates or inherits the token, passes it to `backend.exe`, and exposes it to the renderer through the preload bridge. Browser-only development can leave the token unset.

Public exceptions are limited to OpenAPI documentation paths:

- `/api/docs`
- `/api/openapi.json`
- `/api/redoc`

## Markdown Backup

Settings exposes the owned markdown backup flow:

- `Create, Refresh, and Open` writes the managed markdown vault, best-effort registers it with Obsidian, then opens it.
- `Refresh Only` updates the vault without opening Obsidian.
- `Download ZIP` streams the same markdown rendering as a ZIP.

Mnemion remains the source of truth. The markdown vault is a one-way projection.

## Build And Release Checks

From `studio/electron`:

```bash
npm run pack
npm run dist
```

`pack` rebuilds the frontend, memory service, and Electron shell, verifies
packaged resources, and refreshes `dist-electron/win-unpacked`.

`dist` performs the same resource build and then creates the NSIS installer.
If `dist-electron/win-unpacked` is already verified and current, use
`npm run dist:prepackaged` to rebuild only the installer.

Useful individual checks:

```bash
npm run verify:resources
npm run verify:installer
npm run smoke:packaged
npm run dist:prepackaged
```

`verify:resources` requires:

- `dist-backend/backend/backend.exe`
- `studio/frontend/dist/index.html`
- `studio/frontend/dist/icon.ico`
- `studio/frontend/dist/icon-tray.png`

`verify:installer` requires the installer and blockmap plus these payload files inside the NSIS archive:

- `Mnemion Studio.exe`
- `resources\backend\backend.exe`
- `resources\frontend\dist\index.html`
- `resources\frontend\dist\icon.ico`
- `resources\frontend\dist\icon-tray.png`

For public release validation, require Authenticode signing:

```bash
set MNEMION_REQUIRE_CODE_SIGNATURE=1
npm run verify:installer
```

That command must fail when the installer is unsigned.

## Manual Release Smoke

After installing or launching the unpacked app:

- The app icon appears in the system tray.
- Closing the window hides the app to the tray instead of quitting.
- Tray menu items show the app, open Settings, open Connect AI Apps, restart the memory service, and quit.
- Live Memory loads without console errors.
- Connect AI Apps can rescan installed tools.
- Settings shows App Health and the markdown backup controls.
- A memory can be saved, searched, opened, and exported.

Automated packaged smoke:

```bash
npm run smoke:packaged
```

The smoke launches `dist-electron/win-unpacked/Mnemion Studio.exe` with an
isolated profile, verifies the private backend port, checks the packaged tray
icon source, and confirms the memory service responds. In headless or remote
sessions Windows may report `shellTrayWarning: true`; that means the shell could
not visually place a status icon in that session, not that the packaged tray
asset is missing.

## Keyboard Shortcuts

| Keys | Action |
| --- | --- |
| `Ctrl+K` | Command palette |
| `?` | Show keyboard shortcuts |
| `C` | Save memory |
| `G D` | Go to Live Memory |
| `G G` | Go to Graph |
| `G B` | Go to Browse Memories |
| `G S` | Go to Search |
| `G A` | Go to Agents |
| `G C` | Go to Connect AI Apps |
| `Esc` | Close modal or go back |

## API Surface

All endpoints are under `/api`; the typed client is `frontend/src/api/client.ts`.

- Status and taxonomy: `/status`, `/taxonomy`
- Memories: `/drawers`, `/drawers/recent`, `/drawer/{id}`
- Search: `/search`
- Graph: `/kg/graph`, `/kg/entity/{name}`, `/kg/entities`
- Trust: `/trust/stats`, `/trust/contested`, `/trust/{id}/verify`, `/trust/{id}/challenge`
- Agents: `/agents`
- Connectors: `/connectors`, `/connectors/{id}`, `/connectors/{id}/install`, `/connectors/{id}/uninstall`
- Config: `/config`, `/config/llm`
- Markdown backup: `/obsidian/status`, `/obsidian/sync`, `/obsidian/open`, `/export/vault`
- Sources and wiki: `/sources/*`, `/wiki/*`

In development, OpenAPI docs are available at
`http://127.0.0.1:7891/api/docs`. In the packaged app, use Settings -> App
Health -> Advanced diagnostics because the memory service uses a private dynamic
port.
