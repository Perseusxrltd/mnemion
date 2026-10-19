# OpenAI hosted MCP access review

Reviewed 19 October 2026 against current official documentation. This is a
provider compatibility study, not a claim of successful account enrollment or
a completed ChatGPT tool call.

## Authentication

[OpenAI's current authentication guide](https://developers.openai.com/apps-sdk/build/auth)
requires protected-resource discovery, authorization-server discovery, S256
PKCE and resource binding. It supports dynamic registration, client metadata
documents or predefined clients. Mnemion's published built-in server uses
dynamic registration with public clients, exact callbacks, issuer identification,
personal/company sign-in and current space authorization.

OpenAI documents a stable callback when RFC 9207 issuer identification is
supported and a callback-specific URL otherwise. Mnemion already advertises
issuer response support and returns its exact configured issuer. There is no
need to invent an OpenAI-specific bearer-header connector or assume that dynamic
registration is obsolete. Mnemion does not currently advertise CIMD support.

Issues [18](https://github.com/Perseusxrltd/mnemion/issues/18) and
[4](https://github.com/Perseusxrltd/mnemion/issues/4) retain their real-client
acceptance: create the connection in a supported, authorized ChatGPT workspace,
complete registration and consent, list tools, then check a scoped tool call
and revocation. Internal protocol tests alone do not establish those outcomes.

## Private transport

The [Secure MCP Tunnel guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
documents outbound HTTPS polling from a customer-operated tunnel client to an
OpenAI-managed endpoint. It supports HTTP or stdio MCP targets and supported
ChatGPT, Codex and API surfaces. This offers an additional provider-specific
route for a private MCP server.

Its prerequisites include a Platform tunnel identity, runtime API key,
organization-level tunnel permissions, the intended ChatGPT workspace
association and permission to add/use a custom MCP server. The private client
must keep running. An offline host remains unavailable.

OAuth discovery can travel through that tunnel, but **the authorization server
is not automatically tunneled**. Mnemion's browser sign-in/consent still needs
the appropriate reachable origin. This tunnel also does not by itself expose
the complete Mnemion web app, restore a lost host, or serve every other agent
vendor.

The documented default limits include 600 requests/minute, a 10 MiB serialized
envelope and a 120-second request deadline. These are not capacity guarantees.
This review did not establish pricing or account eligibility, create a key,
start a trial or make a paid model call. Any integration must retain the user's
zero-spend requirement and validate the intended account first.

## Product work

Keep the published [app-managed ngrok and existing proxy paths](../service/remote-access.md).
Add Secure MCP Tunnel as an optional OpenAI transport only after verified
account setup, private credential custody, supervised lifecycle and an actual
hosted tool call. It does not replace provider-neutral hosting or independent
recovery. Provider branding alone does not establish a client's MCP support.
