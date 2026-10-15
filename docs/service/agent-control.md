# Agent administration and operation discovery

For local host and app controls, version 4.6.0 adds a
[private desktop operator interface](desktop-operator.md) under the owning OS
account, including backup schedules, independent recovery and, in 4.7.1,
recorded inventory and reviewed retention cleanup. The guide keeps
its native release boundary explicit. Memory API credentials retain the scope
described below.

Use `mnemion-control --credentials /private/workspace.json doctor` for a bounded,
read-only connection report. See [connection and recovery](connection-diagnostics.md)
for offline hosts, rejected credentials, space access and MCP checks. This
diagnostic is available from version 4.0.10.

From **4.0.4**, agents can discover and use every existing HTTP operation through
a reviewed catalog, a command-line client and four compact MCP tools. Version
4.0.5 through 4.0.10 cover **84 operations**, including durable source-sync controls.
Version 4.0.11 adds three OAuth binding operations for **87 total**; see the
[optional organization OAuth guide](oauth.md) for its configuration and limits.
Published **4.2.0** adds 13 [personal sign-in operations](sign-in.md) for
**100 total**. Check [release status](../RELEASE_STATUS.md) before requiring a
version from users. These operations declare `authentication`, `sensitive_input`
and `mcp_available`; passwords, private invitations and rotating credentials use
private CLI input/results instead of generic MCP calls.
Version **4.3.0** adds `oauth.configuration`, `oauth.connections` and `oauth.disconnect` for **103 total**,
with the same permission checks as [personal agent consent](hosted-agent-sign-in.md).
Version **4.8.0** adds `recovery.directory` and `recovery.configure` for **105 total**.
These expose administrator-only references; the [recovery directory guide](recovery-directory.md)
also documents local encrypted-kit creation from a private CLI result file.
Version **4.9.0** adds seven [company-account operations](company-sign-in.md) for
**112 total**. Configuration and authorized link administration are discoverable;
one-use company login steps use private CLI input/results and are excluded from
generic MCP execution.
Schemas load one at a time, so connecting an
assistant does not put the entire administration API into its context.

Every call uses the application's own credential and the existing tenant,
space and role checks. Catalog visibility describes capabilities; it does not
grant permission to use them. Revoking a key or a space grant takes effect on
subsequent operations. Source-derived read-only spaces retain their policy.

`oauth.configuration` inspects the authenticated workspace's agent sign-in mode
and MCP availability without exposing another tenant's issuer settings.

## Available operations

| Area | Operations |
| --- | --- |
| Identity and teams | Inspect identity, create/list spaces and principals, issue/revoke keys, manage grants |
| Personal access (4.2.0) | Configure passwords, invite/reset people, log in, refresh, list/revoke device sessions and invitations |
| Company access (4.9.0) | Inspect configured providers, start/finish private company login, list/link/revoke permitted company identities |
| Memory and evidence | Save, fetch, revise, review, forget, retrieve history, inspect source evidence and attachments |
| Retrieval and knowledge | Search, construct bounded context, explore the knowledge map, maintain core blocks |
| Source connectors | Register, enable/disable, bind access, list/refresh scopes, request/monitor scans, suspend/resume, run sync pages and resolve proposals |
| Embeddings | Discover approved choices, inspect settings, start/control reindexing and resume approved configurations |
| Librarian | Configure approved models and budgets, start/cancel runs, inspect findings, accept/reject/undo proposals |
| Evaluations | Manage datasets, start/cancel runs, inspect/assess results, compare and export |
| Operations | Health, durable receipts, retries, activity, resource insights and Obsidian export |
| Recovery directory (4.8.0) | Read/update administrator-only host, recovery-material and contact references; no host authority is delegated |

Machine setup, database migrations, model-provider configuration, backups and
recovery use the operator's existing `mnemion-service` commands and deployment
credentials. Their host privileges remain separate from a memory API key.
An agent with those operator credentials can follow the
[deployment](deployment.md) and [recovery](recovery.md) procedures.
From 4.0.7, Unix host operators can also use `mnemion-service supervise` to prepare,
start, inspect and stop a background API/worker instance. Its JSON output and
generated startup files are described in [the supervision guide](supervision.md).
From 4.0.8, `mnemion-service updates` adds host adoption, status, signed checks,
staging, compatible application and automatic-update preferences; see the
[managed update guide](managed-updates.md). These JSON commands require local
host access and appropriate private credentials; a remote memory key does not grant it.

Version 4.0.11 also includes local desktop setup, RAM policy/recovery and
stopped-workspace address controls. Authorized agents on the host use the same
typed operator commands as Studio; see [local workspaces](local-workspaces.md)
and [memory resources](memory-resources.md). Earlier 4.0.10 desktop clients
connect to an existing service and do not include these native-hosting controls.

## Discover through MCP

Use the [connection guide](agents.md) to connect with an application key.
Upgrade the server/gateway to 4.0.4 or later and refresh the assistant's tool
connection. Source-sync controls require 4.0.5 and its updated runner.

1. Call `mnemion_operations` with a query such as `librarian` or `connectors`.
   Use `next_offset` to page through results and `groups` to narrow discovery.
2. Call `mnemion_operation` with one returned operation name. Inspect its
   `input_schema`, `effect`, `retry`, `download` and `sensitive_result` fields.
3. Use `mnemion_read` for a read operation or `mnemion_write` for a write.
   Supply the exact `request` envelope described by that schema.
4. Keep returned request/operation IDs. Poll durable operations before treating
   indexing, reindexing, sync or librarian work as complete.

The familiar `memory_save`, `memory_search`, `memory_context`, `memory_fetch`
and other primary tools remain available. A read tool rejects a write before
sending it. The generic write tool advertises possible destructive effects and
does not advertise universal idempotence.

## Use the CLI from any supported OS

Install the Python release on the agent's machine. The catalog and schemas work
offline and do not load an embedding model:

```sh
mnemion-control catalog --query librarian
mnemion-control describe retrieval.search
mnemion-control --credentials app.mnemion-credentials.json call identity.me
```

Create a `recall.json` input file:

```json
{
  "body": {
    "query": "Which project decisions changed this week?",
    "space_ids": [],
    "all_accessible": true
  }
}
```

```sh
mnemion-control --credentials app.mnemion-credentials.json call retrieval.search --input recall.json
```

Use `--input -` to read JSON from standard input. Credentials come from the
private file or `MNEMION_API_URL`/`MNEMION_API_KEY`; there is no command-line token
argument. `--url` can select a HTTPS origin or loopback HTTP address. An address
ending in `/v1/` is accepted. Redirects are not followed with credentials.

The request envelope has `parameters` for path/query values, `body` for JSON,
and `idempotency_key` where the operation supports it. Names and paths come from
the reviewed catalog. Arbitrary URLs, headers and process commands cannot be
injected through an operation request. Input validation never prints rejected
memory text or credentials.

## Private results and bounded memory bandwidth

The CLI returns JSON containing the operation, result, HTTP status, request ID,
attempt count, elapsed milliseconds, response bytes and response SHA-256.
MCP defaults to **32 KiB** of response JSON; the CLI defaults to **64 KiB**.
Choose smaller API pages first. `--max-response-bytes` can raise CLI JSON output
to 256 KiB; an oversized result fails explicitly instead of returning a cut-off
document. MCP permits at most 128 KiB per generic result.

Attachments, Obsidian archives and evaluation exports stream to `--output FILE`,
with a default/maximum of **1 GiB**, rather than entering an agent transcript.
Inline operations have a 90-second retry/transfer budget; downloads have fifteen
minutes. The budget is checked between network chunks, including a slow trickle;
an in-flight socket read may take up to its remaining configured timeout
(capped at thirty seconds). Inputs are bounded to 2 MB, and the combined MCP
transport bounds response buffering before copying a complete API result.

`keys.create` requires `--result-file FILE` and is unavailable through generic
MCP execution. The new file is reserved and made private **before** issuing the
key. The resulting JSON includes top-level `api_url` and `api_key`, so it can
be passed directly to `mnemion-agent`, `mnemion-service --credentials`, or
`mnemion-control --credentials` without printing or copying the secret.
Other `--result-file` operations retain the ordinary JSON result envelope.

From 4.2.0, sensitive sign-in operations also require a private result file.
Login, refresh and invitation acceptance use `transport: "native"` in private
input files and write session metadata with `api_url` and a short-lived
`api_key` alias. Use the new file with `--credentials`; refresh is explicit and
is never automatically retried. Invitation creation writes its private receipt
to `--result-file`. See [agent sign-in controls](sign-in.md#agent-and-operator-controls)
for file privacy and lost-response handling.

Files are created exclusively. An existing file, symlink or invalid filename
is never overwritten. Failed downloads are removed. Unix outputs use mode 0600;
Windows outputs use a protected owner-only DACL before data is written. A
filesystem that cannot enforce the required Windows permissions fails before
the request. Use a private folder; these files contain authorized private data.

## Retry and outcome rules

| Outcome | Meaning | Next step |
| --- | --- | --- |
| `not_sent` | Local validation or output preparation failed | Correct the request or output path |
| `rejected` | The service returned a rejection | Follow the status, permissions and current resource state |
| `unknown` | A response was lost, invalid or incomplete, or the service returned a server error | Inspect durable state before retrying a write |

Reads may retry transient failures. Writes retry only when their operation
explicitly supports idempotency **and** the request includes a stable key.
Retries preserve the complete request and key, and honor bounded `Retry-After`
delays. An uncertain administrative write without idempotency returns
`retryable: false`. The CLI never invents a new key to replay it. Use the same
key only for the same logical write; preserve optimistic version fields.

## Contract maintenance

The authenticated server exposes `GET /v1/agent/operations` and
`GET /v1/agent/operations/{operation_name}`. The CLI catalog describes its own
installed package; the server catalog reports that server's package version.

`mnemion-service agent-schema --output FILE` regenerates the machine-readable
contract from the actual OpenAPI routes without opening a database. CI rejects
unclassified operations, schema drift and duplicate operation names. Each new
public route requires an explicit read/write, download and retry classification.

The catalog does not add hosted OAuth, provision a public tunnel, install a
source runner, or automatically upgrade a deployed server. Those capabilities
remain distinct items on the [roadmap](../ROADMAP.md).
