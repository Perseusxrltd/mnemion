# Connect an agent with your personal login

Requires service and Studio **4.3.0**, with migration **016**. Check
[published release status](../RELEASE_STATUS.md) before requiring this version.
This optional authorization server uses Mnemion's personal accounts and requires
no paid identity service. Organizations with an existing authorization server
can continue using [external issuer mode](oauth.md).

## Connect and approve

1. Get the workspace's public HTTPS MCP address from its administrator, such as
   `https://memory.example.com/mcp`.
2. Add that address in an agent supporting MCP OAuth, dynamic client registration
   and S256 PKCE. Choose its OAuth connection flow.
3. On the Mnemion page, check the requesting app and return address. App names
   are self-declared. Sign in with your personal workspace login.
4. Review your identity, organization authority and memory-space permissions.
   Select **Allow connection** to return to the app, or **Cancel** to refuse.

The agent receives revocable access, never your password. It uses MCP and the
`/v1` API with your account's current permissions, including future changes.
Organization administrator authority includes changing grants; it does not
itself bypass memory-space grants. Use a separate account with limited grants
when an agent should have less authority than your main account. A separate
per-connection space allowlist is not implemented in this release.

Need a login or a password reset? Ask an administrator for a
[personal invitation or reset](sign-in.md). Connection requests expire after
ten minutes. After expiry or a reload, start again from the agent. Signing in
alone does not grant access; approval is explicit.

## Inspect and revoke

Open **Account & sessions → Connected apps** to inspect creation, last renewal,
expiry and revocation. People see their own connections; administrators can
inspect and revoke connections in their organization. The list is bounded to
the latest 1,000 connections. Labels and last renewal are not hardware
attestations or a record of every memory request.

**Revoke app** immediately invalidates its access and refresh credentials.
Reconnecting requires a fresh approval. Password changes/resets, principal
disablement and database recovery also invalidate the relevant sessions.
Other independently authorized connections retain their own authority. Already
committed memory writes and their ordinary indexing remain durable.

The same permission checks protect these agent controls:

- `GET /v1/oauth/connections` — catalog operation `oauth.connections`.
- `POST /v1/oauth/connections/{session_id}/revoke` — `oauth.disconnect`.
- TypeScript: `oauthConnections()` and `revokeOAuthConnection(sessionId)`.

## Enable on a host

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
alone do not reconfigure an existing supervisor. Guided host/SSO configuration
in Studio remains separate work.

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
up to 15 minutes; a connection lasts at most 30 days, shares the account's
32-session limit and allows at most 4,096 refresh rotations. Code and refresh
replay revoke the affected connection. Random credentials are stored as
digests; current account and space authority is rechecked on use.

Consent requires the host's own origin, a Secure/HttpOnly browser cookie and
a request-bound CSRF proof. Passwords and pending proofs stay in page memory,
never browser storage. Changed permissions require a fresh review. Protocol
bodies are capped at 32 KiB, callbacks at ten per client, active requests at
2,048, and registered clients at 10,000. Transport and password-hashing limits
bound work; throttled clients must respect `Retry-After`. A capacity limit fails
explicitly rather than silently evicting active authorization.

## Provider acceptance

The generic flow follows the current
[OpenAI authentication contract](https://developers.openai.com/plugins/build/auth).
It does not establish live acceptance in ChatGPT, Dot, Claude, Grok Bot, Hermes
or OpenClaw; each still needs provider-specific setup and validation. CIMD,
private-key client authentication, company SSO onboarding and a multi-workspace
login chooser are not implemented by this mode. Automatic conversation capture
remains a [separate source integration](capture.md).
