# Perseus XR agent plugins and connection packages

From **4.39.0**, **Agents → Connect with your account** can download a package
for the selected workspace. Choose the agent, download the ZIP and follow its
`README.md`. The package uses the workspace's configured HTTPS MCP address;
sign-in and permission review take place in the receiving agent.

All packages identify **Perseus XR** as author and carry the canonical Mnemion
logo. They include no password, API key, OAuth token, private client secret or
personal app identifier. Exporting does not create an account, grant access,
install another agent or enable conversation capture.

## Choose the appropriate package

| Agent | Contents and installation |
| --- | --- |
| OpenAI / Codex | Portable `plugin.json` and `mcp.json`, with Perseus XR author and OpenAI developer metadata. Use the client's supported plugin distribution/import flow. ChatGPT also accepts the [custom MCP/OAuth flow](hosted-agent-sign-in.md#chatgpt-custom-mcp-connection). Dot uses its enabled account's supported plugin surface; its separate live acceptance remains open. |
| Claude Code | `.claude-plugin/plugin.json` declares the authenticated HTTP MCP server. Extract into a new folder and load it through Claude's plugin manager or `claude --plugin-dir FOLDER`. Claude Desktop/web use their own supported connector setup. |
| Grok Build | A Claude-compatible plugin with native Grok metadata support. Extract it and run `grok plugin install FOLDER`; use `/mcps` for authentication and `grok mcp doctor mnemion --json` for diagnostics. This is separate from Grok Bot cloud. |
| Hermes | A YAML `mcp_servers.mnemion` definition with browser OAuth. Merge that entry into the intended profile, run `hermes mcp login mnemion`, then `/reload-mcp`. This is native configuration; inclusion in the Nous catalog needs its own approval. |
| OpenClaw | A nested `mcp.servers.mnemion` definition with explicit Streamable HTTP and OAuth. Merge it into the intended configuration or use `openclaw mcp set` with that server object; then `openclaw mcp login mnemion` and `openclaw mcp probe mnemion`. This is native configuration, not an OpenClaw SDK extension. |
| Grok Bot | A connection card and [cloud setup guide](grok-bot.md). The official route supports an uncatalogued MCP server by URL or a command on the Bot's cloud computer. The package is **not an importable marketplace plugin**; actual authentication, native tools and persistence remain tracked by [issue 44](https://github.com/Perseusxrltd/mnemion/issues/44). |

Every ZIP also contains a machine-readable `connection.json`, its version,
provider, package kind and authentication method. This card describes the
connection; it is not a universal vendor import format. Generated ZIP paths are
fixed, output is bounded and the app verifies the download checksum.

The current Claude compatibility manifest omits the newer directory-only `icon`
field because actual Claude Code **2.1.59** rejects it. The canonical image is
included in the package and rendered README. Actual Grok **1.0.62** and Claude
**2.1.59** manifest validation passed; this does not establish OAuth/tool calls
inside every target provider. Provider directory publication and account-owned
listing attribution remain separate from package metadata. In particular,
[actual ChatGPT testing](../validation/2026-10-20-chatgpt-acceptance.md) found that
its private wrapper retained the creating account's display name.

## Native agent operations

The app, authenticated API and standalone CLI use the same generator. Discover
`agents.package` in the [agent catalog](agent-control.md), or call:

```http
POST /v1/oauth/agent-package
Authorization: Bearer YOUR_EXISTING_WORKSPACE_CREDENTIAL
Content-Type: application/json

{"provider":"hermes"}
```

The response includes `filename`, `media_type`, `content_base64`, `sha256`,
`author`, `kind`, `version` and `contains_credentials: false`. It has `no-store`
cache policy. It requires a current workspace identity and uses only that
tenant's configured public MCP address. Disabled sign-in/MCP or another tenant's
settings cannot produce a package. It is classified as a read operation and
issues no credentials. Python `Client.agent_package(provider)` and TypeScript
`MnemionClient.agentPackage(provider)` expose the same API.

Without a running app or server, a trusted local agent can generate a package
from the intended, non-secret HTTPS MCP address:

```sh
mnemion-service agent-package --catalog
mnemion-service agent-package --provider claude \
  --mcp-url https://memory.example.com/mcp --output ./mnemion-claude.zip
```

The installed standalone engine accepts the same `agent-package` command.
CLI output is a JSON receipt; an existing output file is never overwritten.
The CLI checks the URL format but does not claim the host is reachable or OAuth
enabled. Do not include credentials in the address. Packages are specific to the
chosen host; export again if the host address changes.

## Accounts, teams and availability

Use `memory_profile` after authentication to verify the principal and workspace.
Consent grants the signed-in account's actual current and future permissions.
Use a separate account when an assistant needs narrower authority.

OpenClaw's exported OAuth configuration uses the gateway operator's shared
connection. It does not identify each employee. Per-requester OAuth requires its
separate gateway configuration and has a documented shared-channel sign-in-link
limitation; review that provider contract before enabling it for a company.
Grok Bot shares files, browser sessions, command credentials and apps across the
Bots on one account. Its [setup guide](grok-bot.md#shared-custody-and-continuity)
distinguishes connected-app OAuth custody from credentials on the cloud computer.

Cloud assistants must reach the workspace's host over HTTPS. A stable public
host does not need ngrok; an offline host remains offline regardless of the
package. Keep the [independent host/recovery route](host-recovery.md) available.
Model quota exhaustion must be reported separately from endpoint health.

For local agents using dedicated application keys, the [Studio installer](desktop-agents.md)
also supports Hermes YAML and OpenClaw JSON5. It preserves other connections,
honors selected profile paths and uses the private managed launcher. Configure
[conversation capture](capture.md) separately.
