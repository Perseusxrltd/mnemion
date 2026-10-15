# Local desktop controls for agents

Introduced in the 4.6.0 source after the 4.5.0 backup/recovery batch.
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
| `local.create`, `local.start`, `local.stop` | Create, start or stop the app's local workspace through the ordinary lifecycle controls. |
| `local.memory` | Set automatic/manual RAM limits or repair a damaged RAM policy with its current repair token. |
| `local.port` | Change a stopped workspace's API port using its observed current port. |
| `local.remote`, `local.remote-check` | Configure or check the existing supervised remote-access options. |
| `local.preferences` | Set `start_with_app` for the selected workspace; OS login startup remains a separate app preference. |
| `backup.status`, `backup.key` | Read schedules/receipts or generate a new key into a private result file. Saved keys are never returned. |
| `backup.configure`, `backup.run`, `backup.cancel` | Configure protected schedules, capture a snapshot/ledger, or cancel an active recovery operation. |
| `backup.inspect`, `backup.restore` | Authenticate selected encrypted files and restore into a new managed private copy. |
| `recovery.list`, `recovery.use` | Discover verified copies, select one, or return to the original workspace. |

Native engine validators retain their bounds and requirements. See
[RAM controls](memory-resources.md), [local addresses](local-workspaces.md),
[remote access](remote-access.md) and [backups](native-backups.md) for the input
fields and their semantics. Unknown actions and input fields are refused.

For every workspace-bound action, include `expected_workspace_id` at the top
level using `status.result.info.settings.workspace_id`. Supply explicit `null`
when no workspace exists, such as initial creation or recovery on a new computer.
Refresh after switching copies. State-changing requests share the app's native
mutation guard, and a stale workspace identity is refused.
Creating, selecting or stopping the displayed workspace also checks for unsaved
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
Disconnecting cancels backup, inspection and restoration work owned by that
request, including private staging cleanup. A configuration save or lifecycle
operation may already have completed when its response is lost. Read current
status, revisions and receipts before retrying a change; the client does not
automatically resend mutations. Any authorized local operator can also submit
`backup.cancel` while another request is running. Automatic app updates wait
for local mutations; shutdown cancels/drains owned recovery work.

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
