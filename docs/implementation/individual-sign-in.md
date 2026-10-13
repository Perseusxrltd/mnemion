# Individual sign-in, invitations and hosted agents

Implementation contract updated **2026-10-13** for A01–A03, A07–A08, A11–A13
and C04–C07. The full flow below is not published. It builds on the existing
[authorization boundary](../service/organizations.md),
[OAuth resource server](../service/oauth.md) and
[workspace continuity contract](workspace-continuity.md).

## Joining and signing in

An administrator chooses a person and explicit compartment permissions, then
creates an expiring, one-use invitation. The app previews the server, workspace,
person and granted roles. A person chooses their own login and password; the
administrator never sees that password. A company can also use its own identity
provider. Neither path requires a paid Mnemion account or a central service.

The invitation identifies a single workspace and principal. Its random secret
belongs in a URL fragment or private delivery file, never in query parameters,
access logs, public documentation or an agent transcript. Invitation acceptance
atomically consumes the secret and rechecks expiry, issuer authority, target
identity and current grants. Replaying or concurrently accepting an invitation
must not create multiple accounts or duplicate authority.

Normal login links identify the workspace without including credentials. Saved
connections retain its verified UUID, so users do not need to type UUIDs or pick
between indistinguishable names. A new device can use that sign-in link or its
invitation. Avoid an unauthenticated directory of all organizations on the host.
Login input may locate an account; it must never set transaction authority.

Password storage uses a maintained password-hashing implementation with a
bounded memory-hard configuration. Preserve passphrases exactly. Cap input,
hashing concurrency and repeated attempts, including unknown accounts, without
exposing whether a username exists. Do not rely on proxy-supplied client IPs or
an unbounded in-memory attempt dictionary for protection.

Published 4.1.3 includes the [bounded Argon2id foundation](../validation/2026-10-12-password-foundation.md),
using the existing cryptography dependency. It is not connected to a public login
endpoint. Account persistence, invitations, attempt throttling, password-strength
screening, sessions and the app flow still need implementation and validation.

## Sessions and administration

Each device gets its own revocable session. Access credentials are short-lived;
refresh credentials rotate atomically, are stored only as digests on the server,
and have an absolute expiry. Reuse revokes the affected session family. The app
serializes refresh and explains a lost or expired session instead of silently
switching to a different saved identity.

Browser credentials must not enter local storage. Any cookie-based refresh path
needs Secure/HttpOnly cookies, origin and CSRF checks, and same-origin handling.
Desktop refresh credentials use the existing OS-protected vault and bounded IPC.
Remembering a workspace and remembering a login remain explicit device choices.

Current key, principal and space checks remain authoritative for every API
transaction and queued operation. A session uses a dedicated hidden credential
anchor, so logout, administrator revocation, disabling a person and disaster
recovery can stop its future access without altering unrelated API keys. Normal
token refresh must not cancel already authorized background jobs by accidentally
retiring their stable anchor. Revocation must still cancel further work under it.

People can inspect and revoke their own sessions; administrators can inspect and
revoke sessions within their organization. Show device names, creation, expiry
and last activity with bounded retention. Do not claim a device name proves
hardware identity. Self-service password changes require recent authentication.
Administrator-assisted reset uses a separate expiring invitation and revokes old
sessions. No recovery flow can revive a deleted identity or reuse its profile ID.

Keep final-administrator protection valid for password accounts, sessions,
ordinary keys and OAuth bindings together. A forgotten password or unavailable
issuer does not remove the separately held recovery credential and host-operator
channel. Database restoration must invalidate restored sessions, refresh tokens,
invitations and OAuth authorization codes before clients are admitted.

## Hosted-agent authorization

The next authorization-server implementation must provide discovery, S256 PKCE,
exact redirect validation, resource binding, explicit consent, one-use codes,
refresh rotation, revocation and durable client registration. Reuse maintained
protocol handlers; test their actual metadata and behavior. Offer a public-client
path without requiring a paid certificate or shared client secret. Existing
company identity providers remain an optional supported deployment path.

Consent names the requesting client, the selected workspace identity and its
actual permission scope. A person may not delegate authority they do not hold.
Separate application identities remain available when an agent needs narrower
or independently managed grants. The scope `mnemion:access` alone confers no
memory, organization-administrator or host-operator permission.

Support DCR and, when implemented and validated, CIMD. Metadata URL resolution
must have outbound-network, redirect, response-size and timeout controls;
untrusted client metadata must not become a credential destination. Advertise
only the methods and scopes that work. Return the exact issuer in authorization
responses when advertising RFC 9207, including error callbacks. Preserve the
canonical resource throughout authorization, code exchange and refresh.

The current [official OpenAI authentication guide](https://developers.openai.com/plugins/build/auth)
was fetched on 12 October. It documents CIMD/DCR/predefined clients, PKCE S256,
resource binding, issuer-identified callbacks, optional enterprise domain
restrictions and stable profile identification. Enterprise verified-email claims
require actual email verification and an appropriate UserInfo endpoint; never
infer them from a typed email or an invitation label. The profile declaration
does not enable OAuth or establish live provider compatibility.

## Published account identification

The `memory_profile` MCP tool, published in 4.1.3, uses the existing immutable principal
UUID as an opaque profile ID. Different credentials for that principal retain
the ID; distinct principals and organizations do not share it. Display-name
changes only change labels. The tool requires current authentication but no
memory grant, returns only `id`, `name` and `nickname`, and declares
`_meta["openai/profile"]: true` with a strict output schema. It adds no login,
consent or account-linking authority. The
[profile validation](../validation/2026-10-12-mcp-profile.md) and
[4.1.3 publication record](../validation/2026-10-12-managed-connectors.md)
record its completed source, native and delivery checks. The complete individual
sign-in flow above remains required.

## Acceptance before publication

1. Complete invitation, login, restart, refresh, password change, reset and
   revocation through the app and corresponding documented agent/operator APIs.
2. Exercise two organizations on one origin, a separate personal workspace,
   repeated display names, tenant substitution, revoked grants and concurrent
   acceptance/refresh. Cached or selected identities never authorize a request.
3. Test expiry, malformed inputs, login throttling, refresh reuse, CSRF, callback
   substitution, wrong resources, unavailable providers and interrupted writes.
   Return no passwords, tokens, private URLs or membership details in errors.
4. Restore a backup with the current recovery ledger, prove old credentials and
   invitations cannot revive access, and exercise independent human/operator
   recovery after removing the original agent.
5. Verify protected persistence and reopening on Windows, macOS and Linux, and
   browser login without plaintext credential persistence. Keep resource use
   bounded on modest hardware.
6. For each named hosted client, record real sign-in/consent, tool discovery,
   allowed and denied calls, refresh, disconnect, reconnect and revocation.
   Protocol fixtures, profile metadata and generic MCP support are not substitutes
   for live ChatGPT, Dot, Claude, Grokbot, Hermes or OpenClaw acceptance.
