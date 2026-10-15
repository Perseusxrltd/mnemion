# Share a locally hosted workspace

Desktop **4.4.0** adds remote access under **Setup & this device** and the local
workspace welcome screen. Check [published release status](../RELEASE_STATUS.md)
for available installers. The same workspace can serve the desktop, a browser,
teams and agents through its public HTTPS address.

The operating-system account that owns the local workspace controls this setup.
An organization administrator or memory API key alone does not grant access to
the host's files, provider credentials or lifecycle. Other users join with
[individual logins](sign-in.md) or independently scoped agent credentials.

## Set up in the app

1. Create or open a workspace **on this computer**. Open **Setup & this device →
   Remote access**. The screen names the local workspace being configured.
2. Choose **Managed ngrok connection** or **Existing HTTPS proxy or private
   network**. Supply the HTTPS origin, such as `https://memory.example.com`.
   Credentials, query strings, fragments and application paths are refused;
   an address ending in `/mcp` is normalized to its origin.
3. For ngrok, enter your account's authtoken and assigned domain. For an existing
   proxy, configure forwarding as described below.
4. Leave **Allow hosted agents to request account sign-in and consent (OAuth)**
   enabled to let compatible agents request an individual login and approval.
   This setting controls hosted-agent OAuth; people still need their own
   workspace account and memory permissions. From 4.10.0, company accounts are
   also offered when the host has an approved [identity provider](company-sign-in.md).
5. Select **Save & restart local host**. The app drains the previous engine,
   saves the settings and reopens the same workspace. A stopped workspace offers
   **Save settings**, then **Start local host**. Memories, grants, existing keys,
   the database and local resource settings are retained.
6. Wait for **Last check passed**, then copy **Workspace address** for people or
   **MCP server** for agents. Use **Account & sessions** for invitations and
   **Agents & apps** for scoped keys or personal-agent sign-in. Sign-in and
   invitation links use the configured public origin.

Saving briefly interrupts connected clients. The controls serialize with app
shutdown and updates. An explicit stop or close during the change prevents an
unwanted restart. If another operator changes the settings, the app preserves
unsaved edits and requires review of the saved version before another write.

## Managed ngrok connection

Use your own [ngrok account authtoken](https://dashboard.ngrok.com/get-started/your-authtoken)
and [assigned domain](https://dashboard.ngrok.com/domains). Mnemion includes the
reviewed official Python SDK **1.7.0**, opens its own connection and supervises
reconnection. No separate tunnel program is required. The saved domain must
belong to that account and be available; Mnemion does not take over a domain
already serving another computer. Endpoint pooling is disabled.

A free ngrok account can be used within the provider's current limits. At the
15 October 2026 review, the [free plan](https://ngrok.com/docs/pricing-limits/free-plan-limits)
includes **20,000 HTTP requests and 1 GB outbound traffic per month**. Routine
route checks consume about **2,880 requests per 30 days**; memory/API traffic,
browser assets and retries also consume the account's allowance. Mnemion does
not enroll a paid plan or automatically purchase more capacity. The provider
controls its quotas, domain policies and availability.

The provider token is kept in the host's private operator file, protected by
the OS account's filesystem permissions. It is **not encrypted by Mnemion's
desktop key store**. It is never returned in status, displayed after saving,
included in a copied link or sent as a memory credential. Protect the host
account and its backups. Leave the token field empty to retain the saved token;
enter a replacement to rotate it. Selecting Off or an existing proxy removes
the token from the active configuration. An explicit repair of damaged settings
retains a private recovery copy, which can contain the previous token.

## Existing HTTPS proxy or private network

Your operator supplies the proxy, stable address, TLS certificate and network
access. It must forward the **whole site** to the local API address displayed
in the app, including `/`, `/workspace`, `/assets`, `/v1`, `/mcp`, `/oauth` and
`/.well-known`. Preserve the public Host header. Forwarding `/mcp` alone cannot
serve the login, consent and invitation pages.

The engine continues listening on loopback. A proxy on another computer needs
an independently configured secure path to that loopback service. The provider
may terminate TLS and process traffic; choose one consistent with your team's
requirements. Private-network users must have access to that network, and both
the host and clients must trust its certificate. Route checks verify TLS and
do not follow redirects or disable certificate verification.

Selecting Off stops Mnemion's managed ngrok session and disables its configured
public OAuth issuer. **An independently operated proxy must also have its
forwarding removed by its operator.** Turning this setting off cannot stop a
separate program or revoke already issued memory keys.

## Check and recover a route

The status shows the last actual successful check, not a guarantee of continuous
availability. A successful check proves that the configured HTTPS route reaches
this running engine using a fresh bounded challenge. It sends no memory key,
password, cookie or workspace contents. This does not prove that a particular
external agent supports the connection or can reach a private network.

Normal checks run every 15 minutes. **Check now** queues a fresh check after a
network change; requests are coalesced and limited to once per 30 seconds.
**Refresh status** reads current local observations. Failures retry with bounded
backoff; a failing ngrok session is closed and recreated independently of the
local API. The app shows a sanitized provider error code when available.
Stale observations from a previous process or settings revision are ignored.

If remote access fails, local memory access remains available. Check the domain,
provider quota, certificate, forwarding and host network. A readable damaged
remote configuration can be repaired explicitly; the prior private bytes are
retained. Unsafe or unreadable storage is reported rather than overwritten.

Changing the public origin changes the OAuth issuer/resource. Reconnect agents
through the new address and review their old sessions. Background operation and
startup keep the host independent of an agent's model quota, but do not wake a
powered-off or provider-suspended computer. For independent recovery, retain
host operator access and a [verified backup](recovery.md). Guided fleet hosting,
replicas, failover and provider-specific agent acceptance remain on the
[roadmap](../PRODUCT_REQUIREMENTS.md).

## Equivalent local agent controls

The bundled `mnemion-engine` and `mnemion-service` expose the same typed commands.
Run them as the owning OS account with the workspace's actual data directory:

```sh
mnemion-service local status --root DATA_FOLDER
mnemion-service local remote --root DATA_FOLDER
```

Stop the host before the second command; it acquires the same exclusive local
workspace lock. It reads one JSON line from standard input, capped at 4096 bytes:

```json
{"workspace_id":"00000000-0000-4000-8000-000000000001","expected_revision":"not-configured","mode":"proxy","public_url":"https://memory.example.com","personal_sign_in":true,"ngrok_authtoken":null}
```

Replace `workspace_id` and `expected_revision` with `settings.workspace_id` and
`remote_access.revision` from fresh status. For ngrok use `mode: "ngrok"` and
provide the authtoken through this private stdin channel, never a command-line
argument or shared document. For Off use `mode: "disabled"` and `public_url: null`.
Unknown fields, stale revisions and a different workspace are refused. Inspect
status after an interrupted command before retrying; do not edit around the lock.

A running host also accepts a bounded, revision-bound check request:

```sh
mnemion-service local remote-check --root DATA_FOLDER
```

Its stdin contains only `workspace_id` and `expected_revision`. It queues the
same coalesced route check as the app without stopping the host. Inspect status
for the result. These operator commands do not grant a remote memory agent OS
authority; host ownership and workspace authorization remain separate.

See the [validation record](../validation/2026-10-15-native-remote-access.md) for
the actual test scope and platform publication evidence.
