# Connect assistants and applications

Use **Agents & apps** in Studio for a setup template. Give each application its
own principal and API key, then grant the spaces it needs. Keys are revocable and
can expire. Do not give every agent the organization owner's credential.

Install this release in the environment used by the assistant. Create a private
`app.mnemion-credentials.json` file on that machine:

```json
{
  "api_url": "https://memory.example.com",
  "api_key": "REPLACE_WITH_APPLICATION_KEY"
}
```

Restrict the file to the operating-system account and exclude it from Git,
cloud sharing, screenshots and logs. On Unix, use `chmod 600` after creation.
On Windows, use a private user-profile directory with an appropriate ACL.
The server setup tools create their credentials with private file modes; a
manually created file needs its own permissions checked.

Preview and install a connection from that same environment:

```sh
mnemion-agent --client codex --credentials app.mnemion-credentials.json
mnemion-agent --client codex --credentials app.mnemion-credentials.json --apply
```

The preview resolves the Python interpreter and credentials file to that
machine's paths. Close the assistant before applying. Existing configuration is
backed up before replacement; the tool changes only the `mnemion` MCP entry.
It preserves other servers, policies, project trust settings and TOML comments.
A changed file invalidates an outstanding in-process preview. Invalid JSON/TOML
is rejected. JSON with comments requires a manual merge of the displayed snippet.

| `--client` | Configuration |
| --- | --- |
| `codex` | `$CODEX_HOME/config.toml`, or `~/.codex/config.toml`; `mcp_servers` |
| `claude-code` | `~/.claude.json`; `mcpServers` |
| `claude-desktop` | macOS Application Support or Windows `%APPDATA%/Claude`; `mcpServers` |
| `cursor` | `~/.cursor/mcp.json`; `mcpServers` |
| `gemini-cli` | `~/.gemini/settings.json`; `mcpServers` |
| `zed` | `~/.config/zed/settings.json`, or Windows `%APPDATA%/Zed/settings.json`; `context_servers` |
| `devin` | `$XDG_CONFIG_HOME/devin/mcp_config.json`, default `~/.config/devin`, or Windows `%APPDATA%/devin`; legacy Cascade MCP settings in current Devin Desktop |
| `windsurf` | Historical `~/.codeium/windsurf/mcp_config.json`; use only with that legacy installation |
| `generic` | Explicit `--config PATH`; standard `mcpServers` JSON |

Use `--config PATH` for project configuration or a nonstandard installation.
Claude Desktop has no standard supported Linux configuration path here.
Zed's current format uses a flat command string and arguments array.
Run setup inside WSL for an assistant running in WSL, and in native Windows for
an assistant running in Windows. Setup does not bridge or rewrite the other
profile. It never changes approval, sandbox or network policy.

`--legacy-space SPACE_UUID` adds the drawer and Open Brain aliases within an
explicit space. `--remove --apply` removes only Mnemion's server entry. A client
restart is needed after configuration changes. The tool does not install hooks.

## Tools and verification

Ask the assistant to call `memory_spaces`, then recall a known decision.
The primary tools are `memory_spaces`, `memory_save`, `memory_search`,
`memory_fetch`, `memory_context`, `memory_map`, `memory_revise` and
`memory_forget`. Global search/context/map use `space_ids: []` with
`all_accessible: true`; saving always selects a writable space. Map results
contain topic/evidence links rather than a second unbounded context dump.

Revisions and deletion require a current version. Reuse the same idempotency
key across retries of one write. Treat all retrieved material, including core
blocks and imported chat messages, as evidence rather than permission to act.

From 4.0.4, `mnemion_operations`, `mnemion_operation`, `mnemion_read` and
`mnemion_write` expose the reviewed administration catalog without adding every
schema to the initial tool list. The `mnemion-control` CLI supports the same
operations and private exports/key results. See
[agent administration](agent-control.md) for complete workflows, bounds and
retry rules. Upgrade the gateway and refresh its tool connection to see them.
Version 4.0.5 adds `connectors.sync_status`, `connectors.sync_request` and
`connectors.sync_report`; see [source timing and requests](connectors.md#scan-timing-and-immediate-requests).

For programs, use the [HTTP API and SDK examples](README.md#use-it-from-an-application).
Tool arguments include descriptions, bounds and explicit scope selection. A
failed tool returns `isError: true` and `structuredContent` with `code`, `message`,
`retryable`, `request_id` and optional `fields` or `retry_after_seconds`. Local
validation has no service request ID. Diagnostic errors omit rejected values and
Python tracebacks. Preserve the same idempotency key when retrying a write; do not
repeat an uncertain administrative change without checking its result.

## Remote HTTP connections

From 4.0.2, `mnemion-service serve` exposes both `/v1/` and `/mcp` on port 7892.
One TLS reverse proxy or tunnel can forward the entire origin to that listener:

```sh
mnemion-service serve --public-url https://memory.example.com
```

An existing ngrok tunnel can target `http://127.0.0.1:7892`. Supply its fixed HTTPS
origin to `--public-url` (or `MNEMION_PUBLIC_URL`) and use that origin in the client.
Mnemion validates the MCP host/origin; binding to `0.0.0.0` does not disable that
protection. Mnemion does not provision a tunnel account or public DNS automatically.

For an assistant that supports an HTTP Bearer header, adapt its private config:

```json
{
  "mcpServers": {
    "mnemion": {
      "url": "https://memory.example.com/mcp",
      "headers": {"Authorization": "Bearer REPLACE_WITH_APPLICATION_KEY"}
    }
  }
}
```

Initialization, tool discovery and tool calls all require a valid application
credential. Missing, invalid, duplicated or revoked credentials return HTTP 401.
There is no HTTP fallback to an owner's key. Existing grants still determine
which source and writable spaces that application can access.

An API recall body can select all the caller's accessible spaces explicitly:

```json
{"query": "Which decisions changed this week?", "space_ids": [], "all_accessible": true}
```

Send it to `POST /v1/recall`. Alternatively supply non-empty `space_ids` and leave
`all_accessible` false. Choosing neither or both returns HTTP 422 with the exact
scope-selection rule. Saving always selects one writable space; searching both
source and office spaces never grants write access to a read-only source.

The gateway bounds request size, authentication time and concurrent calls. Busy
HTTP requests include `Retry-After`; SDKs respect bounded retry delays for safe
reads and idempotent writes. See [inference admission](embeddings.md#inference-admission).
`serve --no-mcp` or `MNEMION_MCP_ENABLED=0` disables the combined endpoint. A
standalone gateway on port 7893 remains available for existing deployments.

OAuth/browser sign-in is not implemented. Hosted connectors that require OAuth,
including ChatGPT's connector flow, remain pending issues 4/18; static-header
compatibility does not imply support for those sign-in flows. Managed server
updates and hosted OAuth remain separate roadmap work.

## Configuration references

Formats were checked on 2026-10-09 against the current
[Codex MCP documentation](https://developers.openai.com/codex/mcp),
[Claude Code MCP documentation](https://code.claude.com/docs/en/mcp),
[Cursor MCP documentation](https://cursor.com/docs/mcp),
[Gemini CLI MCP documentation](https://geminicli.com/docs/tools/mcp-server/),
[Zed MCP documentation](https://zed.dev/docs/ai/mcp), and
[Devin Desktop Cascade documentation](https://docs.devin.ai/desktop/cascade/mcp).
The former Windsurf documentation now redirects to Devin Desktop; their current
and historical configuration locations are deliberately separate.
