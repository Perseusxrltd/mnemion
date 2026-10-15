# Company accounts and identity-provider setup

Requires the **4.9.0 service and Studio**. Check [release status](../RELEASE_STATUS.md)
for published downloads. Company sign-in connects an organization's existing
OpenID Connect provider to its people in Mnemion. It is optional and free;
Mnemion does not require a central account, subscription or paid identity service.
The company runs or chooses its provider and controls who can join.
The guided local-host setup below requires **4.11.0**; its source can precede
published installers. Separately operated servers retain the environment-file
configuration introduced in 4.9.0.

## Join with your company account

1. Open the workspace sign-in link supplied by your administrator, or choose
   **Company sign-in** in the desktop app and paste that link.
2. Select **Check workspace**. For a first-login invitation, review your name,
   organization role and memory spaces before continuing.
3. Choose the company account when more than one provider is available. Name
   this device and choose whether to remember the login.
4. Select **Continue with …**. Complete your company's sign-in and any required
   multi-factor authentication in the browser, then return to Mnemion.

An existing **First login** invitation also offers **Join with my company
account** after its access preview. Reset invitations reset a personal password;
they do not relink a company account. Ordinary sign-in links contain no key or
password. Invitations are private, single-use and invalidated by relevant access
changes. The host and identity provider must both be reachable.

Desktop sign-in opens the system browser and uses a temporary receiver on
`127.0.0.1`. It closes on completion, cancellation or timeout. Company passwords
stay with the identity provider. Mnemion session credentials remain in the main
process and, when remembered, the operating system's protected store. The browser
app uses a separate sign-in window and a same-origin channel; allow that window.
Remembered browser sessions use Secure/HttpOnly cookies, with origin and CSRF
checks. Local storage holds connection metadata, never access or refresh tokens.

## Give people the right access

In **People & apps**, create a **Person** and assign their spaces and roles.
In **Account & sessions**, issue a first-login invitation for that person and
share it privately. Accepting the invitation binds the authenticated company's
stable subject identifier to exactly that person. The service checks the
invitation and current permissions again before creating the session.

Alternatively, an administrator can use **Account & sessions → Company access →
Link an existing company identity**. Choose the person and configured provider,
and enter the exact immutable OpenID Connect `sub` claim from the provider.
Verify that identifier with the identity administrator before linking; an
administration console can use a different internal account identifier.
First-login invitations bind the authenticated subject automatically. Email addresses, domains,
display names and provider role claims never automatically grant Mnemion access.
An existing linked subject cannot be reassigned to another person.

People can inspect and revoke their own linked company accounts. Organization
administrators can inspect and revoke the organization's links. Revoking a link
ends its associated device sessions immediately. Disabling the person ends all
their Mnemion access. Revoking one device in **Device sessions** only ends that
session. Independent personal passwords and API keys remain separately managed.
Explicitly relinking an account invalidates its old sessions.

## Configure a provider on the host

The host operator owns this configuration. Workspace administrators cannot make
the service contact arbitrary identity endpoints through the memory API.

### A workspace hosted by the desktop app

On its host computer, open **Setup & this device → Company sign-in setup**.
The same controls are available on the local workspace's welcome screen.

1. Enable the workspace's HTTPS address in **Remote access**. Copy the callback
   address shown by Company sign-in setup.
2. In your existing company identity provider, register an OpenID Connect client
   with that exact callback address, authorization code, S256 PKCE and signed
   RS256 or ES256 ID tokens. Use `client_secret_basic` for a confidential client,
   or a public client without a secret. Provider registration requires your
   organization's identity-administration access.
3. Select **Add company provider**. Enter a button label and the exact issuer
   address, including any tenant or realm path. Select **Read provider settings**
   and review the sign-in, token-exchange and signing-key addresses. Discovery
   reads public metadata without a memory credential or client secret. Fixed
   endpoint entry is available under **Manual provider settings**.
4. Enter the client ID, its secret if required, and a maximum session length.
   For a private certificate authority, expand **Company certificate authority**
   and supply a trusted PEM bundle, up to 8 KiB, without private keys. This bundle
   replaces system trust for all company providers on this local host; certificate
   and hostname verification stay enabled.
5. Confirm that the callback was registered and the provider addresses reviewed.
   Select **Save company provider**. A running workspace stops cleanly, saves the
   settings and restarts. A stopped workspace retains them for its next start.
6. Use **Invite people & manage identity links** to grant actual people access.
   Complete a real company sign-in before inviting the rest of the organization.
   A successful metadata check is not a test of the client registration or MFA.

Names and the real service workspace are taken from the local host; the user does
not need to find or enter a UUID. Up to 32 providers fit within a 64 KiB private
configuration. Saved client secrets stay in the host's private operator files,
protected by OS ownership/ACLs. They are not returned to Studio or agent status,
and are not searchable memory. This storage is separate from the planned
encrypted general-purpose secrets vault.

Editing requires the current company and remote-access revisions. Concurrent
operator changes require refresh and review. A retained secret cannot be sent
to a changed issuer, endpoint or client: replace or explicitly remove it first.
Changing identity policy requires the link approval described below. Keep an
independent administrator login or key available during provider changes.

Removing a provider removes its secret from the active local configuration and
disables its company connections while absent. Revoke its identity links in
**Account & sessions** when retiring it permanently; re-adding the same policy
does not itself permanently revoke older links. Disabling Remote access retains
provider settings but suspends their local-host activation until HTTPS returns.
Damaged company settings disable company sign-in while other local access remains
available. An explicit **Reset company settings** preserves the damaged private
bytes before clearing the configuration. A restored workspace requires fresh
provider setup and identity approval.

Existing explicitly configured `local run` environment files remain supported.
The local setup controls identify these as host-managed and refuse a silent
replacement. Review and remove that environment setting before adopting local
setup. Ordinary desktop startup does not inherit arbitrary provider variables.
These controls apply to the app-owned host. Guided configuration of a separately
operated remote host remains on the roadmap.

### A separately operated server

1. Configure the service's public HTTPS origin using `--public-url` or
   `MNEMION_PUBLIC_URL`, as described in [deployment](deployment.md). Employees
   should use that origin's workspace sign-in link.
2. Register an OpenID Connect authorization-code client at your provider.
   Register exactly `https://memory.example.org/company/callback` as its redirect
   URI, replacing the origin. Enable S256 PKCE and signed RS256 or ES256 ID
   tokens. A public client uses PKCE without a secret; a confidential client uses
   `client_secret_basic` as well. No provider refresh token is requested or kept.
3. Copy the issuer, authorization endpoint, token endpoint and JWKS URI from
   the provider's trusted configuration/discovery document. Mnemion pins these
   endpoints and checks the token's issuer, audience, subject, signature, times
   and nonce. It does not follow token-supplied key URLs or HTTP redirects.
4. Create a private JSON configuration file. For example, a self-hosted Dex
   provider can use the following structure; substitute the actual workspace
   UUID and provider values:

```json
[
  {
    "workspace_id": "00000000-0000-4000-8000-000000000001",
    "id": "company",
    "name": "Company account",
    "issuer": "https://identity.example.org/dex",
    "authorization_url": "https://identity.example.org/dex/auth",
    "token_url": "https://identity.example.org/dex/token",
    "jwks_url": "https://identity.example.org/dex/keys",
    "client_id": "mnemion-company",
    "session_seconds": 28800
  }
]
```

Set `MNEMION_COMPANY_SIGN_IN_FILE` to that file's absolute path in the service
environment. For a confidential client add `client_secret_file`, pointing to a
separate private UTF-8 file containing its secret. In this server-managed format,
keep the secret in that private file; never put it in Git or memory. For a company certificate authority,
`MNEMION_COMPANY_CA_FILE` selects the operator's CA bundle; TLS verification
remains enabled. The file supports at most 32 distinct workspace/provider pairs
and 64 KiB; client-secret files are separately bounded.

For the [background supervisor](supervision.md), put these environment names
and file paths in the private JSON supplied with `supervise prepare --environment`.
Follow that guide's replacement-state procedure when changing an existing
configuration. A normal shell change does not alter a saved supervisor profile.
Other deployment methods should set the variables on the API process and restart
it through the existing host service manager. Provider URLs must use HTTPS and
must not contain credentials, query parameters or fragments.

Changes to the issuer, endpoints, client, session duration or public/confidential
mode invalidate the old company policy. Existing company sessions fail closed;
an administrator must explicitly approve the linked identity under the new
policy. Renaming the provider or rotating an existing confidential-client secret
does not reassign users. Keep a separately held administrator key and host
operator account available, as described in [independent administration](organizations.md).

## Session duration and current limits

Company sessions last **8 hours by default**, configurable from **15 minutes to
24 hours**. Short access credentials rotate within that absolute lifetime; then
the person signs in through the company provider again. Remembering a device
does not extend the lifetime. Refresh replay revokes the affected session family.
Restoring a workspace revokes restored company links and sessions before use.

This release does not implement SCIM provisioning, automatic group-to-space
mapping, mandatory company-only sign-in or provider back-channel logout. Removing
an upstream account does not instantly revoke an already issued Mnemion session.
Revoke its Mnemion link or disable its person for immediate local enforcement;
otherwise its next company authentication occurs after the configured lifetime.

From **4.10.0** and migration **019**, company accounts can also authorize
assistants through the built-in [hosted-agent consent page](hosted-agent-sign-in.md).
The host must enable that mode for the workspace. Existing linked users complete
company authentication, review their current permissions and explicitly approve
the requesting app. They do not need to create a Mnemion password. Assistant
connections share the configured company lifetime and local revocation policy;
the consent flow preserves their remembered Studio session. Live acceptance
across named hosted assistant products remains on the roadmap. Scoped agent keys
and the separately configured [trusted-issuer OAuth resource server](oauth.md)
remain available. Generic OIDC support does not establish compatibility with
every company's provider, MFA policy or restricted device; validate the actual
provider configuration before deploying it broadly.

## Agent and SDK controls

For an app-owned local host, the private desktop catalog adds
`local.company-discover` and `local.company` in 4.11.0. Both confirm the selected
local workspace and the current company/remote revisions. The latter saves,
removes or explicitly resets provider configuration through the same restart
controller as the screen. These are owning-OS-account operations, unavailable
to remote memory keys. [Desktop operator setup](desktop-operator.md) describes
the authenticated private pipe and agent discovery.

For example, submit discovery through that pipe using values from `status`:

```json
{
  "action": "local.company-discover",
  "expected_workspace_id": "LOCAL_WORKSPACE_UUID_FROM_STATUS",
  "input": {
    "workspace_id": "LOCAL_WORKSPACE_UUID_FROM_STATUS",
    "expected_revision": "COMPANY_REVISION_FROM_STATUS",
    "expected_remote_revision": "REMOTE_REVISION_FROM_STATUS",
    "issuer": "https://identity.example.org/dex"
  }
}
```

Save with `local.company`: `action: "save"`, the same revision fields and a
`provider` containing `id`, `name`, `issuer`, `authorization_url`, `token_url`,
`jwks_url`, `client_id` and `session_seconds`. Optional `client_secret` replaces
the secret; omission retains it. `clear_client_secret: true` explicitly removes
it. Omitted `ca_pem` retains trust; a PEM string replaces it, and explicit `null`
returns to system trust. `action: "remove"` takes a `provider_id` instead of a
provider. `action: "reset"` is accepted only for the currently observed damaged
record. The selected local-host UUID differs from the service's tenant UUID;
always copy the local identifier from desktop status for these operations.

Direct local operators can use `mnemion-service local company-discover --root
<data-folder>` and `local company --root <data-folder>` with the same inner JSON
on private stdin. The direct writer requires a stopped host; prefer the desktop
pipe when the app owns its lifecycle. Never put secrets in shell arguments.

The reviewed catalog adds seven operations: `company.configuration`,
`company.check_configuration`, `company.start`, `company.finish`, `company.links`,
`company.link` and `company.revoke`. Configuration only describes the supplied
workspace; it does not enumerate organizations. Link administration uses current
Mnemion authority. Python and TypeScript clients provide configuration, listing,
linking and revocation helpers.

`company.start` and `company.finish` require private CLI input and result files,
are excluded from generic MCP execution and never automatically retry an
uncertain one-use request. A native login caller must own the validated temporary
loopback callback and retain its PKCE verifier privately. The company account
holder completes provider authentication; a memory API key cannot bypass it.
The finish result can be used as a private `mnemion-control` credential file and
refreshed or revoked through the existing personal-session operations. See
[agent controls](agent-control.md) for file handling and operation discovery.

The schema migration is `018_company_sign_in.sql`. Separately hosted servers
need the [guarded operator upgrade](managed-upgrades.md); ordinary desktop
updates do not migrate a remote server. Existing password accounts and sessions
remain usable after that upgrade. Release validation distinguishes protocol,
browser and native checks from published installers and automatic updates.
