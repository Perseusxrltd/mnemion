# Connecting clouds, vaults, and company systems

Mnemion keeps canonical memory in its service. Source adapters run where the
operator has access to a repository, vault, cloud account, or company network.
They send versioned observations through the same authenticated API used by
applications. Provider credentials stay with the adapter; the service does not
fetch arbitrary URLs or store Slack, Google, Git, or rclone credentials.

## Included adapters

| Adapter | Reads | Access model | Current boundaries |
| --- | --- | --- | --- |
| Git | Committed text from a selected local repository or HTTPS/SSH remote and ref | Explicit publication to mapped identities | No checkout, hooks, submodule execution, or writes upstream. Uncommitted files are excluded. |
| Filesystem / Obsidian vault | UTF-8 Markdown, text, JSON, JSONL, CSV from a chosen folder | Explicit publication to mapped identities | Preserves text and wikilinks. Ignores Obsidian settings, common credential files, and generated Mnemion mirrors by default. Internal symlinks produce an error. |
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

## Set up an adapter

1. Create a dedicated **application** principal without organization administrator
   rights, then issue its own Mnemion API key. Do not reuse an assistant's key.
2. As an organization administrator, register `POST /v1/connectors` with `name`,
   `provider`, `principal_id`, and `access_mode`. Use `provider` for Slack/Drive or
   `published` for filesystem/Git/rclone.
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

## Updates, permissions, and deletion

Each provider scope has an access lease, default **15 minutes**, configurable
from 60 seconds to 24 hours. The adapter records when it actually observed
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

Text is split into bounded, stable source parts with source hashes, exact captured
text, and character offsets. The initial built-in file limit is 20 MB, configurable
up to 100 MB; individual API pages stay below the service's 2 MB request limit.
Store large or rich original files in the provider or an approved evidence store;
the ordinary connector API is not a binary object-store backup.

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
