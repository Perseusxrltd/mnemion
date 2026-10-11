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

An offline ngrok tunnel now produces a specific error instead of a generic
HTTP 404. Ask the host operator to restore the service and network connection.
Generating another memory key does not restart an offline computer or tunnel.
Browser network/CORS failures can hide proxy headers; in that case use the
diagnostic below from a machine allowed to reach the workspace.

## Read-only diagnostic for people and agents

This command is included in the next patch after 4.0.9 (available from `main`).
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

Checks use a 25-second overall budget, 5-second request timeouts and a 128 KiB
response limit. They verify TLS, never follow redirects and never run model
inference, read memories, modify access or restart a host. MCP initialization
may create an ephemeral transport session; cleanup is attempted within the same
budget. Normal service access logs may record these checks.

Reports contain fixed error codes/guidance, HTTP status, booleans and counts.
They exclude the private address, key, names, IDs, memory text, raw HTML and
untrusted server messages. Review any surrounding shell logs separately before
sharing them; the credentials file itself must remain private.

| Result | Next action |
| --- | --- |
| `tunnel_offline` | Open the host's operator console; restart the tunnel and check the Mnemion service. |
| `network_error` / `timeout` | Check the address, host uptime and company VPN/private-network connection. |
| `tls_error` | Repair certificate trust or the company proxy configuration. Keep verification enabled. |
| `redirect` / `not_found` / `invalid_response` | Use the direct Mnemion HTTPS address; check proxy routing/sign-in and API/MCP support. |
| `unauthorized` / `forbidden` | Ask an administrator to review your individual key and grants. |
| `no_spaces` | Authentication works; an administrator must grant the intended space access. |
| `not_ready` | Check service/database readiness on the host. |

## When an agent hosts the workspace

For Grok Bot, the official computer documentation describes **Agent Computer →
Take over** and computer recovery/update controls. Use the operator interface to
inspect the durable workspace and restore its service/tunnel; a chat with an
out-of-quota Bot is not the only documented management path. Availability of
those controls on a particular account still needs checking. Avoid resetting
the computer: unsynchronized data can be lost. See the
[platform research and official sources](../research/2026-10-11-agent-platforms.md).

For company use, prefer a workspace host and stable HTTPS/private-network address
owned by the organization. Run the service and connector under an independent
supervisor, assign each person/agent revocable access, and keep tested backups
and operator recovery instructions. The [deployment guide](deployment.md) and
[workspace guide](workspaces.md) describe the current supported setup.
Guided invitations, hosted OAuth, independent native remote setup and broader
host recovery remain tracked in the [requirements](../PRODUCT_REQUIREMENTS.md).
