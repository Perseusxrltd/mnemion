# Connecting clouds, vaults, and company systems

Mnemion keeps canonical memory in its service. Source adapters run where the
operator has access to a repository, vault, cloud account, or company network.
They send versioned observations through the same authenticated API used by
applications. Provider credentials stay with the adapter; the service does not
fetch arbitrary URLs or store Slack, Google, Git, or rclone credentials.

Studio 4.31.0 provides [desktop source setup](desktop-sources.md) for folders,
Obsidian vaults and growing JSONL conversations, including protected keys,
background scans, RAM limits and matching private-agent controls. The device
can contribute to a shared workspace without hosting a local database.
Source 4.34.0 adds [guided Slack and Drive setup](desktop-cloud-sources.md) with
existing approved credentials. Interactive provider-account enrollment remains
separate from this selected-source workflow.

**Unreleased:** [retained conversation capture](durable-capture.md) adds explicit
source and device approval, an encrypted local inbox and delivery after producer
logs disappear. Existing adapters remain mirrors. Its native journey and full L1
acceptance are still pending; consult [release status](../RELEASE_STATUS.md) for
published availability.

## Included adapters

| Adapter | Reads | Access model | Current boundaries |
| --- | --- | --- | --- |
| Git | Committed text from a selected local repository or HTTPS/SSH remote and ref | Explicit publication to mapped identities | No checkout, hooks, submodule execution, or writes upstream. Uncommitted files are excluded. |
| Filesystem / Obsidian vault | UTF-8 Markdown, text, JSON, JSONL, CSV from a chosen folder | Explicit publication to mapped identities | Preserves text and wikilinks. Ignores Obsidian settings, common credential files, and generated Mnemion mirrors by default. Internal symlinks produce an error. |
| [Live conversations](live-conversations.md) (4.17.0+) | Selected complete records or supported messages from growing JSONL logs | Explicit mapped audience; one managed scope per file for mirrors | Bounded fragments, deferred tails, metadata checkpoints and body-free reuse. Capture mode controls whether raw records are copied. Requires a running source host; [retained custody](durable-capture.md) is a separate unreleased choice. |
| Google Drive | Selected files or recursive folders; text files; Docs, Slides and all sheets in Sheets exports | A managed permission scope for each file; mapped effective user permissions | Shared-drive API flags are enabled. Unmapped users, groups, domains and `anyone` grants confer no Mnemion access. Group expansion requires an identity-aware custom adapter. |
| Slack | Explicitly selected channels, messages, edits, and threads | Channel membership mapped to Mnemion identities | Read-only. No messages are sent. Attachment references are retained; attachment binaries are not downloaded. The credential must be allowed to read history, membership, and requested threads. |
| rclone | Text objects from an operator-configured remote | Explicit publication to mapped identities | Supports the storage providers available in the installed rclone, including S3-compatible stores, OneDrive, Dropbox, WebDAV, and private endpoints. No automatic provider ACL translation. |
| Custom adapter | Any system that can produce source observations and permissions | Provider-derived permissions or explicit publication | Use the Python connector protocol or its versioned HTTP routes. No provider-specific SDK is required on the server. |

These are ingestion adapters, not blanket certification of every account type,
provider deployment, file format, or rclone backend. Unsupported formats and
insufficient permissions fail visibly. Git and rclone must be installed on the
adapter host. Windows, macOS and Linux use the same configuration and protocol.

An Obsidian vault can live in a cloud-synchronized folder or Git repository.
Import its selected notes as a source, or refresh a local visualization vault
and let the chosen storage client transport it. Keep the ingestion root and the
generated visualization separate to avoid feedback loops. A synchronized folder
is not a replacement for the authoritative database or a verified recovery archive.

From 4.13.0, text imports also reject recognized host database-login documents,
recovery state and Mnemion key material even when a private file is renamed.
Host recovery archives and `host-secrets.json` are excluded from folder selection.
Normal documentation that explains configuration fields remains importable.
Keep source folders separate from runtime credentials; this guard is not a
general-purpose secret or personal-data classifier.

## Connected sources and writable memory

A connected Git repository appears in a connector-managed source space. Its
imported content remains controlled by the repository and the connector's access
mappings. The same applies to other connected providers. Your team's writable
memory, such as an **Office** space, remains a separate compartment. This keeps
ordinary source permissions, source changes and provider deletions enforceable.
Retained conversation custody has its own explicitly approved source space;
producer-file deletion does not withdraw already accepted retained evidence.

**Search both together.** First map the person or agent to the source identities
it is allowed to read. Then use **Search & context → All accessible memory** in
Studio, or send the following to `POST /v1/recall` or `POST /v1/context`:

```json
{"query":"What did we decide?","space_ids":[],"all_accessible":true}
```

MCP `memory_search` and `memory_context` accept the same explicit scope. From
4.1.6, omitting their `space_ids` also selects currently accessible spaces;
explicitly selected IDs still narrow the request. The
Python client equivalent is `client.search("What did we decide?",
all_accessible=True)`. Each returned hit or citation retains its source and
`space_id`. This searches currently readable spaces in one workspace; it does
not combine other saved personal/company connections or grant access to an
unmapped repository.

For a narrower search, supply the selected source and writable space IDs in
`space_ids` and leave `all_accessible` false. In the HTTP API, omitting both
scope choices or selecting both is rejected with the scope-selection rule. Explicit selection
prevents an API client from accidentally searching a broader scope than intended.

**Git revisions follow individual paths.** From 4.1.6, a Git document's revision,
`git_commit` metadata and immutable evidence URL use the last change of that
path within the selected repository snapshot. Unrelated commits do not revise
the document, queue its embeddings again or refresh its memory timestamp.
The recorded commit can therefore precede the watched branch's current HEAD.
It still identifies the exact cited file contents. Changed, renamed and deleted
paths continue through the existing complete-inventory and permission rules.
The first scan after upgrading can update older commit-wide provenance once;
later unchanged paths retain their existing revisions. Rewriting Git history
or changing connector extraction settings may also legitimately revise evidence.

**Save new notes to a writable space.** Select one with contributor or higher
access from `memory_spaces` or `GET /v1/spaces`. Searching a source never grants
permission to write into it, and the connector does not push changes upstream.
To change the source itself, edit the repository/provider and request a rescan.
From 4.15.0, an independently approved [Git journal](git-journal.md) can publish
future native changes from a writable space. It does not grant inbound
connectors permission to write upstream. Replay requires the complete journal
root, including its catalog and archive.
Do not copy its contents into a writable space merely to make search unified;
that would detach the copy from the source's access and deletion lifecycle.

## Retained conversation capture (unreleased)

The [retained capture guide](durable-capture.md) covers the app choice, current
limits, status, recovery and equivalent native-agent controls. An administrator
approves `capture_mode`, namespace and mapped audience through
`capture.source.configure`, then binds `capture.grant.configure` to one exact
dedicated application key. The normal source key cannot authorize itself.
Desktop enrollment supplies those approvals as the typed `source.custody`
object and creates a separate OS-sealed inbox key.

Each scan commits selected evidence and its verified position locally before
HTTP. It retries exact saved pages, applies current forgetting fences and retains
accepted evidence through offline operation or raw-log rotation/removal. The
capture selection is immutable for that inbox; new devices cannot infer earlier
accepted or forgotten history from current files. Existing mirrors need a
reviewed migration before changing retention.

The ordinary `mnemion-connect` configurations and commands below keep their
existing mirror behavior. The unreleased [headless capture guide](headless-capture.md)
describes the separate top-level `capture` configuration and local stdin
controls for retained enrollment, scheduling and recovery. `custody` belongs
to private desktop source settings; neither field belongs inside `provider`.
Server custody approval alone does not enroll a local runner. Successful
delivery also does not establish indexing readiness or completed librarian work.

Unreleased development source adds `mnemion-service connect` and bundled
`mnemion-engine connect` (`mnemion-engine.exe connect` on Windows). They use the
same `mnemion-connect` options, configuration and private stdin control body;
see [runner entrypoints and installed locations](headless-capture.md#choose-a-runner-entrypoint-unreleased).
The `capture` object still controls retention. All six packaged journeys remain
pending; these new entrypoints are not included in public 4.44.0.

Desktop retained-source removal requires a pause, explicit local discard and confirmed
grant revocation. A current workspace administrator can confirm retirement if
the saved device key is unavailable, using a removal-only credential that is
never saved by the operation. See [removal and recovery](durable-capture.md#pause-remove-and-forget)
for the app and private-agent paths, including offline cleanup after a confirmed
retirement was recorded locally.

## Set up an adapter

1. Create a dedicated **application** principal without organization administrator
   rights, then issue its own Mnemion API key. Do not reuse an assistant's key.
2. As an organization administrator, register `POST /v1/connectors` with `name`,
   `provider`, `principal_id`, and `access_mode`. Set **`provider`** to the adapter
   name: `slack`, `gdrive`, `filesystem`, `git`, `rclone`, or your custom adapter's
   name. Set **`access_mode`** to `provider` for Slack/Drive or `published` for
   filesystem/Git/rclone. For example: `{"provider":"filesystem","access_mode":"published"}`.
   Each connector needs its own application principal; an existing connector's
   provider cannot be changed while retaining its source identities.
3. Map source identities using `PUT /v1/connectors/{id}/bindings`: `external_id`,
   `principal_id`, and `role` (`reader` or `reviewer`). Unknown identities get no
   access. An application may be mapped explicitly to the source audience it
   needs. A connector cannot create mappings or grant access to other spaces.
4. Put the connector configuration on its host. Reference private environment
   variables or token files; never put bearer tokens in the JSON configuration.
   Restrict token-file permissions/ACLs to the adapter account. Token files are
   reread for provider requests, supporting rotation by a secret manager.
5. Run `mnemion-connect --config connector.json --inspect` to inspect source scope
   IDs and memberships. This reads the provider and service without importing or
   changing access. Add the required identity mappings, then run without
   `--inspect`. Add `--watch` for repeated scans.

`provider` names the adapter; `access_mode` names its permission policy.
The API rejects `provider: "provider"` and `provider: "published"` with an
actionable message. Before reading a source, the runner also checks that the
configuration matches the registered provider and access mode. A token reference
must be an object such as `{"file":"/private/source.key"}` or
`{"env":"MNEMION_CONNECTOR_KEY"}`. Invalid configuration reports this shape
without echoing the supplied credential.

On an adopted Linux/macOS service host, use the
[managed connector launch path](managed-connectors.md) to follow verified
service hotfixes. A plain `--watch` process keeps its installed runtime; its
startup record identifies that manual update mode. Scan reports include the
actual runner version. Stop the old runner before transferring its existing
configuration to managed mode.

The new service/engine entrypoints follow the same rule: `--managed-state`
requires `--watch` and an existing adopted Linux/macOS host. An independently
started engine watcher needs its own process startup and restart handling.
Standalone Windows watchers do not automatically follow Studio updates.

For a local or synchronized vault:

```json
{
  "version": 1,
  "service_url": "https://memory.example.com",
  "service_token": {"env": "MNEMION_CONNECTOR_KEY"},
  "connector_id": "00000000-0000-0000-0000-000000000001",
  "provider": {
    "type": "filesystem",
    "path": "./company-vault",
    "scope_id": "engineering-vault",
    "name": "Engineering vault",
    "members": ["employee:alice", "application:engineering-assistant"],
    "publish_to_mapped_members": true
  }
}
```

Replace the example UUID with the registered connector ID. Relative file paths
resolve beside the configuration on all platforms. The required publication
flag acknowledges that this adapter cannot infer the source's effective ACLs.
Sharing a Git credential or rclone remote does not automatically authorize a
whole team to read its contents.

Alternative `provider` configurations:

```json
{"type":"git","path":"./repo-cache","remote":"https://github.com/example/knowledge.git","ref":"main","scope_id":"knowledge-repo","name":"Knowledge repository","members":["team:engineering"],"publish_to_mapped_members":true}
```

```json
{"type":"rclone","remote":"company:Knowledge","config_file":"./private/rclone.conf","scope_id":"company-documents","name":"Company documents","members":["team:engineering"],"publish_to_mapped_members":true}
```

```json
{"type":"slack","token":{"file":"./private/slack.token"},"team_id":"T12345678","channels":["C12345678"],"include_threads":true}
```

```json
{"type":"gdrive","token":{"file":"./private/google-access.token"},"folder_ids":["GOOGLE_FOLDER_ID"],"file_ids":[],"recursive":true}
```

Slack binding IDs are `slack-user:U12345678`. Drive binding IDs are
`google-user:PERMISSION_ID`, taken from a **user** permission, not an email guessed
from a document title. Provision OAuth/workload credentials with read permissions
for the selected sources. Google access tokens must be refreshed by the operator's
credential provider. The runner does not implement an interactive OAuth consent UI.

## Git snapshot freshness

From 4.3.2, **Connections → Source status** and
`GET /v1/connectors/{id}/sync` expose `scanned_commit`, `scanned_at` and
`scanned_space_id` for the latest completed Git scope. Ordinary scan output also
includes `scanned_commit`; [managed host status](managed-connectors.md) retains
the last successfully observed scan's commit and date. These fields are empty
until a compatible runner completes an inventory. The API and CLI agent controls
use the same status and authorization as the app.

A remote Git connector fetches its configured reference and pins that scan to
the fetched commit. A bare cache's `refs/heads/main` can still point to the
original clone: the connector does not rewrite branches that another local tool
may use. Compare the reported **scanned commit** with the upstream tip at the
observation time. `FETCH_HEAD` is a fetch observation and can advance before a
scan succeeds; it is not a completed-ingestion receipt. No extra fetch is made
by reading status.

The complete-inventory checkpoint advances only after all pages and the removal
sweep finish. A failed scan leaves the previous commit and completion time;
`last_successful`, access state and pending requests still show the current
attempt's outcome. A completed scan means the source inventory was processed;
local corrections can still await review and embeddings can still be pending.
Use source proposals and index status for those separate states.

Per-memory `metadata.git_commit` and `source_modified_at` continue to describe
that file's last change. They should not all equal the scanned repository tip.
This separation preserves unchanged-file revisions and meaningful recency.
Existing checkpoints and optional response fields provide the new observation
without a database migration or re-index.

## Scan timing and immediate requests

From 4.0.5, **Connections → Source status → Sync now** requests a complete scan by
the connector's existing runner. The equivalent HTTP routes are
`GET /v1/connectors/{id}/sync` and `POST /v1/connectors/{id}/sync` with
`{"expected_generation": N}`, using the generation returned by the GET.
Organization administrators and that connector's dedicated application can
request scans. Other source readers and reviewers cannot. Provider credentials
remain on the runner; this endpoint accepts no URL, command, Git payload or token.

The watch configuration has these optional top-level settings:

| Setting | Default | Meaning |
| --- | --- | --- |
| `poll_seconds` | `300` | Seconds after a scan before the next scheduled full scan; range 30–86400 |
| `remote_sync` | `true` | Check the service for durable immediate-sync requests |
| `trigger_poll_seconds` | `5` | Seconds between small control checks; range 1–60 |

At the defaults, an idle connected runner observes a request in approximately
five seconds, plus network time. Source fetching, provider rate limits and
indexing add their own latency. A busy runner finishes its current scan first;
requests arriving during that scan remain pending. Only a successful complete
scan acknowledges the generation it observed **before** reading the source.
Failed scans keep requests pending and wait at least 30 seconds before another
requested attempt. Normal scheduled scans continue if control checks fail.
Configurations and credential files reload between runs; token files are also
reread for control checks. A stopped runner cannot fetch a source, so Studio
shows the outstanding request without claiming that the source is current.

Control checks do not fetch the provider, run embeddings or ingest memories.
They read one small record per connector, about 12 API requests per minute at
the default interval. Increase `trigger_poll_seconds` or disable `remote_sync`
when minimizing control traffic matters more than prompt synchronization.
An older server returning 404/405 retains the ordinary polling behavior.
Upgrade **both server and runner** to receive immediate requests and reports.

Agents can discover `connectors.sync_status`, `connectors.sync_request` and
`connectors.sync_report` through [the operation catalog](agent-control.md).
The first two are also typed SDK methods:

```python
status = client.connector_sync_status(connector_id)
requested = client.request_connector_sync(
    connector_id, expected_generation=status.requested_generation,
)
```

TypeScript uses `connectorSyncStatus(id)` and
`requestConnectorSync(id, status.requested_generation)`. After an uncertain
request or a 409 conflict, read status again before deciding whether another
scan is needed. Writes are not blindly retried. The comparison prevents two
agents using the same observed generation from duplicating a request.

A company's Git push workflow can call these authenticated routes using its
protected connector credential. Mnemion does not yet accept unauthenticated
GitHub webhooks or supply provider-specific webhook signature verification.
No inbound port or public tunnel is required on the runner.

Each runner result includes UTC `started_at` and `timestamp`, elapsed
`duration_seconds`, `changed`, `removed`, `unchanged` and `conflicts`, plus the
per-scope results. Changed means created or revised canonical memories; a review
proposal is reported as a conflict. Removed includes explicit deletion outcomes
and the final cumulative snapshot-pruning count, without double-counting batches.
Counts in an incomplete scan cover its completed scopes. Fatal failures log a
timestamp and bounded error code; provider response bodies and credentials are
excluded. Server status records the latest reported result and request/completion
generations. It is not a historical analytics store or a runner heartbeat.
Exit code 2 indicates an incomplete scan or unconfirmed control report; already
committed observations remain committed. An unconfirmed report also activates
the watcher's retry backoff, avoiding repeated cloud scans every five seconds.

Version 4.0.5 adds migration `012_connector_sync_requests.sql`. Follow the
coordinated backup, migration and restart instructions in its
[release notes](../releases/4.0.5.md). Existing indexes and Obsidian formats stay
unchanged; a Studio update alone cannot migrate a separately hosted server.

## Text-file failures and source health

From **4.21.0**, folder, Git and rclone scans skip ordinary text files containing
invalid UTF-8 or binary data, and files exceeding `max_file_bytes`. Other valid
files continue updating. The original bytes are never changed or decoded with
replacement characters.

The app's **Connections → Source status → File status** shows the skipped count,
relative paths and reasons. CLI scan receipts and each scope's `inventory`
response contain `incomplete_inventory`, `skipped_documents` and `file_errors`.
Detailed errors are bounded to 50 paths of at most 512 characters, each with a
SHA-256 of the complete relative path. No source content or absolute host path
is included. Repair the file or deliberately exclude it, then request another
scan; a clean result clears the warning.

A partial scan keeps previously indexed versions, which may be stale. It does
**not** infer that unreadable or unvisited files were deleted, advance the last
complete checkpoint/time, or acknowledge a requested complete sync. Already
applied healthy updates remain committed. A later complete scan performs the
normal missing-file reconciliation. Scan exit code 2 and `last_successful:
false` keep this distinction visible even when healthy files changed.

Search/context add `connector_inventory_incomplete` and
`connector_scope_suspended` warnings for the caller's selected source access.
`GET /v1/health/sources` returns scoped counts, `attention` and `observed_at`;
Python `client.source_health()`, TypeScript `client.sourceHealth()` and agent
operation `health.sources` use the same authenticated endpoint. An existing
grant lets its holder learn that access expired or was suspended, without
returning source content, ACLs, paths or IDs. Other users' sources do not enter
the summary. Explicitly narrowed recall does not warn about unrelated sources.

`/health/ready` checks service availability. With a valid Authorization header,
it also checks that caller's source health and includes the same `attention`
warnings. Without credentials it returns `source_health_checked: false` and no
private source status. A healthy HTTP process or Supervisor `ready` result is
not a complete-source-delivery receipt; monitor the authenticated source status
and scan timestamps too. No third-party alerting service is configured by this
feature.

Upgrade both service and source runners. An older server that lacks the partial
inventory capability causes the runner to retain fail-closed behavior with
`text_source_server_upgrade_required`. Migration `024_source_health.sql` adds
an index and a narrowly scoped health function, with no memory rewrite.

Directory/catalog failures, symlinks, lost permissions and provider read failures
still suspend the scope. Unreadable JSON/JSONL and partial Git-journal inventories
also stay fail-closed, because a skipped catalog or denial could expose withdrawn
evidence. Use [live conversation capture](live-conversations.md) for actively
appended transcripts. This change does not repair malformed files or bypass
provider access rules.

## Updates, permissions, and deletion

Each ordinary provider scope has an access lease, default **15 minutes**,
configurable from 60 seconds to 24 hours. The adapter records when it actually observed
permissions. Expired or suspended access is denied in database row-level policies,
including search, source/history fetches, context, and exports. The connector
identity retains access to its own scope so it can perform recovery and fresh
permission checks. Disabling the connector/principal denies that access too.

Revoking an identity mapping suspends affected scopes immediately. A fresh
provider observation can grant only identities in the current mapping. Ordinary
space-grant endpoints cannot override a managed source's permissions. Credentials
and already-downloaded exports cannot remotely erase a recipient's own copy;
their storage and retention remain the recipient's responsibility.

The service coordinates competing adapters with a five-minute ingestion lease.
Pages commit atomically with durable receipts. Replaying a page with a different
payload is rejected. Checkpoints advance only after a successful run. Page
progress renews the lease; an expired worker cannot overwrite a newer run.

An explicit deletion removes the source observation from ordinary retrieval
immediately and queues physical erasure. A complete, authoritative snapshot can
also withdraw items absent from its inventory. Incomplete pagination, rate-limit
failures, missing roots, unsupported content, and lost permissions never authorize
that missing-item sweep. Lost access suspends the scope instead of pretending the
source was deleted. Drive's ambiguous “removed”/404 cases use this conservative
behavior. Large deletion sweeps finalize in bounded transactions; the final
checkpoint is withheld until all batches complete.

A source identity deleted in Mnemion stays deleted on subsequent scans. Renaming
or creating a genuinely new source identity is a separate observation; identical
text in another permission scope is not automatically merged. Human corrections,
reviewed claims, and quarantine are preserved. A changed upstream source becomes
a proposal for a reviewer to accept or keep separate from the local correction.

Slack and Drive currently use complete scans. This detects older edits and
deletions that a simple “messages newer than timestamp” poll would miss. Provider
rate limits therefore determine feasible history size and poll intervals. Slack
documents a one-request-per-minute/15-object limit for some new commercially
distributed apps; internal customer-built and Marketplace apps have different
limits. Rate limits are honored, and cursors/permissions are not fabricated.

Recovery requires a current deletion/access ledger. It includes connector
bindings and deleted external identities, including identities first seen after
the backup. Restored scopes stay suspended until permissions are checked again.
An old backup cannot silently reinstate a removed identity mapping.

## Add a company adapter

```python
from mnemion.sdk import Client
from mnemion.connectors import ConnectorClient, Document, Scope

# Obtain these values from your deployment's credential/identity provider.
with Client(service_url, connector_key) as client:
    connector = ConnectorClient(client, connector_id)
    scope = connector.refresh(Scope(
        external_id="project:approved-handbook",
        name="Approved handbook",
        members=verified_external_user_ids,
    ))
    document = Document(
        external_id="document:stable-provider-id",
        revision="immutable-provider-version",
        title="Release procedure",
        text=source_text,
        uri="https://docs.example.com/release-procedure",
    )
    result = connector.sync(scope["space_id"], document.items())
```

`sync()` defaults to a complete snapshot: pass the **entire** scope inventory,
not just the changed document. For changes only, use `mode="incremental"` and
explicit `ConnectorItemInput(action="delete", ...)` events for deletions. Yield
`None` after remote pages to persist progress and renew the ingestion lease.
Use the same scope ID, external source IDs, version semantics and permission
mapping on every hardware instance. Do not use local filenames that change per
machine as cross-device identities.

On 4.17.0+, an unchanged inventory member can use
`ConnectorItemInput(action="retain", external_id=..., revision=...)` without a
memory body. The exact revision must already exist in that scope; otherwise the
service returns `source_reference_unavailable` and the adapter must resend full
evidence. This never creates, edits or revives a memory or replaces a review
proposal. A complete snapshot still includes every retained identity. Python
`sync()` also accepts a checkpoint callable; a final progress marker can store
verified capture counters after streaming completes.

Text is split into bounded, stable source parts with source hashes, exact captured
text, and character offsets. The initial built-in file limit is 20 MB, configurable
up to 100 MB; individual API pages stay below the service's 2 MB request limit.
Store large or rich original files in the provider or an approved evidence store;
the ordinary connector API is not a binary object-store backup.
The [live JSONL adapter](live-conversations.md) has separate streaming limits,
per-file scopes and documented generation/removal semantics.

## Validation and provider references

Provider contract tests cover Git commits, UTF-8/newlines, selected paths,
membership pagination, thread deduplication, token-file rotation, rate limits,
incomplete inventories, Drive file-version checks, and all spreadsheet sheets.
The service tests use real PostgreSQL and separate non-owner application/worker
roles. OAuth installation and live customer accounts require deployment-specific
acceptance; test fixtures are not presented as live-provider certification.

Primary references checked 9 October 2026:

- [Slack history](https://docs.slack.dev/reference/methods/conversations.history/),
  [members](https://docs.slack.dev/reference/methods/conversations.members/), and
  [replies](https://docs.slack.dev/reference/methods/conversations.replies/).
- [Drive permissions](https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions/list),
  [exports](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/export),
  and [changes](https://developers.google.com/workspace/drive/api/guides/manage-changes).
- [rclone inventory](https://rclone.org/commands/rclone_lsjson/) and
  [Git tree inspection](https://git-scm.com/docs/git-ls-tree).
