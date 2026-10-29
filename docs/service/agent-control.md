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
Version **4.10.0** lets assistants complete the standard OAuth authorization
flow with an approved company account. Company-provider authentication and
human permission review stay on their dedicated browser pages; the generic
MCP catalog remains **112 operations**. See [account consent](hosted-agent-sign-in.md)
for session expiry, revocation and provider acceptance limits.
Version **4.11.0** adds `local.company-discover` and `local.company` to the
**23-operation private desktop catalog**. These manage an app-owned host's
provider setup and restart under the owning OS account, with the same settings
review as Studio. The HTTP/MCP catalog stays at 112 operations; a memory key
does not grant host configuration. See [company operator controls](company-sign-in.md#agent-and-sdk-controls).
Source **4.12.0** adds ten [vault operations](secrets-vault.md#agent-and-sdk-controls)
for **122 HTTP operations**, and `local.vault`/`local.vault-key` for **25 private
desktop operations**. Value inputs/results use private CLI files. Three dedicated
MCP vault tools are available only when explicitly enabled by the host operator.
Schemas load one at a time, so connecting an
assistant does not put the entire administration API into its context.

Source **4.16.0** adds `journal.organize` to 4.15's `journal.status`,
`journal.configure` and `journal.push`, for **126 reviewed HTTP operations**.
Filing is explicitly enabled, requires reviewer access and retains original
journal bytes. These operations share Studio's permissions,
policy-version checks and explicit retained-history consent. Local destination
enrollment uses `mnemion-service journal` under the operator OS account; memory
credentials cannot select executable or storage paths. See [Git journals](git-journal.md).

Source **4.18.0** adds `local.journal`; source **4.19.0** adds `app.status`,
`app.preferences`, `app.update-check` and `app.update-restart`, for **30 private
desktop operations**. These use the owning OS account and the same controlled
restart, current-state and unsaved-work safeguards as Studio. They add no remote
memory authority. See [app update controls](desktop-operator.md#app-updates-and-startup).

Source **4.23.0** adds `vault.keepass.preview`, `vault.keepass.import` and
`vault.keepass.export`, bringing the reviewed HTTP catalog to **133 operations**.
[KeePass transfer](keepass.md) uses private CLI input/result files, exact preview
approval and current per-credential read grants. The generic MCP surface refuses
these sensitive transport operations; it does not put file passwords or exports
into chat context.

Source **4.33.0** adds `local.models` for [private desktop model setup](desktop-models.md).
Enrollment, key changes, removal and damaged-file repair retain the app's
current-state checks and controlled host restart. They make no model calls and
add no public host-configuration authority.

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

### Large inventories and activity history (4.46.43)

For an inventory, request `memories.list` with `summary: true`. It returns memory
and revision IDs/versions, subject preview, kind, claim/review state, author and
recorded date. Content, source evidence and arbitrary metadata stay in the full
fetch. Subject previews have a 160-byte UTF-8 bound and `subject_truncated` flag;
use `memories.get` when the full text is needed. Follow `next_cursor` without
constructing or editing it. The typed JavaScript SDK offers `client.inventory()`.

The compact `mnemion` tool defaults to 16 KiB per response. For 100 summary
records, explicitly select the existing 128 KiB maximum:

```json
{
  "action": "read",
  "operation": "memories.list",
  "max_response_bytes": 131072,
  "request": {
    "parameters": {"space_id": "SPACE_UUID", "summary": true, "limit": 100}
  }
}
```

`operations.activity` accepts `action`, `memory_id`, `limit` and `cursor`.
Pages are ordered newest first; reuse the same filters with the next cursor.
Every page checks the current reviewer grant. Studio's Activity page provides
the same change filter and older/latest controls. A successful journal filing
pass with zero changes updates its status without creating another audit event.

`principals.list` and `insights.runtime` require a **tenant administrator**.
A **space administrator** manages only its granted space. `connectors.list`
shows the caller's owned connectors, or the tenant's connectors for a tenant
administrator; an empty list does not prove the workspace has no sources.
Source health, access leases, connector control and content permissions are
separate. Ask the responsible tenant/source administrator to inspect an
unavailable source through its supported controls.

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

### Source diagnosis and recovery (4.46.44)

Use the existing `health.sources` operation with `details=true` when a source
warning needs investigation. The default response retains personal grant-based
counts. Explicit diagnostics use the existing source-control permissions:
tenant administrators see affected sources across the organization; active
connector operators see their own. A space administrator's content permissions
do not make them a tenant administrator or connector operator. Other callers
receive `visibility: "unavailable"` without source identities.

```json
{"action":"read","operation":"health.sources","request":{"parameters":{"details":true,"limit":20}}}
```

`diagnostics.items` identifies `space_id`, `connector_id` and the responsible
`operator_id`, with fixed `reasons`, a `recovery` step and current `can_resume` /
`can_request_sync` hints. It omits source paths, external memberships, private
labels, checkpoints and raw error text. Pass `diagnostics.next_cursor` as `after`
for the next page; `limit` is 1–100. Every page rechecks current database access.
The hints do not authorize a later write; each command checks access again.

| Recovery step | Supported action |
| --- | --- |
| `resume_source` | A tenant administrator explicitly calls `connectors.resume` with `space_id`. The source remains unavailable until its runner checks current provider permissions. Intentional pauses should remain paused until their owner chooses otherwise. |
| `request_source_sync` | Read `connectors.sync_status`, then call `connectors.sync_request` with `connector_id` and that response's `requested_generation` as `body.expected_generation`. The registered runner must be online; queuing a scan does not restore permissions. |
| `enable_connector` | A tenant administrator reviews and calls `connectors.enable` with `connector_id`, then follows the refreshed diagnosis. |
| `restore_connector_identity` | A tenant administrator restores an active, dedicated application identity through the organization controls. Connector identities cannot carry tenant-administrator privileges. Recheck status before requesting work. |
| `repair_source_files` | Inspect the authorized source controls / `connectors.scopes` inventory, repair unreadable source files, and request a new scan. A partial inventory does not authorize deleting retained memories. An access failure names one source-relative path, its SHA-256, and a fixed category such as `source_permission_denied` or `source_disappeared` on that inventory. The same receipt withholds every previously indexed item that scan did not re-read, including files the walk never reached. A refreshed access lease does not remove the failure, advance the last complete scan, reveal those items, or make them eligible for background indexing. A body-free retain is not a new read. A later scan that reads the files restores them even when the body and revision are unchanged. Readable but malformed text keeps the last good copy and does not quarantine the source. |

In the app, **Connections → Source availability** shows the same affected
sources and links to existing controls. Python uses
`client.source_health(details=True, after=cursor, limit=20)`; TypeScript uses
`client.sourceHealth({details: true, after: cursor, limit: 20})`.
Reading the diagnostic view performs no recovery action.

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

The response envelope also reports `idempotency: "new"`, `"replayed"`, or
`null`. Supporting servers expose this as `X-Mnemion-Idempotency` after an
authorized receipt lookup. `null` means the operation has no observed receipt
classification, including older servers; it does not prove a new write. A
replayed receipt keeps the original operation result. Neither classification
proves that asynchronous indexing, evaluation or librarian work has finished.

The owned `mnemion-control call` entry point uses the installation's
[product telemetry choice](../guides/product-telemetry-controls.md). Its reviewed
[operation coverage](../../mnemion/product_telemetry/control-origins.json)
excludes inspection, nested transport and session refresh. Cached writes and
keyed writes without a fresh receipt do not contribute a new use. Generic SDK
and remote MCP/API calls do not infer a local measurement owner. Collection
remains unavailable while V08 is being completed.

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
