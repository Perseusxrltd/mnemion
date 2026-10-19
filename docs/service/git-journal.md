# Git journals for native memory

Source **4.15.0** adds optional publication of future native changes to a
host-approved Git destination. Ordinary saves return after a private local
journal is durable; important saves also require Git to acknowledge the push.
Check [release status](../RELEASE_STATUS.md) before requiring this version.
Source **4.16.0** adds optional scheduled filing into Markdown notes and intact
archival, with the same controls in Studio, HTTP, SDKs and the agent catalog.
Source **4.18.0** adds destination registration in the desktop app and its private
local agent interface.
Source **4.19.0** adds file rollover and an index of validated Git objects.
Source **4.20.0** adds pinned SSH deploy-key access and explicit local/network
destination types in receipts. The 4.18 native build was withheld; 4.19 includes
its guided setup with the desktop connection metadata correction.

An inbound Git connection does not enable publication. Existing memories, core
blocks, attachments, credentials and organization settings are not backfilled.
Use a [complete host recovery package](host-recovery.md) to preserve accounts,
grants, native database IDs and source settings. A journal protects published
memory text and provenance, with the recovery boundaries described below.

## Setup

### A workspace hosted by the desktop app

From 4.19.0, open the local workspace, choose its space and select **Git journal**.
An organization administrator with administrator access to that space sees
**Repository on this host** when connected directly to this computer's local
service. Remote workspaces use their own host's setup below.

1. Install Git for this OS account and sign in through its credential manager,
   or prepare the dedicated SSH files described below. SSH also requires OpenSSH.
   Use an existing repository with the required write access. The app detects
   whether the Git command can be found; that is not proof of authentication or
   repository permissions. Restart the app after installing Git.
2. Select **Register a repository**. Choose **HTTPS · Git credential manager**
   or **SSH · repository deploy key**. Enter its address without a password,
   token, query or fragment. For SSH, use `ssh://user@host/repository` and choose
   the private deploy-key and verified known-hosts files. The app stores their
   paths locally; it does not put the key contents in the registration or API.
   Choose the branch and an unused journal folder. The
   default folder is unique to the selected space and separate from old external
   buffers. Keep personal-data pattern checks enabled unless your policy calls
   for a different setting; recognizable-secret checks are always on.
3. Review and save the host registration. The app writes private settings and
   restarts its local service after a clean drain. Your workspace identity,
   existing memories and credentials are retained. Other clients briefly lose
   their connection during the restart.
4. When it returns, review **Enable this destination** below. Confirm publication
   and retained Git history, choose its schedule and save the space policy.
   Registering the host alone never enables publication or sends a Git request.

The app derives private queue paths and does not accept executable scanners or
custom Git/SSH commands through this form. Only the two selected SSH credential
file paths are accepted as optional local inputs. The primary organization of the local
workspace supplies the destination's tenant identity. Each space needs a distinct
repository folder. An already configured `MNEMION_WRITEBACK_CONFIG` is retained;
adopt app-managed configuration deliberately through the host operator.

**Change repository registration** retains private pending entries. Fresh space
approval is required when its destination fingerprint changes; pending changes
then use that destination. Published Git history is not migrated. **Remove
registration** keeps queue files and history, but journal-backed saves require a
valid approved destination to resume. Use the ordinary **Pause publication**
setting for a temporary publication pause. Repair preserves damaged registration
bytes before clearing the host's destination choices.

Git installation and credential provisioning are still separate prerequisites;
this feature creates no account or paid service. Local database recovery preserves
the queue in the database but does not recreate host registrations or Git sign-in.
Retain repository/branch/folder choices with your independent recovery references
and re-register them on the recovered host before approving publication.

### Other API hosts and operator-managed destinations

1. Install Git on the API host. Authenticate its **service OS account** through
   Git's credential manager, or use [pinned SSH access](#ssh-deploy-keys-and-host-pins),
   with write access to the selected repository. Use
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

Git installation and credential provisioning still require the service OS
account's operator. Hosts outside the app use the registration command above.
Ordinary memory API principals cannot choose arbitrary host paths, destinations
or scanner programs. No paid account or provider subscription is created.

`mnemion-service journal status --config /private/mnemion/journals/registry.json`
validates registrations and prints fingerprints. Enroll additional unique
destinations into the same registry. Replacing an existing registration requires
its current `--expected-fingerprint`; restart the API and approve the new policy
in Studio. Each space needs a separate state directory and repository prefix.
Changing a destination does not migrate previously published history.

### SSH deploy keys and host pins

From 4.20, an SSH destination requires an explicit `ssh://user@host/repository`
URL, its own private key and a verified known-hosts file. Optional ports are
supported. SCP-style `user@host:path`, passwords in URLs and custom SSH commands
are not accepted.

1. Create a deploy key for this repository and service OS account, for example
   `ssh-keygen -t ed25519 -N "" -f /private/mnemion/keys/journal-key`. Grant its
   **public** key write access in the repository provider. Keep the private key
   on the host and in an independently controlled encrypted recovery location.
2. Obtain the host's public SSH keys through its provider's authenticated
   documentation or the host administrator. Save the verified entries in a
   dedicated known-hosts file. For a nonstandard port, use entries in the form
   `[host]:port key-type public-key`. A network `ssh-keyscan` by itself does not
   verify the host's identity. Mnemion never automatically trusts an unknown key.
3. Both input files must be regular files owned by and readable only by the
   service OS account, without links. On Unix use mode `0600`; on Windows use an
   owner-only file ACL. Existing files are checked, not silently repaired.
4. Choose **SSH · repository deploy key** in the desktop form, or enroll through
   the same local operator command:

   ```sh
   mnemion-service journal enroll --config /private/mnemion/journals/registry.json --id office --label "Office memories" --tenant 11111111-1111-4111-8111-111111111111 --space 22222222-2222-4222-8222-222222222222 --state /private/mnemion/journals/office --remote ssh://git@git.example.com/team/memories.git --ssh-key-file /private/mnemion/keys/journal-key --ssh-known-hosts-file /private/mnemion/keys/known-hosts
   ```

   Configure the host environment/restart and approve space publication as above.
   Registration verifies bounded private-file access; **Push now** or an important
   save tests the actual Git connection and repository write permission.

SSH uses only the selected identity and host pins. It ignores inherited SSH
commands, SSH agents, user/system SSH configuration and global Git URL rewrites.
Password/passphrase prompts, forwarding, local SSH commands and multiplexed
connections are disabled. Unattended keys that need an interactive passphrase,
agent, hardware touch, proxy jump or company-specific SSH configuration need a
different provisioned transport; they are not silently bypassed.

Each network operation reads the existing files through checked handles and uses
temporary owner-only snapshots. This handles paths with spaces, Unicode, quotes
and percent signs without shell interpolation. Snapshots are removed after the
operation; an abrupt OS/process kill may leave a private staging directory under
the publisher's private control folder. Key contents never enter Git, the public
API or publication receipts. Keep the original key and host-pin files under
independent operator custody when moving/recovering a host; database backups do
not recreate those external credential files.

Key revocation, an unknown/changed host key and connection failure leave delivery
pending. Repair the credential or independently verify new host keys, then retry
the same event/idempotency key. File contents are reread on the next network
operation. Changing the registered file paths requires the current registration
fingerprint/revision and fresh space approval. Existing HTTPS/local registrations
retain their fingerprints when upgrading to SSH-capable versions.

### Adopting an older external journal

The prototype buffer in the issue 39 report used different fields and has no
native versioned catalog. It is not compatible with this journal format. Enroll
an unused prefix, for example `--prefix memory/native-buffer`, and retain the
old buffer and its remote commits independently. Native publication refuses an
occupied journal prefix without its valid catalog; it does not convert those
files or infer that they were acknowledged remotely.

A checked migration/reconciliation tool remains tracked: it must preserve the
original records, map identities explicitly, reconcile duplicate and withdrawn
memories, and verify the exact remotely published events/bytes. Do not mark all
current local file bytes as delivered after a push that sent an earlier snapshot.
Native receipts acknowledge selected event IDs, so a concurrently appended event
remains pending until its own confirmed publication.

## Save acknowledgments and failures

Use the normal HTTP/SDK/MCP save and revision commands. Add
`"metadata":{"important":true}` or select the app's important checkbox to
require immediate Git delivery. Preserve other metadata when revising it.

Receipts add `writeback.event_id`, `durability`, `remote_pending` and
`external_history_retained`. `local_journal` means the database and private
journal are durable locally. The compatibility name `remote_git` means the
**selected Git destination** acknowledged publication; that destination may be
a local bare repository. It does not acknowledge another replica or a complete
off-host backup. From 4.20, `writeback.destination_kind`, journal status and the
private publication receipt distinguish:

| Destination kind | What its Git acknowledgement covers |
| --- | --- |
| `local_repository` | The explicitly enrolled local bare repository only. A separate replication job needs its own remotely verified receipt. |
| `https_repository` | The repository reached through the enrolled HTTPS URL. Other replicas and storage durability are not independently verified. |
| `ssh_repository` | The repository reached through the enrolled SSH URL with its selected key and host pins. Other replicas are not independently verified. |

Older receipts can omit the kind; do not infer off-host protection from them.
Even a network URL can reach another service on the same physical host.
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

Pause stops automatic and manual pushes and filing while local capture continues. An
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

## File rollover and version compatibility

From 4.19.0, a daily writer file rolls over before an appended complete record
would exceed **20,000,000 bytes**. The original `<writer-uuid>.jsonl` stays intact;
continuations are `<writer-uuid>.part-000001.jsonl`, `.part-000002.jsonl`, and so
on in the same UTC day. Numbering is contiguous and shared across active/archive
locations. Retries inspect all parts for the exact event, so restarting the host
or losing a cache does not acknowledge unpublished content or duplicate records.
Late writes continue an archived series, with the same complete replay rules.

The first continuation atomically changes the catalog to **schema 2** with the
new files. Individual records keep schema 1. Upgrade **all publishers, filing
hosts and journal-reading source runners to 4.19 or later** before relying on
rollover. Older versions refuse schema 2 instead of omitting its parts. Ordinary
unsegmented journals retain catalog schema 1 until rollover is needed. Catalog
downgrade and missing numbered parts are refused; do not edit the catalog to
make an old publisher accept it. Upgrade a separately deployed service/runner
through its own operator; updating a desktop does not update that remote host.

A private `publisher-control/delivery-index.sqlite3` stores only validated object
IDs and event/version hashes. Immutable sealed objects are reused; a changed Git
object is parsed again. SQLite uses a 2 MiB page cache and file-backed temporary
storage. Loss of this disposable index triggers reconstruction from Git. Detected
SQLite damage refuses that attempt, removes only the damaged metadata cache, and
rebuilds on the next attempt; publication receipts and memory files are retained.
Missing Git history or unsafe linked state is not repaired by inventing records.

Each writer/day has at most 4,096 parts, and planning refuses more than one
million physical records or 2 GiB for that series. Batch limits still apply.
Complete filing/replay retains its whole-inventory limits below; these are
separate limits, so many individually valid days can still exceed that total.
Rollover removes the single daily-file stop, not every large-history limit.

The private `publication.json` receipt includes `append_planning.read_bytes`,
`written_bytes` and `rollover_files`, summed across attempted pushes. These count
JSONL object bytes and continuation files planned, including an attempt displaced
by another writer. They exclude Git network/compression, history comparisons,
catalogs and generated notes. They are not a measurement of total bandwidth.

## Automatic filing and archival

On a 4.16.0 or later server, open the space's **Git journal** settings and enable
**Automatically file readable notes and archive older journals**. Review the
displayed notes folder along with the repository. Filing is off by default;
upgrading an existing journal does not enable it. The default minimum age is
24 hours and the default interval is one hour. Organization/space administrators
can select 24–8,760 hours and a 60–86,400-second interval. Reviewers can also use
**Organize & archive now** after queued changes have reached Git.

For the default journal prefix, the librarian creates ordinary Markdown files
in `memory/buffer-mnemion-notes/<memory-uuid>.md`. They contain the current text,
title aliases and tags, the original identity/version, and a link to journal
history. Obsidian can open these alongside the rest of the repository. Stable
UUID filenames avoid renames when titles change. Edit the original memory in
Mnemion; these marked files are generated views. Unrelated repository files are
preserved. A conflicting filename or edited view stops filing for review.
Publishing a source change clears that view's body, including hand edits; its
previous version remains in Git history.

Filing uses the complete current journal projection, including archived records,
later revisions, permanent deletions and quarantines. It copies retained text
without asking a model to summarize it. Model-assisted titles, tags, summaries
and review remain available through the [configurable librarian](librarian.md);
those proposals retain their normal approval rules. Filing itself needs no
language model, GPU or paid provider.

After the required notes are ready, eligible dated files move intact into
`memory/buffer/_archive/YYYY-MM-DD/`. A whole UTC day is eligible only after its
end plus the configured minimum age; every record is therefore at least that
old. Original bytes and catalog counts are retained. If an active file reappears
beside an existing archive, its bytes are retained there too; duplicate logical
operations still replay once. Late writes append to the archive.

Newly published changes invalidate existing generated views in the same Git
commit. A deletion/quarantine removes text from that view; another revision marks
it pending until the next filing run. Generated notes are never imported as
independent memory, even with `include_generated` enabled or a damaged header in
the reserved notes folder. Connectors must continue reading the complete journal
and catalog. This protection does not erase old Git commits, exported copies or
files deliberately detached from their managed identity.

Upgrade journal writers to 4.16.0 for immediate view invalidation. Older 4.15
writers understand intact archive moves and can continue publishing within
schema-1 catalogs; their
changes appear in the views at the next 4.16 filing run. Generated notes live
outside the append-only journal folder for this compatibility. Database schema
migrations still require every API process sharing that database to be compatible.

Filing checks permissions and policy again before a fast-forward push. Queued
local changes block filing until published; a concurrent remote commit causes
complete reprojection before retrying. Changed settings, revoked access,
incomplete inventories and resource limits stop the run visibly. Database
recovery's publication pause also stops filing.

Each run changes at most the destination's note-count and byte budget and moves
at most that many journal files. Partial runs prepare notes without prematurely
moving history; remaining work is scheduled again after 60 seconds. Files are
read in bounded Git batches and projected through the existing 2 MiB SQLite
cache. The same one-million-record/2 GiB inventory limits apply, with up to
50,000 journal/view files and an 8 MiB tree listing. This is bounded processing,
not a measured large-company throughput guarantee. The 4.19 rollover above
handles the per-writer daily-file limit; larger complete inventories, backfill
and representative provider/fleet capacity remain roadmap work.

## Monitoring, SDKs and agents

Studio shows the destination, interval, visible pending count/content bytes,
last confirmed commit and fixed error codes. Contributors see their own pending
events; reviewers see the space queue. **Push now** requires contributor access.
Configuration and repair require organization and space administration; stale
policy versions are rejected.

From 4.16.0, status also exposes filing enablement/schedule, notes folder, last
confirmed filing commit/error, updated-note and archived-file counts, remaining
work, and bytes of journal content read/written. These byte counts describe data
processed, not compressed Git network traffic. Counts describe the last run;
they are not lifetime totals. The same values appear in the app.

| Interface | Status | Configure | Push | Organize (4.16+) |
| --- | --- | --- | --- | --- |
| HTTP | `GET /v1/spaces/{id}/writeback` | `PUT /v1/spaces/{id}/writeback` | `POST /v1/spaces/{id}/writeback/push` | `POST /v1/spaces/{id}/writeback/organize` |
| Python | `journal_status(id)` | `configure_journal(id, command)` | `push_journal(id, expected_version=n)` | `organize_journal(id, expected_version=n)` |
| TypeScript | `journalStatus(id)` | `configureJournal(id, command)` | `pushJournal(id, version)` | `organizeJournal(id, version)` |
| Agent catalog | `journal.status` | `journal.configure` | `journal.push` | `journal.organize` |

Discover exact input schemas with [agent control](agent-control.md), through CLI
or MCP. Configuration requires literal `true` for `publish_to_repository` and
`acknowledge_retained_git_history`; repository content cannot grant consent.
Public status includes no local paths or Git credentials.

From 4.18.0, the private desktop catalog adds `local.journal`. Read `status` and
`info.journal_access.revision` first, then submit the current selected host ID and
the same reviewed choices as the app:

```json
{
  "action": "local.journal",
  "expected_workspace_id": "11111111-1111-4111-8111-111111111111",
  "input": {
    "workspace_id": "11111111-1111-4111-8111-111111111111",
    "expected_revision": "not-configured",
    "action": "save",
    "destination": {
      "space_id": "22222222-2222-4222-8222-222222222222",
      "label": "Team memories",
      "remote": "https://git.example.com/team/memories.git",
      "branch": "main",
      "prefix": "memory/native-buffer/team",
      "personal_data_scan": true
    }
  }
}
```

Use `action: "remove"` with `space_id`, or `action: "reset"` only for damaged
settings, omitting `destination`. These operations run under the owning OS
account and use the same drain/reopen and stale-revision checks. Saving host
choices still requires separate `journal.configure` approval through an authorized
workspace administrator. Standalone host tools can send the `input` object on
private stdin to `mnemion-service local journal --root /private/local-workspace`
while that local service is stopped. Do not use another app user's directory.

Set `fold_enabled: true`, `fold_after_hours: 24` and
`fold_interval_seconds: 3600` in the existing versioned policy command to enable
filing. Omitting those fields preserves an existing filing policy, including
when using an older client. Send `fold_enabled: false` to disable future filing;
that does not delete generated notes or stop ordinary publication. Organize
requests contain the current `expected_version` and require reviewer access.

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
guided remote-host enrollment and provider sign-in, old-memory backfill, direct
writable-space reconstruction and large-history/live-provider acceptance. The
source now includes local app host registration, capture, guarded publication,
scheduled filing/archival, app/agent controls and source replay; it does not
replace complete workspace backups or independently hosted infrastructure.
