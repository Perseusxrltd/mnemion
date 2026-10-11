# Agent platforms and durable workspace access

Researched **2026-10-11** from the official documentation below. These are
provider capabilities, not claims that a Mnemion-branded plugin has already
shipped or passed a provider's approval process. Track implementation in the
[requirements checklist](../PRODUCT_REQUIREMENTS.md).

## Findings that change the product

| Platform | Documented connection and hosting behavior | Mnemion implementation consequence |
| --- | --- | --- |
| OpenAI Dot | Its own cloud computer/browser; enabled account plugins; a separately approved personal-computer connection. Local computer access requires that computer online with the app open. | Build the supported hosted plugin/OAuth path. Keep local Codex MCP configuration distinct from Dot's cloud plugin configuration. |
| OpenAI ChatGPT/Codex | Hosted plugin authorization uses MCP OAuth; local Codex supports stdio, Streamable HTTP bearer tokens and OAuth. The OAuth contract covers resource metadata, PKCE, client registration/metadata and token validation. | Implement OAuth discovery and consent as well as existing scoped API keys. Test the actual target product; a successful shell request is insufficient. |
| Grok Bot | A persistent cloud computer is shared by a user's Bots. Files and browser sessions are shared; separate screens are not separate security boundaries. Agent Computer offers takeover; recovery/update controls exist outside a Bot conversation. | Give each connection scoped credentials, keep durable data outside temporary directories, and maintain an operator path independent of model usage. A credential file on that shared computer may be available to the user's other Bots. |
| Hermes | Local and remote MCP, browser OAuth, configurable headers, private setup values, per-server tool selection and connection/cooldown recovery. Configuration uses `mcp_servers` in its profile. | Supply and verify a Hermes-specific setup path, secure token handling and tool refresh/reconnection. Catalog inclusion requires upstream review. |
| OpenClaw | Stdio and HTTP transports, explicit `streamable-http`, bearer headers and OAuth; per-requester OAuth is distinct from shared operator credentials. Its docs explicitly describe a shared-channel sign-in-link limitation. | Support per-person consent and connection identity. Do not use a shared channel or shared agent credential as proof of a particular employee's identity. |
| Anthropic/Claude | Existing Mnemion setup supports Claude Code/Desktop, and capture normalizes Claude exports. Hosted connectors and native packaging need their own current contract review and live acceptance. | Retain working local integrations; track hosted OAuth/plugin/capture work separately instead of claiming all Claude surfaces work identically. |

Connecting a memory tool lets an agent call permitted operations. It does not
automatically grant access to that provider's complete conversation history.
Automatic capture requires a supported provider API, export, event or local
hook, explicit source approval, checkpoints, exclusions and deletion/retention
handling. The product must show what was captured and what is unavailable.

## Availability and company access

A live diagnostic returned ngrok `ERR_NGROK_3200` for the API and MCP endpoint.
This establishes an offline tunnel, not invalid Mnemion credentials or a
retrieval failure. The workspace host could not be reached to determine its
current service version. Private addresses and credentials are omitted here.

The required design is a company-controlled workspace address and sign-in,
independently supervised service and network connection, individually revocable
people/agent access, and an administrator recovery path. A web entry page can
help with joining and status; it cannot restart an unreachable host without a
separately authorized management channel. Keep the operator plane distinct from
ordinary memory permissions and model availability.

Provide both personal and organization deployment paths. Existing company
infrastructure, a suitable always-on computer/NAS, or a user-selected host can
run Mnemion. The software must not require a paid memory subscription. Hosting,
networking and identity-provider services retain their own availability and
terms; do not promise an always-on free third-party host.

## Sources

- [Dot: computers and apps](https://learn.chatgpt.com/docs/dots/computers-and-apps)
- [Dot: controls and workspace administration](https://learn.chatgpt.com/docs/dots/controls)
- [Dot: getting started](https://learn.chatgpt.com/docs/dots/getting-started)
- [OpenAI MCP configuration and supported features](https://learn.chatgpt.com/docs/extend/mcp)
- [OpenAI plugin authentication](https://developers.openai.com/plugins/build/auth)
- [Grok Bot: computer and apps](https://docs.x.ai/grok-bot/computer-and-apps)
- [Grok Bot: troubleshooting and recovery](https://docs.x.ai/grok-bot/troubleshooting)
- [Grok Bot: private networks](https://docs.x.ai/grok-bot/private-networks)
- [Hermes MCP integration](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp)
- [OpenClaw transport and OAuth contract](https://github.com/openclaw/openclaw/blob/main/docs/cli/mcp/transports.md)

Pages were fetched and read on the date above. No paid account, trial, provider
registration or live-memory import was created during this research.
