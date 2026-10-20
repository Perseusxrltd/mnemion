# Connect an agent with your personal or company account

Requires service and Studio **4.3.0**, with migration **016**. Check
[published release status](../RELEASE_STATUS.md) before requiring this version.
This optional authorization server requires no paid identity service. Personal
accounts work from 4.3.0. **Company accounts require service and Studio 4.10.0,
migration 019, and a configured [company sign-in provider](company-sign-in.md).**
Organizations with an existing authorization server can also use
[external issuer mode](oauth.md).

## Connect and approve

1. Get the workspace's public HTTPS MCP address from its administrator, such as
   `https://memory.example.com/mcp`.
2. Add that address in an agent supporting MCP OAuth, dynamic client registration
   and S256 PKCE. Choose its OAuth connection flow.
3. On the Mnemion page, check the requesting app and return address. App names
   are self-declared. Sign in with your personal workspace login, or select
   **Continue with your company account** when your workspace offers it.
4. Review your identity, organization authority and memory-space permissions.
   Select **Allow connection** to return to the app, or **Cancel** to refuse.

Company sign-in opens the provider in a separate window. Complete its normal
authentication, then return to Mnemion to review the permissions. You must already
have an approved company identity in that workspace; accept your invitation in
Studio first or ask an administrator to link your existing account. The consent
page cannot enroll a new person from an email address or provider role.

The agent receives revocable access, never your password or company provider's
tokens. It uses MCP and the
`/v1` API with your account's current permissions, including future changes.
Organization administrator authority includes changing grants; it does not
itself bypass memory-space grants. Use a separate account with limited grants
when an agent should have less authority than your main account. A separate
per-connection space allowlist is not implemented in this release.

Need a login or a password reset? Ask an administrator for a
[personal invitation or reset](sign-in.md). Connection requests expire after
ten minutes; a company-provider handoff expires after five minutes. After expiry
or a reload, start again from the agent. Signing in alone does not grant access;
approval is explicit. Company consent leaves remembered Studio connections and
their protected cookies intact.

From service/Studio 4.3.0, **Agents & apps** checks these connection options and
provides the configured MCP address directly. **Check availability** refreshes
the result after a host configuration change. The page distinguishes personal
account sign-in, an external company issuer and an unavailable or disabled gateway.

## ChatGPT custom MCP connection

The [current OpenAI guide](https://developers.openai.com/plugins/deploy/connect-chatgpt),
checked on 20 October 2026, uses **ChatGPT Plugins**. Your OpenAI account and
workspace policies must allow adding a custom MCP server.

1. In Mnemion, open **Agents & apps**, check account sign-in availability and
   copy **Workspace MCP address**. It must be the public HTTPS address including
   `/mcp`, with hosted OAuth enabled by the workspace's operator.
2. In **ChatGPT Plugins**, select **+ → Add custom MCP server**. Enter a name and
   description, then choose the public-endpoint connection and paste that address.
3. Configure **OAuth**. If asked for a registration method, choose dynamic
   client registration (DCR). Mnemion's built-in server registers public clients
   automatically; it does not require a manually supplied client secret.
4. Review ChatGPT's connection notice and select **Create as a plugin**. On
   Mnemion's consent page, sign in with your workspace account and review the
   displayed permissions before approving. A dedicated account with narrower
   grants is appropriate when the agent needs less authority than your account.
5. Confirm that ChatGPT discovers the Mnemion tools. Install the resulting plugin,
   start a new conversation and select it with `@`. Ask it to list accessible
   spaces and fetch a known permitted memory; an inaccessible space must remain
   inaccessible.

After tool metadata changes, open this custom connection in ChatGPT Plugins and
select **Refresh**, then start a new conversation. Mnemion's application updates
do not control an external client's cached tool list. MCP supplies tools for the
selected workspace; [conversation capture](capture.md) is configured separately.

The [OpenAI authentication contract](https://developers.openai.com/plugins/build/auth)
supports DCR with public-client token exchange. Mnemion advertises S256 PKCE,
an exact resource and issuer, and issuer-bearing authorization responses.
It does not advertise CIMD. For an external identity provider, copy the exact
callback displayed by ChatGPT and configure that provider's supported client
method; do not assume every deployment uses the same callback URL.

OpenAI also documents **Secure MCP Tunnel** for private-server testing. Its
workspace association and tunnel client are operated through OpenAI; Mnemion's
workspace permissions and host availability still apply.

The [live public protocol exercise](../validation/2026-10-20-live-hosted-signin.md)
passed. Actual signed-in ChatGPT acceptance remains tracked in
[issue 18](https://github.com/Perseusxrltd/mnemion/issues/18); these instructions
are based on the current official contract, not a claim that its UI was tested.

## Inspect and revoke

Open **Account & sessions → Connected apps** to inspect creation, last renewal,
expiry and revocation. People see their own connections; administrators can
inspect and revoke connections in their organization. The list is bounded to
the latest 1,000 connections. Labels and last renewal are not hardware
attestations or a record of every memory request.

**Revoke app** immediately invalidates its access and refresh credentials.
Reconnecting requires a fresh approval. Password changes/resets invalidate
password-backed connections. Revoking a Mnemion company identity link invalidates
its company-backed connections. Principal disablement and database recovery
invalidate the relevant sessions of either kind.
Other independently authorized connections retain their own authority. Already
committed memory writes and their ordinary indexing remain durable.

The same permission checks protect these agent controls:

- `GET /v1/oauth/connections` — catalog operation `oauth.connections`.
- `POST /v1/oauth/connections/{session_id}/revoke` — `oauth.disconnect`.
- TypeScript: `oauthConnections()` and `revokeOAuthConnection(sessionId)`.

From 4.3.0, `GET /v1/oauth/configuration` (catalog `oauth.configuration`,
TypeScript `oauthConfiguration()`) reports `mode`, `mcp_enabled`, `resource` and
`issuer` for the authenticated workspace. A different tenant receives no
selected workspace's issuer or resource. This read requires authentication and
does not enable OAuth, alter grants or fetch an external provider's metadata.

## Enable on a host

For a desktop-hosted workspace from **4.4.0**, use **Setup & this device → Remote
access** and enable **Allow hosted agents to request account sign-in and consent
(OAuth)**. The [guided setup](remote-access.md) supplies the public HTTPS origin,
selects that local workspace and restarts its engine. The bundled browser assets
serve the login and consent flow. Live acceptance in each named provider still
requires separate validation.

For an independently managed service, use the persistent host configuration below.

Apply the release's migrations through the normal guarded
[deployment](deployment.md) or [managed upgrade](managed-upgrades.md). Configure
the API process's persistent environment:

```dotenv
MNEMION_PUBLIC_URL=https://memory.example.com
MNEMION_OAUTH_BUILTIN=1
MNEMION_OAUTH_TENANT_ID=00000000-0000-4000-8000-000000000001
```

Use the actual workspace UUID from bootstrap or `GET /v1/me`. HTTPS must
terminate at the configured stable origin. Incoming Host/Forwarded headers
cannot select an issuer or workspace. OAuth admits one operator-selected
workspace per deployment in this release; existing API keys retain their own
tenant permissions.

Compose passes these settings to its API container. For a managed Unix setup,
put the two `MNEMION_OAUTH_*` settings in the private JSON supplied to
`supervise prepare --environment` or `updates setup --environment`, and supply
the same `--public-url`. Existing hosts need their operator to update the
persisted environment and restart the API. An interactive shell's variables
alone do not reconfigure an existing supervisor. To offer company accounts,
configure the same operator-approved OIDC providers used by Studio. Only providers
for the selected OAuth workspace appear on its consent page. No separate
assistant callback is needed at that company provider: it returns to Mnemion's
existing `/company/callback`; Mnemion then returns to the assistant's registered
callback after approval. Guided remote-host adoption and provider configuration
in Studio remain separate work.

Do not combine this mode with external issuer, introspection or client-secret
settings. Incomplete or conflicting configuration prevents API startup.
`MNEMION_OAUTH_BUILTIN=0` disables local OAuth issuance and authentication.
Historical connections remain inspectable and revocable through an independent
authorized credential. Keep recovery and host access independent of agents.

## Protocol and limits

Discovery uses `/.well-known/oauth-authorization-server` and
`/.well-known/oauth-protected-resource/mcp`. The resource is the public origin
plus `/mcp`; the issuer is the origin plus `/`. Registration, authorization,
token and revocation endpoints are under `/oauth`. Authorization redirects
include `iss` and preserve client state. Public clients use
`token_endpoint_auth_method=none` and S256 exclusively. Callbacks match exactly,
including ports: HTTPS and HTTP loopback callbacks are allowed, while
credentials, fragments and wildcards are rejected.

Request `mnemion:access` and the canonical resource. Code exchange must repeat
the resource. Refresh may omit it; a supplied resource must match. Access lasts
up to 15 minutes. A password-backed connection lasts at most 30 days. A
company-backed connection lasts **8 hours by default**, or the host's configured
company lifetime of **15 minutes to 24 hours**, measured from company
authentication. The permission review shows its absolute expiry. Refreshing does
not extend it; the user signs in and approves again when it expires. Both kinds
share the account's 32-session limit and allow at most 4,096 refresh rotations. Code and refresh
replay revoke the affected connection. Random credentials are stored as
digests; current account and space authority is rechecked on use.

Consent requires the host's own origin, a Secure/HttpOnly browser cookie and
a request-bound CSRF proof. Passwords and pending proofs stay in page memory,
never browser storage. Company handoffs are also bound to that specific request
and browser; they cannot issue a Studio device session. Current company links,
host-approved provider policy and permissions are rechecked before approval,
code exchange and credential use. Permission changes before approval or code
exchange require a fresh review. Protocol
bodies are capped at 32 KiB, callbacks at ten per client, active requests at
2,048, and registered clients at 10,000. Transport and password-hashing limits
bound work; throttled clients must respect `Retry-After`. A capacity limit fails
explicitly rather than silently evicting active authorization.

## Provider acceptance

The [4.10 validation](../validation/2026-10-15-company-agent-consent.md) includes
actual Dex authentication in Chromium followed by the MCP Python SDK's discovery,
registration, PKCE exchange, tool discovery/search, refresh and revocation. It
also covers existing password connections across migration and restored-access
revocation. These are generic protocol and local-provider checks.

The [20 October public-HTTPS record](../validation/2026-10-20-live-hosted-signin.md)
also verifies real discovery, reader consent, MCP access, refresh and immediate
revocation on an independently supervised host. It caught disabled persistent
OAuth settings, preserved existing agent keys and verified a fresh encrypted
off-host backup. An enabled gateway still needs individual accounts; that
exercise does not replace signed-in ChatGPT acceptance.

The generic flow follows the current
[OpenAI authentication contract](https://developers.openai.com/plugins/build/auth).
It does not establish live acceptance in ChatGPT, Dot, Claude, Grok Bot, Hermes
or OpenClaw; each still needs provider-specific setup and validation. CIMD,
private-key client authentication, automatic company provisioning, a company-only
sign-in policy and a multi-workspace login chooser are not implemented by this
mode. Company-provider logout or upstream account removal does not instantly
revoke a local connection; revoke its Mnemion link or person for immediate local
enforcement. Automatic conversation capture
remains a [separate source integration](capture.md).
