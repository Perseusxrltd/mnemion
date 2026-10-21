# Run memory sources from Studio

Studio 4.31.0 adds app-managed **folders/Obsidian vaults** and **growing JSONL
conversation folders** on Windows, macOS and Linux. The release passed all six
native targets and public installed-update checks. [Actual Windows/shared-host
updates also passed](../validation/2026-10-20-431-live-updates.md);
[release status](../RELEASE_STATUS.md) identifies current installers.

**Unreleased:** [retained conversation capture](durable-capture.md) adds an
explicit choice to keep selected, locally accepted evidence after chat logs
rotate or disappear. Existing sources keep their mirror policy. The new workflow
is not included in public 4.44.0 and still requires complete native and L1
acceptance.

The device can contribute to a local or remote shared workspace. Contributing
files does not require a local database, model, GPU, Python installation or
terminal. Embedding happens on the workspace under its existing model policy.

## Set up a source

From 4.41, live conversation folders also offer **What to remember**: retain
complete exposed session records or copy supported messages only. The same
`capture_mode: "complete" | "messages"` selection is available to agents.
See [capture choices and retention boundaries](live-conversations.md#choose-how-much-to-capture).

**Unreleased:** open **Session filters, JSON fields and sizes** and use
**Exclude JSON fields** for up to 32 literal ASCII field names, one per line,
before **Preview capture**. Approved exclusions remove
matching keys recursively before capture in both content modes. Producer files
remain untouched; the rule does not scrub strings or detect secrets in text.
See [field rules, refusal limits and policy v2](durable-capture.md#exclude-json-fields-unreleased).
Focused source, service, controller and migration checks and the Linux source
preview passed; all six packaged journeys remain pending. Existing retained
source selection still requires reviewed migration; changing rules does not
remove already accepted memories or backups.

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
   capture. The computer and source must be available; workspace delivery needs
   the network. Enrolled retained inboxes can accept locally while the workspace
   is offline. Quitting Studio completely stops the device's scans.

**Scan now** coalesces repeated requests. **Pause on this computer** persists the
pause and stops its active scan, retaining committed progress. **Resume** checks
current access again. Pause before changing settings or replacing a key. Save
again after changing the mapped audience. An existing entry cannot silently
switch folders, applications, providers or workspaces; use a separate connection
for a different source.

For retained capture in the unreleased source, pause remains available with a
missing or malformed enrollment record or altered protected inbox-key ciphertext,
provided the saved source configuration is still readable and valid. Change
only the enabled state; resume and other edits still validate the enrollment.
An unchanged damaged source does not block controls on another source. Pause
preserves the failure and accepted evidence without repairing or recreating
private files; follow the [pause and recovery boundaries](durable-capture.md#pause-remove-and-forget).

**Sources on this computer** appears under **Setup & this device** and on the
local setup screen before connecting. It lists saved sources across workspaces.
Pause and resume are available while signed out or when a workspace is offline.
Ordinary source settings can also be removed offline. Removing a retained inbox
requires confirmed server revocation before discarding local content; see
[pause, remove and forget](durable-capture.md#pause-remove-and-forget).
Changing sharing or credentials requires reconnecting and verifying the workspace.
Selecting another workspace does not stop unrelated sources.

Removing an ordinary source stops this computer's runner and removes its saved
key. Existing memories and server-side keys remain. Retained capture additionally
requires a pause and explicit consent to discard its entire local inbox,
including deliveries with unknown outcomes, after device-grant revocation is
confirmed. Administrators can disable the connection and revoke unused keys in
**People & apps**; other devices retain their independent settings.

For an unavailable retained-source key, **Connections** uses the current
administrator session when it matches that source's workspace. **Sources on
this computer → Device key unavailable?** also accepts an optional administrator
key for the displayed workspace. This credential is used only for removal and
is never saved by that operation. If retirement was already confirmed and saved
locally, interrupted cleanup can finish offline without a surviving credential.
See the [removal and recovery rules](durable-capture.md#pause-remove-and-forget).

## Reconnect an existing folder

The 4.42 repair lets Studio reuse a filesystem source first enrolled through an
existing adapter. Select that source's existing connection in **Connections**;
do not register a new source merely to resume the same folder. Stop its previous
runner, then use **Run on this computer** with the genuine folder or its restored
copy, the connection's dedicated application key and the intended mapped audience.
An empty or unrelated folder cannot replace unavailable source data: ordinary
complete-inventory removal rules still apply.

During enrollment and before each scan, Studio checks the connection's recorded
folder catalog. It automatically retains the one existing filesystem namespace,
preserving source and memory identity. A new connection keeps the default
namespace. Multiple recorded folders, an unrecognized catalog or an explicitly
mismatching identity stop before import; retain the original adapter configuration
and resolve the connection rather than guessing a different identity.

This does not wake a host, transfer another runner's credentials or restore
missing files. Provider access and mapped readers are revalidated through the
normal scan. The independent [office access acceptance](../validation/2026-10-20-office-access.md)
records actual provider revalidation and unchanged-client reads separately.

## Reconnect conversation capture

These reconnection steps apply to conversation mirrors. A retained inbox needs
its original verified private state and protected key, or a reviewed migration;
see [retained capture recovery](durable-capture.md#recovery-boundaries).

Use the existing connection and choose the original folder or its copied folder
with the same relative JSONL paths. Stop the previous runner before starting its
replacement. Sources created in Studio retain their default identity. For a
source first connected through a CLI adapter, open **Reconnect an existing
conversation source** and enter its original `provider.scope_id`.

Studio verifies the selected namespace against the existing file catalog before
importing. An unknown namespace, unmatched folder or incomplete copy stops before changing
the existing memories. First enrollment requires every original file still
present in the recorded catalog; files already recorded as absent do not prevent
reconnection. The verified private selection survives restarts, while
normal removal of files—including the final file—continues to work.

New capture checkpoints include a hash of their completed byte prefix. A copied
file can retain its original record identities after that prefix is verified,
even when its filesystem identity changes on another device. Older checkpoints
without this proof need a scan on the original file with this version before
making the replacement copy. If that original is unavailable, retain the
existing memories and source configuration; an unverified copy is refused.
See [validation](../validation/2026-10-20-conversation-identity.md).

## Capture and resources

Ordinary sources use the existing [connector protocol](connectors.md): complete
inventories govern removals; partial scans retain last good data; human corrections
produce review proposals. [Conversation mirrors](live-conversations.md) read
complete JSONL records, wait for unfinished tails and reuse captured fragments,
with one scope per file. They require a server at least 4.17.0. Retained capture
uses a separate approved inbox and custody protocol; producer disappearance
does not remove already accepted evidence.

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

The unreleased retained inbox adds [content and database limits](durable-capture.md#storage-and-resource-limits):
256 MiB pending per source by default (1–1,024 MiB selectable), 1 GiB pending
across the device, 512 MiB database admission per source and 2 GiB across the
device, plus at least 512 MiB free disk for new intake. Bounded delivery reserve
does not increase the allowance for new intake. Accepted evidence has no automatic
expiry; a limit below current usage blocks new intake without trimming the queue.

Remote agents' durable sync requests are picked up at the next scheduled scan.
Capture does not call a model on this device; the workspace may enqueue embedding
work. Ordinary source permission leases expire when successful checks stop.
Retained custody checks its current source, device grant and audience on delivery
and access; a saved inbox never authorizes delivery after revocation.

## Private storage, restart and recovery

The source key uses the OS credential facilities used for saved workspace
connections, with no plaintext fallback. It crosses the helper's private stdin,
never argv, environment, source files, reports or ordinary agent output. Settings
use owner-only native creation, including explicit Windows ownership/DACLs.
Selected source folders cannot overlap Mnemion's private app state. Known
credential files and generated mirrors retain the connector's safe exclusions.

Settings and conversation checkpoints belong to this computer; they are not a
cross-device backup or transfer of OS-protected keys. For ordinary mirrors,
enroll a replacement device with its own key and verified source identity. A
retained inbox also has an independent random 256-bit OS-sealed encryption key;
lost keys or initialized databases stop capture instead of creating an empty
replacement. Current chat files cannot reconstruct its accepted/forgotten history.
After pausing, preserve damaged files and restore only the verified matching
inbox, enrollment, settings and usable protected key. Pausing does not establish
recovery, and an unreadable or invalid saved source configuration cannot be
salvaged by the pause control. Resume and retirement retain their validation.
Follow [retained capture recovery](durable-capture.md#recovery-boundaries).
Recover authoritative server memory, permissions and deletion state from a
verified workspace backup; that cannot recover undelivered local content.

Updates wait for scans and settings writes. Once the updater pauses scheduling,
no new scan starts during shutdown. A cancelled update resumes scheduling; a
normal relaunch reads saved settings. A helper whose owning app disappears stops
instead of leaving an orphaned watcher.

## Local-agent controls

The same OS-account [private desktop interface](desktop-operator.md) exposes:

| Action | Input |
| --- | --- |
| `source.status` | None; returns the settings revision, sources, counts and RSS without keys. The unreleased capture report also separates local acceptance, pending content, server acknowledgements, unknown pages and incomplete scans. |
| `source.configure` | `expected_revision`, `source`, and `credential` for a new entry; an existing entry can keep its key. Cloud sources also use a separate `provider_credential`. |
| `source.pause` | `expected_revision`, `id`, `enabled` (`false` to pause, `true` to resume). The unreleased retained-source pause tolerates damaged enrollment with valid saved settings; resume retains validation. |
| `source.sync` | `expected_revision`, `id`; queues a scan of an enabled source. |
| `source.remove` | `expected_revision`, `id`, `confirm: true`. Retained capture also requires a paused source and `discard_local_inbox: true`; server revocation must be confirmed before local discard. Optional `retirement_credential` supplies current administrator authority through the private pipe and is never saved. Already recorded retirement permits cleanup offline without credentials. |
| `source.repair` (unreleased) | `expected_revision`, `id`, current `repair_token`, `confirm: true`; repairs scan observations for every source on this computer, preserving the damaged diagnostic file and retaining settings, keys, inboxes and checkpoints. |

These actions do not need a selected local workspace or `expected_workspace_id`.
They require the owning OS account's private pipe. Network MCP/memory credentials
do not authorize control of a computer. Read fresh status before changes; after
an uncertain reply, read status instead of replaying an old revision.

The `source` object accepts `id` for an existing entry, `endpoint`, `tenant_id`,
`connector_id`, `principal_id`, `name`, `provider` (`filesystem` or
`conversations`), absolute `path`, `members`, `publish_to_mapped_members: true`,
`poll_seconds`, `memory_limit_mib`, `max_files` and `enabled`. Conversations also
accept `capture_mode: "complete" | "messages"`. The unreleased retained workflow
adds `custody: {source_id, grant_id, keep_accepted: true, pending_limit_mib}` only
for a new conversation connection after independent server approval of its
source and exact device-key grant. Follow the [administrator and native setup](durable-capture.md#agent-and-administrator-setup)
before configuring it. Existing inbox identity, selection and dedicated key
cannot be replaced through an ordinary settings update.

The additional field-exclusion policy belongs in `source.capture_policy`, with
`format: "mnemion-capture-policy-v2"` and `exclude_fields`, matching the approved
device grant and a fresh preview. With no exclusions, existing v1 serialization
and fingerprints remain unchanged. The [headless policy example](headless-capture.md#exclude-json-fields-unreleased)
uses the same policy under `provider.capture_policy`.

Obtain identifiers from the actual workspace and registered connector. Supply
the dedicated key through private stdin. The desktop catalog describes
envelope/byte limits. Read current status after an uncertain reply; do not reset
an inbox or fabricate a successful scan to resolve missing observations.

For `filesystem`, the optional `scope_id` is the folder namespace without its
`filesystem:` prefix. Leave it absent to discover the one existing namespace.
For `conversations`, use the original adapter's `scope_id` for a custom identity;
hashed conversation IDs do not reveal that original value. Omit it for the normal
Studio default. The same verification and persistence apply to app and agent calls.
An existing custom namespace is retained in private settings and returned by
`source.status`; the ordinary `selected-source` default remains implicit.
When a recorded identity already exists, a supplied value must match it, and an
established saved identity cannot silently change. Cloud providers do not accept
this field.
Read current status before configuring a replacement; it is not a host-takeover
control or a substitute for access to the actual folder.

## Other providers

Source 4.34 adds [Slack and Google Drive setup](desktop-cloud-sources.md) using
existing approved provider credentials, explicit resource selection and actual
provider permissions. It shares this runner's offline and private-agent controls.

Git, rclone and custom adapters remain available through **Run on another
computer or use an advanced adapter** and their [guides](connectors.md).
A cloud client can expose ordinary readable files as the selected folder.
Provider-specific sign-in, virtual-placeholder hydration, organization ACL
translation and graphical enrollment for other adapters remain separate roadmap
work. This does not provide blanket access to every AI application's chat history.
