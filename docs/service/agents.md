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

For programs, use the [HTTP API and SDK examples](README.md#use-it-from-an-application).
An optional authenticated MCP HTTP gateway serves `/mcp`; each request uses its
own bearer credential. OAuth/browser sign-in is not implemented. A hosted
assistant that requires OAuth needs an organization-managed gateway providing
that identity integration; it is not certified merely because stdio works.

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
