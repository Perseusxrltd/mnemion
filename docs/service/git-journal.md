# Git journals for native memory

Source **4.15.0** adds optional publication of future native changes to a
host-approved Git destination. Ordinary saves return after a private local
journal is durable; important saves also require Git to acknowledge the push.
Check [release status](../RELEASE_STATUS.md) before requiring this version.

An inbound Git connection does not enable publication. Existing memories, core
blocks, attachments, credentials and organization settings are not backfilled.
Use a [complete host recovery package](host-recovery.md) to preserve accounts,
grants, native database IDs and source settings. A journal protects published
memory text and provenance, with the recovery boundaries described below.

## Setup

1. Install Git on the API host. Authenticate its **service OS account** through
   Git's credential manager, with write access to the selected repository. Use
   an existing free Git provider or a bare repository you operate.
2. Read the organization ID from `GET /v1/me` and choose a native writable space
   from `GET /v1/spaces`. Connector-managed source spaces cannot publish through
   this feature.
3. Register a destination locally. Replace the example IDs and paths; no secret
   belongs in a command or repository URL:

   ```sh
   mnemion-service journal enroll --config /private/mnemion/journals/registry.json --id office --label "Office memories" --tenant 11111111-1111-4111-8111-111111111111 --space 22222222-2222-4222-8222-222222222222 --state /private/mnemion/journals/office --remote https://git.example.com/team/memories.git --branch main
   ```

   Windows uses the same command with absolute paths such as
   `C:\Users\Alice\AppData\Local\Mnemion\journals\registry.json`. Quote paths
   containing spaces. State and registry files must be private to the service
   OS account. The tool creates owner-only files/Windows ACLs and rejects unsafe
   or linked state. `--local-repository /absolute/team-memory.git` can replace
   `--remote` for an explicitly selected existing bare repository. Storage on
   the same disposable host does not protect against losing that host.
4. Set `MNEMION_WRITEBACK_CONFIG` to the private registry's absolute path in the
   API host environment, then restart the API. For a supervised host, use its
   private environment configuration. For Compose, provision Git/credentials
   inside the API container and mount the private registry and persistent state.
   Enrollment does not automatically change an existing service's environment.
5. In Studio, select the space and open **Git journal**. Review the repository,
   branch and folder, then acknowledge publication and retained Git history.
   Configuration requires organization administration **and** administrator
   access to this space. The default interval is 300 seconds, configurable
   between 30 and 86,400. Only future native changes are captured.

Git installation, credential-manager sign-in and initial host registration still
require an operator; this is not yet complete app-only onboarding. The app/API
cannot choose arbitrary host paths, destinations or scanner programs. No paid
account or provider subscription is created by this feature.

`mnemion-service journal status --config /private/mnemion/journals/registry.json`
validates registrations and prints fingerprints. Enroll additional unique
destinations into the same registry. Replacing an existing registration requires
its current `--expected-fingerprint`; restart the API and approve the new policy
in Studio. Each space needs a separate state directory and repository prefix.
Changing a destination does not migrate previously published history.

## Save acknowledgments and failures

Use the normal HTTP/SDK/MCP save and revision commands. Add
`"metadata":{"important":true}` or select the app's important checkbox to
require immediate Git delivery. Preserve other metadata when revising it.

Receipts add `writeback.event_id`, `durability`, `remote_pending` and
`external_history_retained`. `local_journal` means the database and private
journal are durable locally; `remote_git` also means Git confirmed publication.
These fields describe the save's acknowledgment, not the repository's future
state. Read journal status for current pending counts and the last confirmed
commit. Lexical and semantic indexing retain their normal separate receipts;
searching the original memory does not wait for a connector rescan.

Memory, revision, indexing operation and journal event share one database
transaction. A scan rejection returns 422 and rolls the save back. Journal
delivery happens only after commit. If storage or Git fails after commit,
`journal_delivery_pending` returns 503: **retry the same input with the same
idempotency key**. The memory already exists in the database; a different key
can duplicate it. A transport timeout is also an uncertain outcome. Python and
TypeScript clients retain keys during retries; the app retains the key while
the submitted input remains unchanged.

## Privacy, permissions and deletion

Secret checks are always enabled for recognizable Mnemion/cloud/API keys,
private keys, credential URLs and common credential assignments. Default
personal-data patterns cover email addresses, SSNs and international telephone
numbers. These checks can have false positives and cannot recognize every
secret or personal detail; they are not a universal compliance classifier.

The private registry accepts `personal_data_scan` and a `scanner` array. A
scanner is an absolute, operator-reviewed executable plus literal arguments,
run without a shell. It receives one journal JSON record on stdin, with service
credentials removed from its environment. It must exit 0 and return
`{"allow":true}` within five seconds. Output is bounded; raw stderr and rejected
content are not reflected to callers. Scanner code runs as the service OS user,
not in an isolated sandbox. Changed registrations require new app approval.

Publication uses a dedicated application identity with reviewer access to one
space and no organization role. No reusable bearer is returned to users. Its
current key, grants, policy version and memory state are checked before pushing.
Revocation stops delivery; the app's explicit repair replaces that identity and
revokes old access. Retries never silently recreate revoked authority.

Pause stops automatic and manual pushes while local capture continues. An
important save cannot acknowledge Git delivery while publication is paused.
Unpublished withdrawn content is suppressed. A content-free deletion entry
permanently prevents journal replay from restoring that memory, even if files
arrive out of order or a later upsert claims to restore it. Quarantine hides a
memory until a later ordinary revision/release.

**Git commits, clones and backups retain already published text.** Deleting a
memory cannot erase those copies. A change immediately after the final pre-push
check also cannot retract bytes already sent. Do not enable this storage policy
for content that requires complete erasure from external history. Keep secrets
in the separate encrypted vault.

## Journal files and replay

Records are appended at `memory/buffer/YYYY-MM-DD/<writer-uuid>.jsonl`, with
`catalog.json` in the buffer root. Versioned records include the operation ID,
UTC timestamp, original organization/space/memory IDs, writer, memory version,
action, subject, important flag, text, kind and metadata. Denials contain no
text or metadata. Other repository paths are preserved; there is no working
checkout, hook execution or force-push. Concurrent remote commits trigger a
bounded refetch/retry. Truncation or disappearance of an already published
branch stops publication.

Use the existing Git, filesystem or file-based cloud adapter to import the
complete root. Include `*.json`, `*.jsonl`, **all dated files, the catalog and
`_archive`**. Establish source-reader bindings explicitly. The entire journal
inventory is checked before emitting any journal memory. Missing catalogs,
omitted denials, partial lines, unknown schemas and conflicting identities fail
the scan instead of becoming raw text memories. Unrelated documents use normal
ingestion. The catalog detects incomplete selection; it cannot authenticate a
malicious repository owner who rewrites both catalog and records.

Repeated records are deduplicated. Revisions retain a source identity derived
from their original organization/space/memory tuple. Moving intact files into
`_archive` preserves that identity. Push retries also check archived records;
late records append there without recreating the active file or double-counting.
Claimed writer IDs remain provenance and
never become local principals or grants. A fresh workspace assigns new internal
database IDs under its current source permissions; repeated imports into that
source are idempotent. This does not recreate the original writable space,
accounts, attachments or full database history. Use trusted current snapshots
and independent backups/denial ledgers for recovery.

## Monitoring, SDKs and agents

Studio shows the destination, interval, visible pending count/content bytes,
last confirmed commit and fixed error codes. Contributors see their own pending
events; reviewers see the space queue. **Push now** requires contributor access.
Configuration and repair require organization and space administration; stale
policy versions are rejected.

| Interface | Status | Configure | Push |
| --- | --- | --- | --- |
| HTTP | `GET /v1/spaces/{id}/writeback` | `PUT /v1/spaces/{id}/writeback` | `POST /v1/spaces/{id}/writeback/push` |
| Python | `journal_status(id)` | `configure_journal(id, command)` | `push_journal(id, expected_version=n)` |
| TypeScript | `journalStatus(id)` | `configureJournal(id, command)` | `pushJournal(id, version)` |
| Agent catalog | `journal.status` | `journal.configure` | `journal.push` |

Discover exact input schemas with [agent control](agent-control.md), through CLI
or MCP. Configuration requires literal `true` for `publish_to_repository` and
`acknowledge_retained_git_history`; repository content cannot grant consent.
Public status includes no local paths or Git credentials.

Publication defaults to 250 entries/8 MiB per batch, configurable up to 2,000
entries/32 MiB. Subprocesses have time/output bounds. The publisher lock is
separate from local capture. Replay uses a private disposable SQLite index with
a 2 MiB cache, bounded to one million physical records and 2 GiB of input;
duplicates consume the input budget. Files are capped at 20 MB, matching default
adapter limits. A full file or larger inventory fails visibly. Pending storage
can grow while Git is offline: monitor queue bytes/count and available disk.
Automatic sharding and representative large-history capacity remain open.

## Recovery and remaining work

Database recovery pauses publication and suppresses pending upserts for deleted
memories. Encrypted host packages retain the registry as an inspectable private
asset, but do not activate the old scanner, paths or environment variable.
Enroll a destination on the new host, establish its Git credential manager and
explicitly approve its policy in Studio before resuming the durable queue.

[Issue 39](https://github.com/Perseusxrltd/mnemion/issues/39) remains open for
scheduled librarian folding into official notes followed by intact archival,
complete app host enrollment, old-memory backfill, direct writable-space
reconstruction and large-history/live-provider acceptance. This batch delivers
capture, guarded publication, app/agent controls and source replay; it does not
replace complete workspace backups or independently hosted infrastructure.
