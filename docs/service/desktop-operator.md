# Local desktop controls for agents

The base interface requires 4.6.0 or later. Retention configuration, inventory
and reviewed cleanup require 4.7.1 or later.
Check [release status](../RELEASE_STATUS.md) for the available installers and
native acceptance. This interface complements the shared workspace's
[agent API, CLI and MCP](agent-control.md).

Open **Setup & this device → Agents on this computer** and choose **Copy local
agent setup**. The same panel appears during local setup. Give the copied JSON
to a trusted agent running under your OS account on this computer. It contains
the installed engine command, discovery requests and the observed workspace ID,
with no credentials. The agent can work while the app is in the background or
the screen is locked; Mnemion Studio must still be running.

## Authority and discovery

Local controls use your OS account's authority over its app and local workspace.
They include host setup, RAM, addresses, backup keys and recovery. A memory key,
personal workspace login or organization administrator role does not confer this
authority on a remote agent. Company host delegation retains its separate access
requirements. Give ordinary collaborators scoped memory access instead.

The desktop creates a private Unix socket on macOS/Linux or named pipe on
Windows, with a fresh 256-bit credential for each app process. Its discovery
record is readable only by the owning account; Windows checks the actual file
owner and ACL. There is no network listener, browser endpoint or ngrok route for
these operations. Neither pipe addresses nor credentials belong in shared agent
configuration, memory content or source repositories. The command reads the
current private discovery record itself.

The command copied by the app is an executable plus an argument array. Invoke
that executable directly, pass arguments separately, and send one UTF-8 JSON
object on stdin. For a source installation the equivalent entry point is:

```sh
mnemion-service desktop-control
```

The bundled `mnemion-engine` has the same command. A source-only client can also
run `python -m mnemion.desktop_operator` without loading the service or a model.
Read the catalog first:

```json
{"action":"catalog"}
```

Then read the actual selected workspace:

```json
{"action":"status"}
```

Responses contain `protocol`, `session_id`, `request_id`, `ok` and either `result`
or an error. The catalog lists operation names, allowed input fields, whether
the selected workspace must be confirmed, and sensitive results.

The default discovery directory is `mnemion-desktop-control` under Local AppData
on Windows, `~/Library/Application Support` on macOS, or `$XDG_DATA_HOME`
(`~/.local/share` by default) on Linux. An isolated desktop profile uses its own
directory. Prefer the copied command, or specify `--control-directory` explicitly.
A WSL agent controlling the Windows app must invoke the **Windows bundled
engine** so it uses the Windows account and named-pipe implementation.

## Operations

| Action | Behavior |
| --- | --- |
| `status`, `catalog` | Read current native state or discover the supported interface. |
| `app.status`, `app.preferences` | From 4.19.0, inspect this app's version/update policy or change an observed app preference. No local workspace needs to be running. |
| `app.update-check`, `app.update-restart` | From 4.19.0, request an immediate ordinary update check or one guarded restart of the exact verified ready version. |
| `workspace.status`, `workspace.verify`, `workspace.inspect` | From 4.28.0, inspect the selected/saved accounts without secrets, verify a supplied key without connecting, or read a saved account's offline details. |
| `workspace.connect`, `workspace.sign-in`, `workspace.restore` | From 4.28.0, open an explicitly identified key connection, use a personal password login, or revalidate a saved account. |
| `workspace.disconnect`, `workspace.forget` | From 4.28.0, disconnect the selected account or remove one saved connection from this device. |
| `source.status`, `source.configure` | From 4.31.0, inspect or configure [desktop folder/conversation runners](desktop-sources.md#local-agent-controls) with protected dedicated keys and current settings revisions. From 4.34.0, [Slack/Drive selections](desktop-cloud-sources.md#private-agent-setup) accept a separate private provider credential. No local database is required. |
| `source.preview` | **Unreleased development:** inspect a bounded local JSONL selection without credentials, saved content or model calls. Explicit `capture_policy` configuration uses its matching preview hash; see below. |
| `source.backup` | **Unreleased development:** export a paused retained inbox to a new encrypted archive using a separate recovery key and the current source revision. |
| `source.backup.inspect` | **Unreleased development:** verify an archive offline and return bounded identity/policy/status information. Does not restore native enrollment or authorize delivery. |
| `source.pause`, `source.sync`, `source.remove` | Persistently pause/resume a source, queue a bounded scan, or stop and forget its local configuration. Independent of the selected workspace. |
| `agent.status`, `agent.preview` | From 4.32.0, inspect [native agent installations](desktop-agents.md), refresh their packaged runtime and preview a named MCP entry without changing client settings. No local database is required. |
| `agent.install`, `agent.remove` | Install a reviewed dedicated application connection or remove its matching local entry/key file, using the observed configuration hash and explicit confirmation. Other devices and server keys remain separately managed. |
| `local.create`, `local.start`, `local.stop` | Create, start or stop the app's local workspace through the ordinary lifecycle controls. |
| `local.open` | From 4.28.0, select the running local workspace using its independent local owner. Confirm both the local workspace ID and the current connection revision. |
| `local.memory` | Set automatic/manual RAM limits or repair a damaged RAM policy with its current repair token. |
| `local.port` | Change a stopped workspace's API port using its observed current port. |
| `local.remote`, `local.remote-check` | Configure or check the existing supervised remote-access options. |
| `local.company-discover`, `local.company` | From 4.11.0, review an OIDC provider or save/remove/repair the local host's company configuration, with current company and HTTPS revisions. |
| `local.vault`, `local.vault-key` | From 4.12.0, configure/restore the local encrypted vault or explicitly retrieve its host key into a private result file. Requires the current workspace and vault revision. |
| `local.models` | From 4.33.0, enroll/edit/remove embedding or librarian profiles and repair damaged private settings; confirms the current local workspace/revision and drains/restarts a running host. Keys stay on the host; per-space cloud approval remains separate. See [model setup](desktop-models.md). |
| `local.journal` | From 4.18.0, register/change/remove a local host's Git destination or repair its damaged registrations, with the current workspace and journal revision. From 4.20, SSH accepts `destination.ssh.identity_file` and `known_hosts_file` as private OS-account references. Space publication still needs separate administrator approval. |
| `local.preferences` | Set `start_with_app` for the selected workspace; OS login startup remains a separate app preference. |
| `backup.status`, `backup.key` | Read schedules/receipts or generate a new key into a private result file. Saved keys are never returned. |
| `backup.configure`, `backup.run`, `backup.cancel` | Configure protected schedules, capture a snapshot/ledger, or cancel an active recovery operation. |
| `backup.inventory`, `backup.prune` | From 4.7.1, review tracked files and apply the saved retention policy with explicit plan confirmation. The database may be stopped. |
| `backup.inspect`, `backup.restore` | Authenticate selected encrypted files and restore into a new managed private copy. From 4.30.2, [server-package database imports](desktop-host-recovery.md#local-agent-equivalent) also support an explicitly reviewed included or separate ledger. |
| `recovery.list`, `recovery.use` | Discover verified copies, select one, or return to the original workspace. |

Native engine validators retain their bounds and requirements. See
[RAM controls](memory-resources.md), [local addresses](local-workspaces.md),
[remote access](remote-access.md), [company setup](company-sign-in.md#agent-and-sdk-controls) and [backups](native-backups.md) for the input
fields and their semantics. [Vault controls](secrets-vault.md#agent-and-sdk-controls)
describe the separate encryption key and access switches; [journal controls](git-journal.md#monitoring-sdks-and-agents)
describe repository registration and separate publication approval. Unknown
actions and input fields are refused.

For every workspace-bound action, include `expected_workspace_id` at the top
level using `status.result.info.settings.workspace_id`. Supply explicit `null`
when no workspace exists, such as initial creation or recovery on a new computer.
Refresh after switching copies. State-changing requests share the app's native
mutation guard, and a stale workspace identity is refused.
Creating, selecting, stopping or changing company/vault/journal settings for the displayed workspace also checks for unsaved
app edits and pending requests. Save or discard edits before retrying a refused
change. During an accepted switch the app shows its progress, then reconnects
to the selected copy; it does not leave the previous workspace on screen.

For example, pause an existing backup schedule using its current revision and
destination from `backup.status`:

```json
{
  "action": "backup.configure",
  "expected_workspace_id": "WORKSPACE_UUID_FROM_STATUS",
  "input": {
    "expected_revision": "REVISION_FROM_BACKUP_STATUS",
    "destination": "ABSOLUTE_EXISTING_BACKUP_FOLDER",
    "enabled": false,
    "snapshot_hours": 24,
    "ledger_minutes": 15,
    "key_saved": true
  }
}
```

Setting `enabled` back to `true` resumes that protected schedule. A new
configuration also needs `recovery_key` and explicit `key_saved: true`; keep the
key outside the backup folder. Read fresh status before writing its revision.
Use `backup.run` with `{"ledger_only": true}` for a current deletion/access ledger.

In 4.7.1, `backup.configure` also accepts `retention`, for example
`{"mode":"limited","snapshots":7,"ledgers":96}`. Omitting this field preserves
an existing policy; old settings default to `keep_all`. Read `backup.inventory`
with the current `expected_workspace_id`. To clean up, submit `backup.prune`
with `expected_revision` from `backup.status.configuration`, `plan_token` from
that inventory and `confirm: true`. Neither operation requires a recovery key.
Plans are bound to the current recorded scope and policy; stale plans are refused.
See [retention safeguards](native-backups.md#retention-and-inventory-471)
for protected pairs, other keys, untracked copies and cloud deletion behavior.

Generate a key with `{"action":"backup.key"}` and **`--result-file NEW_PRIVATE_FILE`**.
The CLI requires this option for new keys and reserves the owner-only file before
requesting one. It never replaces an existing result file. Keep secrets on private
stdin, not command-line arguments, environment variables or routine logs.

For inspection use `source` and `recovery_key`. Restore uses `source`,
`ledger_source`, `recovery_key`, optional `ledger_key`, inspected `snapshot_sha256`
and `ledger_sha256`, `primary_tenant_id`, and `trusted_backup_confirmed: true`.
The app chooses a new private destination. Restore never selects or replaces the
current workspace automatically. Review its result, then call `recovery.use`
with `{"id":"VERIFIED_COPY_ID"}` and the current workspace identity. Use
`{"id":null}` to return to the original. The same current deletion/access rules,
fresh administrator credentials and external-connection review apply as in the UI.

## Select a team workspace from a local agent

Desktop **4.28.0** adds nine operations, bringing the private catalog to **39**.
They use the same connection manager and OS-protected credential store as the
app. No local model or local database is needed to join a remotely hosted team.
The app can remain in the background or behind the lock screen; a locked OS
credential store can still require the owning person to unlock it.

Read `workspace.status`. Its `revision` identifies the observed connection,
saved accounts and local selection. `active` reports the selected endpoint,
person and organization; `bookmarks` and `activeId` describe saved connections.
Neither result contains a real key, refresh token or native session handle.
These are local observations, not a fresh assertion of server permissions.
Use `workspace.inspect` with a bookmark `id` to read its dated offline access
and recovery information without contacting the host.

When using a supplied key, first verify it without changing the app:

```json
{"action":"workspace.verify","input":{"endpoint":"https://memory.example.com","credential":"KEY_FROM_PRIVATE_INPUT"}}
```

Review the returned `me.tenant_id`, `me.principal_id`, name and administrator
status. Then connect with both exact identities and the current connection
revision:

```json
{
  "action": "workspace.connect",
  "input": {
    "expected_revision": "REVISION_FROM_WORKSPACE_STATUS",
    "endpoint": "https://memory.example.com",
    "credential": "KEY_FROM_PRIVATE_INPUT",
    "remember": true,
    "expected_tenant_id": "TENANT_UUID_FROM_VERIFICATION",
    "expected_principal_id": "PERSON_UUID_FROM_VERIFICATION"
  }
}
```

The app rechecks the actual server identity before saving or selecting it.
A wrong organization/person, stale observation, unavailable host or unavailable
secure store cannot replace the prior connection. Set `remember: false` for a
temporary connection; there is no plaintext storage fallback. Supply secrets
through private stdin, never shell arguments, shared configuration or a memory.

For an existing personal login, use `workspace.sign-in` with `expected_revision`,
`endpoint`, `remember` and a `credentials` object containing `workspace_id`,
`username`, `password` and `device_name`. Password sessions require service 4.2
or later and retain their ordinary refresh and revocation rules. Creating the
person or accepting an invitation remains available through the existing
[personal-access app and private CLI](sign-in.md); these controls do not create
an account, invent a password or bypass company-provider sign-in.

Use `workspace.restore` with the current `expected_revision` and bookmark `id`
to reopen a saved account. It revalidates identity and, for personal logins,
refreshes the same device session. `workspace.disconnect` needs only the current
`expected_revision`. Key connections retain their encrypted bookmark; password
sign-out removes the saved refresh token and requests server revocation. If the
server cannot confirm sign-out, local access still closes and the command
explains the remaining revocation step. `workspace.forget` takes the same
revision and one `id`; it removes that device bookmark, without deleting
memories or revoking a server key.

To return to the running local host, read both `status` and `workspace.status`,
then call `local.open` with top-level `expected_workspace_id` and input
`expected_revision`. Starting a stopped local host remains `local.start`.
Connecting to a remote account does not stop the local host or change its
background-start preference.

Selection changes check for unsaved drafts and pending UI requests, serialize
with native mutations and refresh the displayed workspace after completion.
An accepted login may complete after the requesting client disconnects. Inspect
fresh status before retrying; the usual bounded request-ID replay applies.
These controls change the desktop selection, not an external agent's own
conversation context or scoped memory authority. Concurrent multi-workspace
sessions and delegated remote host control remain separate requirements.

## App updates and startup

From 4.19.0, the private catalog contains **30 operations**. App controls work
independently of a remote workspace or its originating agent. Use the copied
native engine command as above, with one request on stdin:

```json
{"action":"app.status"}
```

The result includes this desktop's version, OS/architecture, preferences,
administrator policy, distribution support, current bounded update status and
the verified `ready_version`, if any. Ordinary checks run shortly after startup
and then every **6–6¼ hours**, with bounded retries after failure. Automatic
restarts wait for ten minutes of computer inactivity, background/lock state,
saved work and clean completion of active operations. A release being available
does not mean every running installation has already checked or restarted.

From 4.40, `computer_idle_seconds` reports the operating system's current idle
time and `inactivity_remaining_seconds` reports the remaining part of the
ten-minute inactivity requirement. Both are `null` when the OS measurement is
unavailable. A zero remaining value satisfies only that requirement: unsaved
work, active transfers, focused use and administrator policy still apply.
These fields are observations, not a scheduled restart countdown. Continued
computer activity can keep a fully downloaded update waiting.

```json
{"action":"app.update-check"}
```

This requests the app's normal signature-verified check/download immediately.
It refuses paused, administrator-managed or unsupported updates. The app owns
an accepted download even if the requesting agent disconnects. Read `app.status`
for its result; `requested: true` is not proof of a download or installation.

To change a preference, supply its observed value. Allowed keys are
`automaticUpdates`, `startAtLogin` and `background`:

```json
{"action":"app.preferences","input":{"key":"background","expected_value":false,"enabled":true}}
```

Stale values are refused. Administrator-managed automatic updates cannot be
overridden. These app/OS-login preferences are distinct from the selected
workspace's `local.preferences.start_with_app`.

After a version is verified and ready, an authorized local agent can request a
single deliberate restart, substituting the actual `ready_version`:

```json
{"action":"app.update-restart","input":{"expected_version":"4.19.0","confirm":true}}
```

The request is acknowledged before a deferred restart attempt, so the operation
can release its local mutation guard. Like the app's **Restart now** action,
this deliberate request can proceed while the user is active; unsaved drafts,
in-flight work, service/database drain and signature checks remain mandatory.
If refused, it leaves no persistent override of background/inactivity policy.
Read status again; after a successful replacement use the newly published
private discovery record. An accepted request is not proof that installation
completed. These controls never restart or repair a separately hosted server.

## Timeouts, retries and recovery

Requests are limited to 16 KiB, responses to 256 KiB, with at most eight executing
requests. Oversized, unauthenticated or malformed frames cannot invoke a native
operation. The desktop never executes arbitrary commands supplied over this pipe.

An optional UUID `request_id` identifies an operation. Within the same desktop
session, completed replies are retained for up to ten minutes, 64 entries and
2 MiB. An identical retained request returns its original result; changing its
input with the same ID is refused. Repeating an in-flight ID does not start it
twice. These bounded replies are not a durable job journal and do not promise
replay after eviction or app restart.

The CLI waits 30 minutes by default; `--timeout` accepts 1–14400 seconds.
Disconnecting cancels backup, cleanup, inspection and restoration work owned by that
request, including private staging cleanup. A configuration save or lifecycle
operation may already have completed when its response is lost. Read current
status, revisions and receipts before retrying a change; the client does not
automatically resend mutations. Any authorized local operator can also submit
`backup.cancel` while another request is running. Automatic app updates wait
for local mutations; shutdown cancels/drains owned recovery work.
Completed cleanup removals cannot be undone by disconnecting; read the latest
cleanup result and fresh inventory before retrying.

After an app restart, rediscover its current pipe. A dead process's endpoint is
replaced on startup; a second live process cannot overwrite its discovery record.
Unavailable or unsafe discovery produces a local-control error, without falling
back to a network URL or printing credentials. If the app reports a private
control failure, first close extra app instances and use the copied path for
this profile. An agent can still use the documented standalone local engine
commands under the owning OS account.

This interface does not start a powered-off computer, grant SSH/cloud-console
access, establish company recovery custodians, verify cloud backup delivery or
fence another host. Those remain part of
[workspace continuity](../implementation/workspace-continuity.md).

## Preview conversation capture (unreleased)

This addition remains unreleased. [Source validation](../research/2026-10-21-durable-capture-implementation.md#capture-policy-and-preview-source-delta)
records component checks, a Linux source journey and separate recovery/migration
proof; installed acceptance and full L1 remain open. The app's **Preview capture**
and native `source.preview` use the same selection object.
Read the installed `catalog` before using this action; no selected local
workspace or workspace credential is needed for preview. Use a folder path
absolute in the app's operating system:

```json
{
  "action": "source.preview",
  "input": {
    "selection": {
      "path": "/absolute/conversation-folder",
      "capture_mode": "messages",
      "capture_policy": {
        "format": "mnemion-capture-policy-v1",
        "preset": "selected",
        "capture_mode": "messages",
        "include": ["team/*.jsonl"],
        "exclude": ["team/private/*.jsonl"],
        "retention": "until_deleted",
        "max_file_bytes": 1000000000,
        "max_record_bytes": 2000000
      },
      "keep_accepted": true,
      "memory_limit_mib": 256,
      "max_files": 10000,
      "pending_limit_mib": 256
    }
  }
}
```

`selected` permits either content mode; `conversation` requires `messages` and
`detailed` requires `complete`. Include/exclude patterns select relative JSONL
filenames, not session IDs or fields within a file. They are case-sensitive;
`*` can match subfolders and built-in private-file exclusions always apply.
`source_mirror` pairs with `keep_accepted: false`; `until_deleted` pairs with
`true` and requires approved custody when configuring the source. Pause remains
the separate `source.pause` action.

The result contains relative paths, per-file outcomes, complete-line counts,
`configuration_hash`, optional `policy_revision` and capability statuses. It
returns no raw body and saves no source content. Limits are eight matching files,
128 KiB per file, 1 MiB total, 10,000 directory entries and a three-second soft
deadline. `catalog: complete` describes finished traversal of that sample, not
complete transcript coverage. Inspect the [preview limits and unsupported
capabilities](durable-capture.md#preview-the-selection) before reporting coverage.

For a source with an explicit `capture_policy`, pass
`result.configuration_hash` as `input.preview_hash` in `source.configure`, with
the same selection/resource settings in `input.source` and a fresh
`expected_revision` from `source.status`. Changing the normalized folder, content
policy, retention, RAM, file-count or pending-content choice requires a new
preview. This hash binds settings, not file contents; it does not replace
server consent, current authorization or capture-time verification.

The app and agent use the same configuration path. Retained enrollment requires
the exact administrator-approved policy and device grant. Each fragment under
an explicit policy carries a policy fingerprint checked locally and by the
service. A retained policy cannot be edited in place; changing it requires
reviewed migration. Older sources without `capture_policy` retain their
`complete`/`messages` mode-only behavior and do not require the new preview hash.
Automatic expiry, field redaction, attachment fetching and hidden reasoning are
unavailable. See the [capture guide](durable-capture.md) for retention, size and
recovery limits. This addition does not complete L1 or installed acceptance.

## Capture inbox archives (unreleased)

The app's **Sources on this computer** export/verify controls and these actions
share the same archive implementation. Core, helper and controller checks and
local builds passed; the Electron export/restart-inspection journey and packaged
acceptance remain pending. See the [current proof](../research/2026-10-21-durable-capture-implementation.md#portable-inbox-archive-source-delta).
Read the installed catalog before use. Neither action needs a selected workspace
or a workspace API credential, and neither invokes a model.

For export, pause the retained source, wait for active scans to finish and read
fresh `source.status`. Use the existing `backup.key` private-result-file flow to
generate a recovery key, and keep it separately from the archive. Export needs
the source's OS-protected inbox key; the native controller unseals it internally.
Supply a new absolute output filename and the observed source ID/revision:

```json
{
  "action": "source.backup",
  "input": {
    "expected_revision": "REVISION_FROM_SOURCE_STATUS",
    "id": "SOURCE_UUID_FROM_STATUS",
    "file": "/absolute/new-capture-archive",
    "recovery_key": "RECOVERY_KEY_FROM_PRIVATE_STORAGE",
    "confirm": true
  }
}
```

Inspection needs only the archive and its recovery key. It remains available
when the original source settings or OS-sealed inbox key are unavailable:

```json
{
  "action": "source.backup.inspect",
  "input": {
    "file": "/absolute/existing-capture-archive",
    "recovery_key": "RECOVERY_KEY_FROM_PRIVATE_STORAGE"
  }
}
```

The result includes `archive_sha256`, the original binding/policy, creation time,
database size and archived status counts. `authenticated: true` confirms archive
verification; `workspace_credentials_included` and `source_enrolled` are both
false. Raw messages and encryption keys are not returned. After an uncertain
export, inspect that file before retrying; the exporter refuses an existing
output filename.

The archive preserves pending evidence, pages, checkpoints, forgetting fences
and coverage, with the inbox key protected inside its encrypted manifest. It
contains no workspace API credential. These native actions provide export and
inspection only. The separate library restore creates a new private inbox under
the original binding; it does not enroll or activate a device. Native restore,
key resealing, current-grant verification and reviewed device/policy migration
remain unfinished. See [recovery boundaries](durable-capture.md#recovery-boundaries).
