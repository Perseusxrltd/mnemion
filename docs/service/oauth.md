# Hosted OAuth foundation

**Requires service 4.0.11 or later and migration 013.**
This optional resource-server path lets an operator connect an existing or
freely self-hosted authorization server to Mnemion. It retains scoped API keys.
It does not complete the required simple personal/team sign-in, invitations,
app onboarding or account-recovery experience. Those remain in
[A01–A08](../PRODUCT_REQUIREMENTS.md).

Mnemion exposes protected-resource discovery, challenges and authenticated MCP
tools. The chosen authorization server must provide the actual user login,
PKCE S256 authorization-code flow, consent, refresh/revocation, authorization
server discovery, and the client registration methods required by the target
agent. For OpenAI, consult the current [official authentication contract](https://developers.openai.com/plugins/build/auth)
for CIMD/DCR and supported client authentication. Mnemion does not advertise
an authorization/token/registration endpoint it does not implement.

## Operator configuration

Use a stable HTTPS address under the operator's control. Enable the following
only in the service environment, after applying this release's normal database
migrations. Tenant administrators cannot configure outbound URLs through memory
tools or HTTP requests.

```dotenv
MNEMION_PUBLIC_URL=https://memory.example.com
MNEMION_OAUTH_ISSUER=https://identity.example.com/realms/company
MNEMION_OAUTH_INTROSPECTION_URL=https://identity.example.com/realms/company/protocol/openid-connect/token/introspect
MNEMION_OAUTH_CLIENT_ID=mnemion-resource-server
MNEMION_OAUTH_CLIENT_SECRET_FILE=/run/secrets/mnemion-introspection
MNEMION_OAUTH_TENANT_ID=00000000-0000-4000-8000-000000000001
```

The URLs are illustrative, not a verified provider configuration. Store the
introspection client secret in a file readable only by the service operator.
Mnemion reads at most 4 KiB and accepts a secret up to 2,048 characters. Do not
put secrets in URLs, command arguments, repository files or public evidence.
The introspection client must be authorized to inspect tokens for this resource;
it is distinct from the agent's client registration. Authentication uses
`client_secret_basic`. TLS verification is required; redirects and environment
HTTP proxies are disabled. No account, subscription or paid identity service is
required by this software, but operators must deploy or select an actual
authorization server before this mode can work.

Set `MNEMION_OAUTH_TENANT_ID` to the workspace's actual UUID from bootstrap or
`GET /v1/me`. This first single-issuer configuration admits OAuth to exactly one
operator-approved workspace. Administrators in other tenants cannot claim the
configured issuer's users or pre-bind their identities. Authentication rechecks
the configured workspace even for a binding created under an earlier policy.
API keys for other tenants keep their existing behavior. Additional workspaces
need separate service deployments in this slice; managed multi-workspace issuer
admission and account selection remain part of the full onboarding work.

With all OAuth settings absent, the existing API-key behavior remains. Partial
OAuth configuration fails at startup. The issuer and introspection URL are fixed
by the operator; token claims, browser headers, request bodies and discovery
documents cannot redirect verification to another service.

## Discovery and token contract

Both public discovery paths return the same configured resource metadata:

- `/.well-known/oauth-protected-resource/mcp`
- `/.well-known/oauth-protected-resource`

The canonical resource is the public origin followed by `/mcp`. Initial MCP
requests and subsequent unauthenticated requests receive a 401 with a
`WWW-Authenticate` challenge pointing to the first path. Every tool advertises
OAuth and the `mnemion:access` scope. Tool-level authentication failures also
carry `_meta["mcp/www_authenticate"]`. Metadata uses the operator's fixed address,
never an incoming Host/Forwarded header.

The authorization server's RFC 7662 introspection response must include:

| Field | Required value |
| --- | --- |
| `active` | JSON boolean `true` |
| `iss` | Exact configured issuer, including its path/trailing slash |
| `aud` | Exact canonical `/mcp` URL, or a string array containing it |
| `sub` | Immutable subject, nonempty, at most 255 characters |
| `client_id` | Agent's client registration identifier, nonempty, at most 2,048 characters |
| `exp` | Finite numeric expiry in the future |
| `scope` | Space-delimited string containing `mnemion:access` |

If present, `resource` must also equal the canonical resource, `nbf` and `iat`
must not be in the future, and `token_type` must be Bearer. Email, names,
organization IDs and external roles never select a Mnemion tenant or grant
permissions. Providers whose default introspection omits these fields require
configuration; omitting validation is not a compatibility solution.

Verification runs on every authenticated HTTP request and again for the backing
API call of an MCP tool. There is no positive token cache. Introspection has a
four-second total deadline, sixteen concurrent requests per process, a 32 KiB
uncompressed response cap, bounded tokens and duplicate-JSON-field rejection.
Unavailable or malformed issuer responses fail closed with 503. Invalid or
unlinked credentials get 401; a missing access scope gets a discoverable 403.
Tokens use only the Authorization header at the public boundary and a POST body
at introspection. The `mnm_` prefix is reserved for local API keys, which are
never sent to the issuer.

`mnemion:access` is one coarse resource-access scope. It does not grant a space
role, administrative privileges or host controls. The same token can call the
backing `/v1` API under exactly the same Mnemion principal and permissions.

## Approve and revoke connections

An organization administrator first creates/selects a Mnemion principal and
explicitly assigns only its permitted spaces through the existing
[people and grants APIs](organizations.md). New principals have no content
access. Use separate application principals when two agents need different
permissions; connections bound to the same principal share that principal's
current space grants.

After verifying the authorization server's stable subject and the agent's
registered client ID, the administrator calls `POST /v1/oauth/bindings`:

```json
{
  "principal_id": "00000000-0000-4000-8000-000000000001",
  "name": "Employee's approved agent connection",
  "subject": "immutable-subject-from-the-configured-issuer",
  "client_id": "registered-agent-client-id"
}
```

The response contains `id`, `principal_id` and `key_id`; no bearer secret is
returned. Each binding owns a dedicated hidden API-key record, so existing
transaction-level key revocation, principal disablement and expiry checks also
protect OAuth requests. The external token expiry is rechecked in each
request-derived database transaction. Grant changes take effect through the
existing row-level policies. Accepted evaluation and librarian jobs retain their
existing job authorization contract: access-token expiry does not cancel them.
They continue to use the persisted credential anchor and current principal/space
permissions; revoke the connection or cancel the job to stop further authorized
work. Ordinary indexing uses the separate service-worker contract after a memory
write is accepted; connection revocation preserves already committed writes and
their indexing work.

The `(issuer, subject, client_id)` tuple is permanently pinned to one principal
within this Mnemion database. It cannot be reassigned to another person or
tenant. Distinct subjects or client registrations can identify separate
connections within the admitted workspace. OAuth for another workspace requires
a separate service deployment in this slice; a workspace/account chooser remains
to be built. Binding a person by email or automatically granting their external
role would violate this boundary.

`GET /v1/oauth/bindings` lists a person's own connections; organization
administrators can list their organization's connections. `DELETE
/v1/oauth/bindings/{binding_id}` lets a person revoke their own connection or an
administrator revoke a connection in their organization. Other connections and
ordinary API keys are unaffected. The same revocation is available through
`DELETE /v1/keys/{key_id}` for administrators. Revoking a binding is permanent in
this slice; reauthorization of the same pinned tuple is a remaining workflow.
The agent operations are `oauth.bindings`, `oauth.bind` and `oauth.revoke`, exposed
through the existing CLI and MCP operation catalog.

Keep a separately held administrator API key and an operator management channel
outside agent sessions. Issuer outages do not invalidate ordinary API keys.
Host restart, tunnel repair and disaster recovery remain operator actions, not
permissions conferred by an OAuth scope. Existing recovery rotates all key
anchors and therefore disables restored OAuth connections as well; a restored
backup cannot silently revive their access. Guided reauthorization after recovery
remains to be completed.

## Acceptance still required

Local protocol fixtures and real PostgreSQL/RLS tests cover discovery, token
validation, authorized MCP reads/writes, denied operations, isolation,
revocation, expiry and failure privacy. They do not prove live compatibility
with any authorization server or assistant.

For each supported target, record a real authorization-code/PKCE connection,
consent, tool listing, permitted/denied calls, token refresh, removal/revocation,
reconnection and independent recovery. Dot uses supported account plugins as
described in [its official computers and apps documentation](https://learn.chatgpt.com/docs/dots/computers-and-apps).
Dot, ChatGPT, Claude, Grok Bot, Hermes and OpenClaw each need their own packaging,
configuration and live acceptance; none is marked complete by this foundation.

MCP access lets an agent use permitted memory tools. Automatic conversation
capture additionally needs an approved provider API, export/event feed or local
hook, checkpoints, exclusions and retention handling. It remains a separate
acceptance track, alongside built-in personal/company login, invitations,
resumable app onboarding, consent management and recovery.
