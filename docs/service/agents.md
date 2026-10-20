# Connect assistants and applications

For full local/remote provisioning and repair, use the [native agent setup guide](agent-setup.md).

From **4.38**, download [Perseus XR connection packages](agent-packages.md)
directly from **Agents**, or generate them through the API, SDKs or native CLI.
Hermes and OpenClaw also join the local profile installer below.

Published **4.32.0** adds [guided installation in Studio](desktop-agents.md): select
the local client and its dedicated application, review the exact file change,
then install. Configuration backups and other client policies are preserved.
The private launcher connects while Studio is closed and follows its runtime
updates without rewriting agent settings. The manual commands below remain
available for browsers and separately managed installations.

From service/Studio **4.3.0**, open **Agents & apps** to check the workspace's
actual sign-in mode. When personal OAuth is enabled, copy its verified public
MCP address, add it to the agent's connector settings and choose OAuth. Sign in
on the workspace's page and approve the displayed permissions. Manage or revoke
the connection under **Account & sessions**. The
[personal-agent guide](hosted-agent-sign-in.md) explains permissions and host setup.
Its [ChatGPT connection steps](hosted-agent-sign-in.md#chatgpt-custom-mcp-connection)
follow OpenAI's current Plugins flow and public-client OAuth registration.

The page also identifies an external company issuer, a disabled MCP gateway,
an unconfigured workspace or a server too old to report this capability.
**Check availability** refreshes the observation. It never enables hosting or
grants permissions. Named-client acceptance still needs its own validation.

For a separately managed identity, expand **Connect with a dedicated application
key**. Give each application its
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
From 4.30.2, both the backup and staged replacement are created with explicit
private ownership/permissions before receiving configuration bytes, including
Windows ACL protection. Agent configuration can contain other providers' secrets.
If protection or replacement fails, the original configuration is retained;
any completed backup remains available. Existing unrelated files are never used
as temporary storage. See the [validation record](../validation/2026-10-20-agent-setup-private-files.md)
and [published release status](../RELEASE_STATUS.md) for availability.
A changed file invalidates an outstanding in-process preview. Invalid or
duplicate-key settings are rejected. Hermes YAML preserves comments; OpenClaw
JSON5 is saved as ordinary JSON with its exact original backed up. Other JSON
profiles require manual merging when they contain comments.

| `--client` | Configuration |
| --- | --- |
| `codex` | `$CODEX_HOME/config.toml`, or `~/.codex/config.toml`; `mcp_servers` |
| `grok-build` | `~/.grok/config.toml`; `mcp_servers`; separate from hosted Grokbot/plugin setup |
| `hermes` | `$HERMES_HOME/config.yaml`, or `~/.hermes/config.yaml`; YAML `mcp_servers` |
| `openclaw` | `$OPENCLAW_CONFIG_PATH`, or `$OPENCLAW_STATE_DIR/openclaw.json`; otherwise the selected `OPENCLAW_HOME`/`OPENCLAW_PROFILE` default; JSON/JSON5 `mcp.servers` |
| `claude-code` | `~/.claude.json`; `mcpServers` |
| `claude-desktop` | macOS Application Support or Windows `%APPDATA%/Claude`; `mcpServers` |
| `cursor` | `~/.cursor/mcp.json`; `mcpServers` |
| `gemini-cli` | `~/.gemini/settings.json`; `mcpServers` |
| `zed` | `$XDG_CONFIG_HOME/zed/settings.json`, default `~/.config/zed/settings.json`, or Windows `%APPDATA%/Zed/settings.json`; `context_servers` |
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
`memory_forget`. From 4.1.6, search/context/map default to all currently
accessible spaces when `space_ids` is omitted. A query-only `memory_search`
therefore includes connected sources with current access. Provide IDs to narrow
the search, or `space_ids: []` with `all_accessible: true` for explicit global
retrieval. An explicit empty list without that flag remains an error; an
inaccessible selected space never causes a broader fallback. Saving always
selects a writable space. Map results
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

### Compact discovery and session compatibility

Version 4.2.3 adds `search` and `fetch` aliases alongside existing tools. For a
client with a small tool-discovery budget, set `MNEMION_MCP_TOOL_PROFILE=compact`
in the gateway's environment and restart it. Discovery advertises only `search`,
`fetch`, `mnemion` and `memory_profile`, with validation bounds retained and full
operation schemas fetched on demand. The default is `full` for existing clients.
The profile changes discovery, not permissions or which operations are authorized.

Call `mnemion` with `action: "list"` (the default) to browse operations; pass the
returned `next_offset` as `offset` to continue, or `query` to filter the catalog.
Use `action: "describe", operation: "..."` for its schema, then explicit
`action: "read"` or `"write"` with that operation's `request` shape. Read mode
rejects writes. Credentials, private inputs and downloads retain the CLI/private
file requirement. Mutation annotations remain conservative; discovery does not
grant blanket permission to perform the listed operations.

HTTP remains stateless by default. Clients that require `Mcp-Session-Id` can use
`MNEMION_MCP_SESSIONS=1` on the server and restart the gateway. Initialization
then creates a native SDK session; subsequent requests send its header together
with the current bearer credential. Sessions are bound to the exact creating
credential, capped at 128 per gateway process and expire after 15 idle minutes.
Rotation, expiry or server restart requires reinitialization. A different device
key cannot reuse the session, even for the same principal. Every request still
checks credential validity and every operation checks current grants.

Session storage is process-local; deployments with several workers need session
affinity. Stateless clients need neither this mode nor sticky routing. Optional
sessions do not provide hosting, tunnel recovery or offline access. Proxy setups
must preserve the session header. The two settings are independent and work with
the same `/mcp` endpoint; existing host/origin and request-size limits remain.

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
The [connected-source guide](connectors.md#connected-sources-and-writable-memory)
explains the Git/source split, identity mappings and unified search workflow.

The gateway bounds request size, authentication time and concurrent calls. Busy
HTTP requests include `Retry-After`; SDKs respect bounded retry delays for safe
reads and idempotent writes. See [inference admission](embeddings.md#inference-admission).
`serve --no-mcp` or `MNEMION_MCP_ENABLED=0` disables the combined endpoint. A
standalone gateway on port 7893 remains available for existing deployments.

### Migrating a separate MCP listener

The combined listener has been available since 4.0.2. It does not start the
separate port 7893 listener. If an old startup command launched that standalone
gateway and a replacement startup command launches only `serve`, existing
clients can still point at a port where no process is listening.

| Deployment | MCP URL | What to run or change |
| --- | --- | --- |
| Combined API and MCP | `http://127.0.0.1:7892/mcp` | Run `mnemion-service serve`; point local clients and the proxy at port 7892. |
| Keep existing standalone clients | `http://127.0.0.1:7893/mcp` | Also run `mnemion-service mcp --transport streamable-http --port 7893`, with `MNEMION_API_URL` pointing at the API origin. Retain it in the host's process manager. |
| Public HTTPS origin | `https://memory.example.com/mcp` | Forward the chosen local listener, set its matching `--public-url`, and update the client's saved origin when it changes. |

Mnemion does not silently bind the old port or install a cross-origin redirect.
Keeping the standalone command preserves callers that cannot yet change their
URL. Every HTTP caller still supplies its own `Authorization: Bearer …` header;
an endpoint move does not revoke or replace its key. A refused connection means
the listener or forwarding path needs attention. HTTP 401 instead means the
presented credential was not accepted.

Custom Streamable HTTP clients should send `Content-Type: application/json`
and `Accept: application/json, text/event-stream`. Use cleartext HTTP for the
loopback listener and HTTPS for the TLS proxy; sending TLS directly to a
cleartext port produces an HTTP parsing error. This migration guidance also
applies to managed-host startup changes; see
[issue 23](https://github.com/Perseusxrltd/mnemion/issues/23).

Service 4.0.11 adds [optional trusted-issuer OAuth validation](oauth.md) with
individual, revocable identity bindings. Service 4.3.0 adds
[personal-account agent sign-in](hosted-agent-sign-in.md), including public-client
registration, PKCE, consent, refresh and revocation. Actual ChatGPT acceptance
remains in issue 18; Dot and other named-provider/plugin acceptance remain in
the product roadmap. General delegated-authentication issue 4 is resolved. From 4.0.8,
[managed Unix server patches](managed-updates.md) are available to authorized
host operators; a memory key alone cannot grant software-update authority.

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
