# Workspace connection and recovery

A workspace lives on the computer running its Mnemion service and database.
Studio, an agent and a tunnel are ways to connect to that workspace. Keep a
human operator's way into the host independent of an agent conversation or its
model quota. A workspace key grants memory permissions; it is not a host login.

## Connect from Studio

Use the workspace's HTTPS address and your own scoped key. The connection form
also accepts its `/v1` API or `/mcp` address. Do not put a key in the address.
Remote workspaces require HTTPS; loopback HTTP is allowed for a local host.
On desktop, remembered keys use the operating system's secure store.

From 4.0.12, desktop API requests bypass ngrok's human browser warning and the
HTTP cache. This fixes a live Windows case where an old cached offline response
hid a recovered host, followed by a browser warning instead of the workspace
identity. No paid tunnel upgrade is needed for this compatibility fix. The
service still checks every key and permission; redirects remain blocked and TLS
verification remains enabled. The host and its tunnel must still be running.

An offline ngrok tunnel now produces a specific error instead of a generic
HTTP 404. Ask the host operator to restore the service and network connection.
Generating another memory key does not restart an offline computer or tunnel.
Browser network/CORS failures can hide proxy headers; in that case use the
diagnostic below from a machine allowed to reach the workspace.

## Saved workspace details when the server is offline

From 4.0.11, open **Details & recovery** beside a saved desktop connection.
The view reads this device's saved workspace address, workspace and identity IDs,
last successful connection, and last verified organization role. It opens without
contacting the workspace. Recovery guides are bundled with the app.

The role and verification date are protected with the saved credential and bound
to its destination and identity. They are historical information: **Reconnect and
verify access** checks the current server identity and key before opening a
session. An expired or revoked credential cannot authorize work through its
cached role, and inspecting a connection does not select or resume it.

Older saved connections remain usable. Their role is shown as unknown until a
successful reconnection records it. Locked or damaged secure storage has an
explicit explanation, while the saved address and guides remain available.
**Use another address or key** opens an empty key field and retains the original
saved connection; confirm a replacement destination before entering a credential.

From 4.8.0, **Recovery directory** lets administrators record host-console
addresses, backup/ledger/source locations and independent contacts. Remembered
administrator connections keep an OS-protected copy in **Details & recovery**.
An encrypted HTML kit can also be opened on another device, or served from the
organization's separate HTTPS site, while the memory host is offline. See the
[directory and kit guide](recovery-directory.md) for setup, permissions and copy
lifetime. Existing connections remain usable when an older server lacks this feature.

A saved connection does not establish that the device contains a database
replica, a complete backup, or authority to restart the host. A Git/cloud source
mirror can recover its tracked documents; full recovery also needs the verified
database backup and current access/deletion ledger described in the
[recovery procedure](recovery.md). Delegated host controls, verified delivery of
independent backups and guided takeover remain in the
[continuity contract](../implementation/workspace-continuity.md).

## Read-only diagnostic for people and agents

This command is included from version 4.0.10.
Use the private credentials JSON from setup; the key is never a command argument:

```sh
mnemion-control --credentials /private/workspace.json doctor
```

Or check public health without a credential:

```sh
mnemion-control --url https://memory.example.com/mcp doctor
```

The JSON report separates service health, readiness, identity, accessible space
counts/roles and MCP initialization/tool discovery. Exit code 0 means all checks
passed and at least one space is accessible. Exit code 1 means a check failed or
could not be completed, including public-only checks without a credential.
This verifies the connection, not retrieval quality or every tool operation.

From 4.0.12, a health route that replies with HTTP 401 is retried once with the
supplied credential at the same address. This supports gateways that protect
health routes as well as the API. Without a credential, the report says
`authentication_required`; it does not say that a nonexistent key was rejected.
Public health routes, known offline tunnels and redirects still receive no key.

Checks use a 25-second overall budget, 5-second request timeouts and a 128 KiB
response limit. They verify TLS, never follow redirects and never run model
inference, read memories, modify access or restart a host. MCP initialization
may create an ephemeral transport session; cleanup is attempted within the same
budget. Normal service access logs may record these checks.

Reports contain fixed error codes/guidance, HTTP status, booleans and counts.
They exclude the private address, key, names, IDs, memory text, raw HTML and
untrusted server messages. Review any surrounding shell logs separately before
sharing them; the credentials file itself must remain private.

From 4.0.13, the spaces check separates the visible `count` from
`accessible_count`, which includes only explicit memory-space roles. Organization
administrators may see compartments without a content grant (`role: null`);
this is a valid response. If all visible spaces lack grants, the report retains
`no_spaces` while still checking authenticated MCP access. The identity check can
confirm organization-administrator authority independently of memory access.

| Result | Next action |
| --- | --- |
| `tunnel_offline` | Open the host's operator console; restart the tunnel and check the Mnemion service. |
| `network_error` / `timeout` | Check the address, host uptime and company VPN/private-network connection. |
| `tls_error` | Repair certificate trust or the company proxy configuration. Keep verification enabled. |
| `redirect` / `not_found` / `invalid_response` | Use the direct Mnemion HTTPS address; check proxy routing/sign-in and API/MCP support. |
| `unauthorized` / `forbidden` | Ask an administrator to review your individual key and grants. |
| `authentication_required` | The gateway protects health checks. Supply the private credentials file. |
| `no_spaces` | Authentication works; an administrator must grant the intended space access. |
| `not_ready` | Check service/database readiness on the host. |

## When an agent hosts the workspace

For Grok Bot, open its separate desktop client, open the bot's controls and select
**Computer**. A sleeping computer offers **Wake**; a running computer offers
**Open**, then **Take control** for operator access. This path was exercised on
Windows without sending a model prompt, and the existing service/tunnel became
reachable after waking its host. Available controls still depend on the account
and provider. Release control when finished. Avoid resetting the computer:
unsynchronized data can be lost. See the
[platform research and official sources](../research/2026-10-11-agent-platforms.md).

For company use, prefer a workspace host and stable HTTPS/private-network address
owned by the organization. Run the service and connector under an independent
supervisor, assign each person/agent revocable access, and keep tested backups
and operator recovery instructions. The [deployment guide](deployment.md) and
[workspace guide](workspaces.md) describe the current supported setup.
Guided invitations, hosted OAuth, independent native remote setup and broader
host recovery remain tracked in the [requirements](../PRODUCT_REQUIREMENTS.md).
