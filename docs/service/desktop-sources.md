# Run memory sources from Studio

Studio 4.31.0 adds app-managed **folders/Obsidian vaults** and **growing JSONL
conversation folders** on Windows, macOS and Linux. The release passed all six
native targets and public installed-update checks. [Actual Windows/shared-host
updates also passed](../validation/2026-10-20-431-live-updates.md);
[release status](../RELEASE_STATUS.md) identifies current installers.

The device can contribute to a local or remote shared workspace. Contributing
files does not require a local database, model, GPU, Python installation or
terminal. Embedding happens on the workspace under its existing model policy.

## Set up a source

1. Connect to the intended workspace. An administrator creates a dedicated
   application in **People & apps**, then registers its folder or conversation
   connection in **Connections**. Each source uses its own application.
2. Under **Who can use this source?**, map source identities to the people and
   agents who should receive access. Folder sharing permissions are not
   translated automatically. With no mapped audience, only the connector
   identity can read the imported source.
3. In **Run on this computer**, select the actual folder. Review the scan
   interval, RAM allowance, file limit and mapped audience. An administrator can
   leave the key blank to create a dedicated application key automatically;
   another operator supplies that application's key. An administrator's own key
   is refused as a background source credential.
4. Confirm the audience and select **Save and start scanning**. Studio checks
   the workspace, application and connector identities before saving the key
   with OS protection. Counts and failures also appear in **Source status**.
5. Keep **Run in background** and **Start at login** enabled for unattended
   capture. The computer, source and network must be available. Quitting Studio
   completely stops the device's scans.

**Scan now** coalesces repeated requests. **Pause on this computer** persists the
pause and stops its active scan, retaining committed progress. **Resume** checks
current access again. Pause before changing settings or replacing a key. Save
again after changing the mapped audience. An existing entry cannot silently
switch folders, applications, providers or workspaces; use a separate connection
for a different source.

**Sources on this computer** appears under **Setup & this device** and on the
local setup screen before connecting. It lists saved sources across workspaces.
Pause, resume and removal work while signed out or when a workspace is offline.
Changing sharing or credentials requires reconnecting and verifying the
workspace. Selecting another workspace does not stop unrelated sources.

Removing a source stops this computer's runner and removes its saved key.
Existing memories and server-side keys remain. Administrators can disable the
connection and revoke unused keys in **People & apps**; other devices retain
their independent settings.

## Capture and resources

The runner uses the existing [connector protocol](connectors.md): complete
inventories govern removals; partial scans retain last good data; human
corrections produce review proposals. [Conversation capture](live-conversations.md)
reads complete JSONL records, waits for unfinished tails and reuses captured
fragments, with one scope per file. It requires a server at least 4.17.0.

Only one source scans at a time, with one pending request per source. The helper
reports resident memory every two seconds and stops when it exceeds its RAM
allowance. Committed progress is reconciled on the next scan. This is sampled
enforcement, not protection against every brief allocation spike. Source RSS is
included in a local workspace's desktop-memory accounting; the server's model
and database budgets remain separate.

| Setting | Default | Range |
| --- | --- | --- |
| Saved sources per app profile | — | Up to 16 |
| Scan interval | 5 minutes | 30 seconds–60 minutes |
| Source RAM | 256 MiB | 128–2,048 MiB |
| Files per scan | 10,000 | 1–100,000 |
| Ordinary text file size | At most 20 MB | Also bounded by RAM allowance |
| Process deadline | 10 minutes | Stops and retains committed progress |

Remote agents' durable sync requests are picked up at the next scheduled scan.
Capture does not call a model on this device; the workspace may enqueue
embedding work. Pausing a device does not certify access indefinitely: the normal
permission lease expires when successful checks stop.

## Private storage, restart and recovery

The source key uses the OS credential facilities used for saved workspace
connections, with no plaintext fallback. It crosses the helper's private stdin,
never argv, environment, source files, reports or ordinary agent output. Settings
use owner-only native creation, including explicit Windows ownership/DACLs.
Selected source folders cannot overlap Mnemion's private app state. Known
credential files and generated mirrors retain the connector's safe exclusions.

Settings and conversation checkpoints belong to this computer; they are not a
cross-device backup or transfer of OS-protected keys. Enroll a replacement device
with its own key and the intended source identity. Recover authoritative memory,
permissions and deletion state from a verified workspace backup.

Updates wait for scans and settings writes. Once the updater pauses scheduling,
no new scan starts during shutdown. A cancelled update resumes scheduling; a
normal relaunch reads saved settings. A helper whose owning app disappears stops
instead of leaving an orphaned watcher.

## Local-agent controls

The same OS-account [private desktop interface](desktop-operator.md) exposes:

| Action | Input |
| --- | --- |
| `source.status` | None; returns the settings revision, sources, counts and RSS without keys. |
| `source.configure` | `expected_revision`, `source`, and `credential` for a new entry; an existing entry can keep its key. |
| `source.pause` | `expected_revision`, `id`, `enabled` (`false` to pause, `true` to resume). |
| `source.sync` | `expected_revision`, `id`; queues a scan of an enabled source. |
| `source.remove` | `expected_revision`, `id`, `confirm: true`. |

These actions do not need a selected local workspace or `expected_workspace_id`.
They require the owning OS account's private pipe. Network MCP/memory credentials
do not authorize control of a computer. Read fresh status before changes; after
an uncertain reply, read status instead of replaying an old revision.

The `source` object accepts `id` for an existing entry, `endpoint`, `tenant_id`,
`connector_id`, `principal_id`, `name`, `provider` (`filesystem` or
`conversations`), absolute `path`, `members`, `publish_to_mapped_members: true`,
`poll_seconds`, `memory_limit_mib`, `max_files` and `enabled`. Obtain identifiers
from the actual workspace and registered connector. Supply the dedicated key
through private stdin. The desktop catalog describes envelope/byte limits.

## Other providers

Git, Drive, Slack, rclone and custom adapters remain available through **Run on
another computer or use an advanced adapter** and their [guides](connectors.md).
A cloud client can expose ordinary readable files as the selected folder.
Provider-specific sign-in, virtual-placeholder hydration, organization ACL
translation and graphical enrollment for other adapters remain separate roadmap
work. This does not provide blanket access to every AI application's chat history.
