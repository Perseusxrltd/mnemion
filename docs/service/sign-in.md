# Individual sign-in and invitations

Requires the **4.2.0 service and Studio**. See [current release status](../RELEASE_STATUS.md)
for published versions and validation. Each person can use their own login,
password and revocable device sessions. Existing scoped application keys remain
available for agents and independently held administrator recovery.

Version **4.9.0** also supports [company accounts](company-sign-in.md), including
first-login invitation acceptance and revocable company device sessions. A host
operator configures the identity provider; Mnemion administrators still assign
every person's workspace authority.

## Invite someone to your organization

1. In **People & apps**, create a **Person** and give them the required space
   roles. Choose organization administrator authority only when they need it;
   that authority does not automatically grant memory access.
2. Open **Account & sessions**, choose that person under **Invite a person or
   reset their login**, and select **First login**. Choose an expiry of one hour,
   one day or seven days, then select **Create private invitation**.
3. Review the person, organization role and spaces. Share the invitation privately
   with that person. A code also needs the workspace's base address. A configured
   public HTTPS address lets the service generate a browser invitation link.
4. The recipient chooses **Join a workspace → Use invitation**, pastes the link
   or code and selects **Review invitation**. They review their identity and
   access, choose a login and password, name this device and open the workspace.

With an enabled company provider on 4.9.0, a first-login recipient can instead
choose **Join with my company account**. Company sign-in does not require
creating a Mnemion password.

Only the recipient chooses their password. An invitation works once before its
expiry. A replacement invitation, a relevant permission change, a disabled
person or a revoked issuer invalidates it. The server rechecks authority at
acceptance. An invitation receipt stays visible until acknowledged and blocks
an automatic app restart while its private information still needs saving.

Login names use 3–128 ASCII letters, digits, dots, dashes, underscores, `+` or
`@`; matching ignores case. Passwords preserve case, spaces and Unicode. Choose
a unique password or passphrase of 15–128 characters. Common, predictable and
login-derived choices are rejected. An email-shaped login is only a name: it
does not verify ownership of an email address.

## Sign in and remember a device

Use the organization's sign-in link or **Join a workspace → Sign in**. Paste
the **Workspace sign-in link**, then enter your login, password and a recognizable
device name. The link identifies the workspace without requiring you to type
its UUID. A saved connection remembers that verified identity. Never use a
display name as proof of identity.

**Remember this login on this device** is optional. On desktop, rotating credentials
are encrypted using the Windows account, macOS Keychain or a supported Linux
keyring. An unavailable or locked store requires unlocking it or using a
session-only login. The renderer receives a restricted handle; it does not
receive the refresh credential. The app waits for its own local host to be ready
and checks its workspace identity before refreshing a remembered login.

Browser remembering requires the workspace's own configured HTTPS origin.
Refresh uses Secure, HttpOnly, same-site cookies with origin and CSRF checks.
Browser local storage contains connection metadata, never passwords or access
and refresh tokens. HTTP loopback and non-remembered browser logins keep their
credentials only in memory. Reloading those pages requires signing in again.

Access credentials last 15 minutes and refresh automatically while a session
is used. A device session lasts at most 30 days and allows at most 4,096 refresh
rotations. Each person can have up to 32 active sessions. A device name is a
user-supplied label, not a hardware attestation. Multiple tabs coordinate a
remembered browser session; signing it out closes its access in the other tabs.

Expired session metadata and invitation permission snapshots become eligible
for removal 30 days after expiry. The API host cleans them in bounded batches
each minute, including when the person never logs in again. Spent refresh
digests are removed after their session expires or is revoked. Cleanup resumes
after an offline period; a large backlog may take several batches. Stable audit
and job identities remain in the database under the workspace's audit policy.

If a refresh response is lost, Mnemion asks for a new login. It does not replay
the old one-use refresh token. Restarting or selecting another connection cannot
silently replace the verified person with the local owner's account.
If another request rotates access during an ordinary read, the client can retry
once after confirming that the credential changed. Unchanged or revoked
credentials and password/refresh submissions do not enter an automatic retry loop.
When the desktop observes rejection of the current password session, it removes
that saved login, clears the workspace view and returns to sign-in. The workspace
link remains available. A late rejection from an older credential cannot close
a successfully rotated login or cancel a newer connection.

## Manage your access

**Account & sessions** shows the login configuration and device sessions. People
can inspect and revoke their own sessions; organization administrators can
inspect and revoke sessions in that organization. Revoking the current session
returns the app to sign-in. **Sign out** ends that password session and removes
its saved credential from this device. Other independent sessions and keys have
their own revocation controls.

From service/Studio 4.3.0, **Connected apps** lists applications approved through
the optional [hosted-agent sign-in flow](hosted-agent-sign-in.md). People can
revoke their own app connections; administrators can manage their organization's
connections. These are separate from the device list, but share the account's
session limits and password-reset/recovery protection. Revocation stops that
application's access and refresh credentials immediately.

An existing human key holder can set up their own password in this page.
Changing an existing password requires the current password. The change revokes
that person's password sessions and outstanding invitations. Sign in again with
the new password. Separately issued application and recovery keys retain their
own permissions and expiry.

For a forgotten password, an administrator selects **Reset existing login** and
creates a new private invitation. **Creating the reset immediately disables the
old password and its device sessions**, even before the recipient accepts it.
Cancelling or expiring a reset does not reactivate the old password. Issue a new
reset if necessary. Verify another administrator's independent access before
retiring the original administrator or agent.

The workspace must be running for sign-in and remote administration. An
administrator login cannot power on an unavailable host. Keep independent host
access and the [backup and recovery procedure](recovery.md). Restoration revokes
restored session and invitation material; it must not revive expired authority.

## Host setup and upgrades

The 4.2.0 service requires migration **015**. Back up and follow the
[deployment procedure](deployment.md) before upgrading a separately hosted
service. The managed updater refuses an incompatible automatic schema change;
updating Studio alone does not migrate another computer's server. Bundled local
workspaces use the desktop's guarded migration and recovery path.

Set `MNEMION_PUBLIC_URL` to the public HTTPS service address before offering
browser sign-in. Proxy headers alone cannot choose an authorized login origin.
Desktop native sign-in uses the service's authenticated HTTPS boundary; loopback
HTTP is supported for a local workspace. Rate and password-hashing concurrency
limits bound sign-in work; repeated attempts can return `429`.

This feature supplies Mnemion personal passwords and sessions. Optional
[hosted-agent OAuth consent](hosted-agent-sign-in.md) is available from 4.3.0.
Company identity-provider enrollment and live provider-specific acceptance
remain in the [complete requirements](../PRODUCT_REQUIREMENTS.md); an existing
company authorization server can use [external issuer mode](oauth.md).

## Agent and operator controls

The reviewed catalog has 13 `sign_in.*` operations, including account settings,
invitations, login, refresh and session revocation. Use
`mnemion-control describe OPERATION` for each input contract. Non-secret session
and invitation administration is also available through generic MCP operations.
Password, invitation-secret and refresh inputs, and operations issuing secrets,
use the CLI or native API instead of an agent conversation.

Sensitive CLI requests require an existing private `--input FILE`: owner-only
permissions on Unix, or an owner-controlled protected DACL on Windows. Links,
shared files and standard input are rejected for these operations. Generated
credentials require a new `--result-file FILE`, reserved privately before the
request. Never put passwords or tokens in command arguments, public documents
or transcripts. The [agent guide](agent-control.md) describes private results,
retry behavior and independent machine keys.

Session result files include `api_url` and the short-lived `api_key` alias and
can be used as `--credentials`. CLI calls do not silently refresh this file.
Use the explicit refresh contract, save its result to a new private file and
replace the old file only after a successful response. An uncertain refresh
outcome requires a new login; refresh and invitation acceptance are never
automatically retried.
