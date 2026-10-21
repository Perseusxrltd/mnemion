# Headless retained conversation capture

**Unreleased development source.** The stable 4.44 release does not include this
mode. Use a matching development runner and workspace with
`durable_capture: "v1"` in `GET /health/live`. The [source checkpoint checks](../research/2026-10-21-durable-capture-implementation.md#headless-retained-capture-source-delta)
passed; all six packaged target journeys remain pending. This guide does not
close L1 or R07.

An explicit `capture` object makes `mnemion-connect` retain selected conversations
in an encrypted local inbox before attempting delivery. A configuration without
that object keeps its existing mirror behavior. Configuration alone never
enrolls, resumes or recreates a missing inbox. This runner operates independently
of Studio and its [private desktop controls](desktop-operator.md).

## Prepare the approved source and private files

Use the [administrator capture setup](durable-capture.md#agent-and-administrator-setup)
to create a new published `conversations` connector, approve its audience and
initial policy, and grant its dedicated non-administrator application
key custody. The runner verifies the exact tenant, principal, connector, source,
namespace, policy, audience and device grant. Initial enrollment refuses existing
mirror scopes or previous capture history; use recovery for an existing inbox.
It cannot approve its own grant or expand the audience.

Keep the configuration, state, keys and backups outside the selected conversation
tree. The source must be an ordinary directory; its identity is checked on later
scans. Private state and protected input files cannot be symlinks or junctions.
Use owner-only files and directories under the account running the connector.
Windows checks the actual owner and ACL; unsafe key files are refused rather
than having their permissions silently repaired.

Keys are references containing exactly one `file` or `env` field. The service
credential and independent 256-bit inbox encryption key are separate. A recovery
key protects portable archives. Headless capture reads protected files or the
explicitly named environment variables; it does not automatically seal keys in
an OS credential store. Provision service credentials through your existing
protected channel. The inbox key is a base64-encoded 32-byte random value;
the `key` control below generates it without printing it. Referenced values
must be nonempty printable ASCII and fit within 16 KiB. Do not put key values
in JSON, command arguments or logs.

Use the [locked source installation](../../README.md#development-and-support)
and run the examples from that development checkout. All paths, IDs and members
below are synthetic placeholders; replace them with your private locations and
the exact approved identities. Save this configuration as, for example,
`/private/headless-source.json`:

```json
{
  "version": 1,
  "service_url": "https://memory.example.invalid",
  "service_token": {"file": "keys/device-api.key"},
  "connector_id": "00000000-0000-4000-8000-000000000001",
  "provider": {
    "type": "conversations",
    "path": "/srv/selected-conversations",
    "state_directory": "provider-state",
    "scope_id": "selected-source",
    "name": "Selected conversations",
    "members": ["application:approved-assistant"],
    "publish_to_mapped_members": true,
    "normalize_conversations": true,
    "include_generated": false,
    "capture_mode": "messages",
    "capture_policy": {
      "format": "mnemion-capture-policy-v1",
      "preset": "conversation",
      "capture_mode": "messages",
      "include": ["*.jsonl"],
      "exclude": [],
      "retention": "until_deleted",
      "max_file_bytes": 1000000000,
      "max_record_bytes": 2000000
    },
    "max_files": 1000,
    "max_scan_seconds": 120,
    "segment_bytes": 256000,
    "segment_records": 256,
    "max_segments": 100000
  },
  "capture": {
    "id": "00000000-0000-4000-8000-000000000002",
    "tenant_id": "00000000-0000-4000-8000-000000000003",
    "principal_id": "00000000-0000-4000-8000-000000000004",
    "source_id": "00000000-0000-4000-8000-000000000005",
    "grant_id": "00000000-0000-4000-8000-000000000006",
    "keep_accepted": true,
    "state_directory": "capture-state",
    "inbox_key": {"file": "keys/inbox.key"},
    "pending_limit_mib": 256,
    "memory_limit_mib": 256
  },
  "poll_seconds": 300,
  "trigger_poll_seconds": 5,
  "remote_sync": false
}
```

`capture.id` is a new local device identifier. The other IDs come from the
approved server configuration. Relative paths in the configuration resolve beside
that file, including both key references, state directories and the producer
path. Remote service URLs require HTTPS; HTTP is allowed only on loopback.
Configuration input is limited to 1 MB.

An explicit policy must match the full policy returned by the device grant,
which can differ from the source's current default. Its include/exclude and
file/record limits supply the provider settings. Conversation selects supported
messages; Detailed uses `complete`; Selected permits either mode with relative
JSONL file patterns. Session filters select filenames, not records within a
file. See the [selection and capability limits](durable-capture.md#content-file-selection-and-retention).
Retained capture requires `until_deleted`, normalization enabled and generated
files excluded. Automatic expiry, field redaction, attachment fetching and
hidden reasoning remain unavailable.

Older mode-only `complete` or `messages` configurations can explicitly enroll
with `capture` only against a matching mode-only approved grant. They must keep
the default filename and file/record limits. Custom selection requires an
explicit policy; adding one to an existing inbox is a reviewed migration.
Changing enrolled identity, source path, selection, audience or credential
references also requires explicit recovery or re-enrollment. Runtime resource
limits and polling settings do not change the approved capture policy.

## Administrator policy changes (unreleased)

With `capture_policy_versions: "v1"`, administrators can manage source defaults,
policy history and device authorizations from Studio or the hosted workspace's
Connections page. The equivalent operations are `capture.source.list`,
`capture.policy.review`, `capture.policy.versions` and `capture.policy.change`;
use `mnemion_read`/`mnemion_write` with the standard parameters/body envelope, or
the matching HTTP routes in the [administrator procedure](durable-capture.md#manage-source-defaults-and-device-authorizations-unreleased).
These server controls are separate from `--capture-control` and do not read or
change this computer's files.

A reviewed default change applies to new grants. Existing grants are explicitly
retained on their original policies, including permission for new capture, or
all revoked. Keep the local configuration bound to its grant; copying the new
default into an existing inbox is not a migration. Revocation stops server
delivery and, when observed locally, future intake; it preserves offline inbox
evidence. The [policy checkpoint](../research/2026-10-21-durable-capture-implementation.md#capture-policy-versions-source-delta)
records the separate source, server recovery and browser administration checks.
They do not complete existing-device selection/organization migration or the
six packaged journeys. Known inactive authorizations remain
observable even after their retired source/connector metadata is hidden, so
that denial stops later intake without exposing the hidden metadata.

## Use the local control interface

Send one JSON object on stdin. The maximum request size is 64 KiB.
`--capture-control` cannot be combined with `--watch`, `--inspect` or
`--managed-state`:

```sh
uv run --locked mnemion-connect --config /private/headless-source.json \
  --capture-control <<'JSON'
{"action":"status"}
JSON
```

Successful controls return `{"ok":true,"result":...}` and exit 0. Errors return
bounded diagnostics and exit 2. Read `result.revision` before a mutation and use
it as `expected_revision`; an unenrolled source returns the literal
`not-enrolled`. A stale request is refused. Controls and scans share a local
lock: `workspace_busy` means wait for the current operation, then read status
again. Pause does not cancel a scan already holding that lock.

| Action | Additional request fields | Confirmation and effect |
| --- | --- | --- |
| `status` | None | Local enrollment and latest activity metadata; no credential read. |
| `preview` | None | Bounded local selection preview; no service request or model call. |
| `key` | `key_purpose`; also `recovery_key` for a recovery key | `confirm: true`; creates a new protected key file without printing its value. |
| `enroll` | `expected_revision`, `preview_hash` | `confirm: true`; verifies current server authority and creates a paused inbox. |
| `pause` | `expected_revision` | No confirmation field required; works without keys or network. |
| `resume` | `expected_revision` | `confirm: true`; verifies the existing inbox and current server authority. |
| `backup` | `expected_revision`, `archive`, `recovery_key` | `confirm: true`; exports a paused initialized inbox locally. |
| `inspect` | `archive`, `recovery_key` | Authenticates an archive locally without enrolling a source. |
| `restore` | `expected_revision`, `preview_hash`, `archive`, `archive_sha256`, `recovery_key`, `retirement_token` | `confirm: true`; replaces the old grant and creates a new paused device copy. |
| `finish` | `expected_revision`, `archive`, `archive_sha256`, `recovery_key` | `confirm: true`; explicitly completes a recorded recovery. |
| `discard` | `expected_revision`, `retirement_token` | `confirm: true`; revokes and discards an unfinished recovery copy only. |
| `retire` | `expected_revision`, `retirement_token` | `confirm: true`; retires the grant and disables this source, retaining its inbox. |

`archive` and credential file paths submitted in control requests must be
absolute. `recovery_key` and `retirement_token` use the same one-reference shape
as configuration keys, for example `{"file":"/private/keys/recovery.key"}` or
`{"env":"CAPTURE_RETIREMENT_KEY"}`. Keep these paths outside the producer tree
and working inbox. These are references, not values to copy into a transcript.

## Enroll paused, then resume explicitly

1. Read `status`. For a new device, expect `state: "not-enrolled"`.
2. Submit `{"action":"key","key_purpose":"inbox","confirm":true}` to create
   the file named by `capture.inbox_key`. It must not already exist. Generation
   requires a file reference; environment references must be provisioned separately.
   The result contains metadata and `key_printed: false`.
3. Submit `{"action":"preview"}`. Review its counts, relative paths and
   capability statuses. The sample covers at most eight files, 128 KiB per file,
   1 MiB total, 10,000 directory entries and a soft three-second budget. It
   returns no raw bodies, saves no captured content and invokes no model.
4. Copy `result.configuration_hash` into `preview_hash`, then submit the request
   below. The hash binds the reviewed configuration, not an immutable snapshot
   of the producer's changing files. Re-preview after changing settings.

```json
{
  "action": "enroll",
  "expected_revision": "not-enrolled",
  "preview_hash": "REPLACE_WITH_CONFIGURATION_HASH",
  "confirm": true
}
```

The expected result is `state: "ready", enabled: false`. Read its fresh revision
and explicitly resume:

```json
{
  "action": "resume",
  "expected_revision": "REPLACE_WITH_CURRENT_REVISION",
  "confirm": true
}
```

Enrollment and resume require a reachable workspace and the approved device
credential. A pending first enrollment can be retried with the same identity
and key, fresh revision and preview. Only that pending, never-used enrollment
may initialize an empty inbox. Missing initialized data, changed keys or a
changed binding stop capture; deleting state is not a recovery procedure.

To pause, submit `action: "pause"` with the fresh revision. Pausing prevents both
new scans and queued delivery. Observed grant revocation also disables subsequent
intake while retaining queued evidence. Resuming a revoked source still requires
current server authorization; retired or discarded devices cannot resume.

## Run scans and choose scheduling

Run one scan, or keep the process running:

```sh
uv run --locked mnemion-connect --config /private/headless-source.json
uv run --locked mnemion-connect --config /private/headless-source.json --watch
```

Each enabled scan commits selected complete input locally before reading the
service credential or opening its client. An unavailable workspace or service
credential therefore does not undo accepted local content. Missing producer
files can block new intake while the existing queue still delivers. Unfinished JSONL tails wait
for another scan. Anything deleted before local acceptance remains unavailable.

`--watch` reloads configuration and referenced key files for each scan. Normal
polling defaults to 300 seconds, configurable from 30 to 86,400. With
`remote_sync: true` (the default), it also polls for server **Sync now** requests
every `trigger_poll_seconds` (default 5, range 1–60). Local paused-to-resumed
state is checked between polls and can wake the watcher. Unavailable remote
control does not remove the normal scan schedule. `remote_sync: false` disables
remote triggers and control reporting; it does **not** disable queued delivery
or the current authorization checks needed to deliver.

The direct watcher uses its installed development runner until the operator
updates it. Keep one runner for the configured inbox and arrange process startup
and bounded log rotation through your existing process manager.

On an adopted Linux/macOS host, `--watch --managed-state /private/managed-service`
uses the [managed runtime](managed-connectors.md). In this development delta,
retained capture may scan while local service readiness is false. It still
holds the runtime/update leases, waits through update journals and cutovers,
and requires `capture_protocol: 1` from the verified runtime preflight. An older
runtime explicitly refuses retained capture. Mirror configurations keep their
service-readiness gate. This option selects an existing managed service; it
does not install a process manager, enroll a source or provide Windows managed
hosting. Stable 4.44 is not a capture-aware runtime.

## Read status and respect resource limits

`status` reports the persistent enrollment state, revision, `enabled`,
`configuration_matches`, `inbox_present`, limits, recovery metadata and latest
`activity`. It reads metadata without opening keys or decrypting the inbox.
These flags alone do not prove usable keys, current authority, an empty queue
or index readiness. Managed process/version observations remain separately
available through [managed runner status](managed-connectors.md#observe-the-runner).

The latest activity records a scan start before work begins. A saved `scanning`
attempt is reported as `interrupted` if the original process identity no longer
exists. This is an observation, not an automatic retry or a claim about how much
that process committed. Activity holds the latest attempt, not lifetime totals
or a separate history of previous successful scans.

After a finished scan, `activity.report.capture` separates locally accepted
events in that scan, current pending events/bytes, this delivery's committed
events, forgotten events, unknown pages, database usage and completion flags.
One event is a selected fragment, not necessarily one message. A process can
finish with `completed: false`; a one-shot exit 2 can still mean useful local
acceptance followed by deferred delivery or failed control reporting. Read the
report before retrying and never clear the inbox to turn an error into success.

Saved [prefix coverage](durable-capture.md#read-prefix-coverage), queue age and
authenticated contact/acknowledgement observations keep their separate meanings.
[Index observations](durable-capture.md#read-source-index-observations) cover the
authorized shared source across devices, under an observed generation and time
interval; partial sweeps do not replace a completed one. They are distinct from
this device's queue counts. Unknown history remains unknown. L2/L3 consolidation
is unavailable, and these observations invoke no model.

| Limit | Default and boundary |
| --- | --- |
| Process memory | `memory_limit_mib: 256`, configurable 128–2,048 MiB. RSS is checked before controls/scans and sampled once per second during them. Exceeding it stops the process; this is not an instantaneous peak-memory reservation. |
| Pending selected payload | `pending_limit_mib: 256`, configurable 1–1,024 MiB per inbox; 1 GiB across inboxes under the same capture state root. |
| SQLite admission | 512 MiB per inbox and 2 GiB across that root, measured using actual database pages. |
| Free disk | At least 512 MiB plus room for the intake transaction. |
| Enrollment records | At most 64 in the configured state root, including retained retired/discarded records. |
| Streaming work | Defaults shown above; file count allows 1–100,000 and the scan budget 1–600 seconds. Policy file/record caps remain separate. |

These aggregate limits apply to the configured root, not all independent roots
on the computer. Lowering a cap below current usage blocks new admission without
trimming evidence. Bounded delivery/forgetting bookkeeping can still proceed
subject to usable storage and authority. After a killed process, inspect status
and reuse the existing inbox and exact pending pages; SQLite recovery and later
delivery reconcile committed work. Do not generate a new key for that inbox.

The additional unreleased [free-page cleanup](durable-capture.md#reclaim-unused-database-pages-unreleased)
delta attempts reclamation before intake and after delivery. New inboxes use
incremental vacuum with a 64 MiB allowance and 0.5-second cooperative time budget
per pass. Older inboxes need whole-database conversion after all pending events
and delivery pages settle through confirmed storage or forgetting, with disk
reserve and the same cooperative time interruption; the 64 MiB allowance does
not cap that conversion.
`activity.report.capture.storage` reports final database/reclaimable page bytes,
bytes reclaimed across the scan's two passes and the final pass's bounded
state/reason. Older absent/null observations remain unknown. Cleanup preserves
every logical record and denial, introduces no expiry and does not relieve the
100,000-reference or 10,000-scope caps. Its focused source, controller and
migration checks passed separately from the earlier headless proof; all
installed-platform, release and full L1 acceptance remain open.

## Back up and inspect locally

Generate a separate recovery key into a new protected file:

```json
{
  "action": "key",
  "key_purpose": "recovery",
  "recovery_key": {"file": "/private/keys/recovery.key"},
  "confirm": true
}
```

Pause, read the fresh revision, then request `backup` with a new absolute archive
filename, the revision, recovery-key reference and `confirm: true`. It reads the
inbox key but needs no service credential or network. Existing output files are
refused. Keep the archive and recovery key separately protected.

`inspect` takes the archive and recovery-key reference. Its bounded receipt
includes `archive_sha256`, authenticated identity/policy and queue metadata;
`authenticated: true` proves that archive was read back successfully. Inspection
requires a valid capture configuration for private staging, but no original
enrollment, service credential value or original inbox key. It returns no secret
or body and does not enroll a source.

The encrypted archive preserves the original binding, pending evidence and exact
pages/receipts, checkpoints, forgetting fences and coverage, with the inbox key
inside its protected manifest. It contains no workspace API credential or
producer files. Server backups remain necessary for already delivered memory
bodies; this archive is not a complete workspace or historical transcript.

## Recover with a new device grant

Recovery changes the device grant and inbox key while keeping the original
organization, connector, source, namespace and capture policy. It does not
migrate selection or create a new origin to bypass forgetting.

1. Inspect the archive and retain its authenticated `archive_sha256`. Keep the
   archive and recovery key available through any interrupted recovery.
2. Have the administrator approve a replacement device key/grant for the same
   source. On a policy-version-aware server, explicitly supply the archive's
   original `previous_grant_id` and `confirm_previous_policy: true` to
   `capture.grant.configure`, alongside the new `device_key_id`. This preserves
   the exact old policy even after a default change; see
   [original-policy approval](durable-capture.md#approve-original-policy-recovery).
   Read the returned grant before configuring recovery. Create a new local
   device ID/configuration and unused inbox destination with that grant and the
   archive's unchanged selection. Generate a **new** inbox key; reusing the
   archive's key is refused. Supply the replacement service credential by
   protected reference.
3. Select the copied producer folder and preview its approved policy. Present
   captured prefixes must match; missing historical files are permitted but do
   not establish complete history. Keep the approved audience unchanged.
4. Provide a temporary `retirement_token` reference authorized to retire the
   original grant: its original device credential or current workspace
   administrator authority. It is not saved as the replacement service key.
5. Submit `restore` with the new device's `not-enrolled` revision, fresh preview
   hash, archive path/hash, recovery and retirement references, and explicit
   confirmation.

Restore authenticates and stages the copy, checks the destination, available
capacity and present producer prefixes before retiring the old grant. It also
verifies current replacement authority. Once retirement is confirmed it records
an explicit `recovering` intent before publishing the local copy. Success leaves
`state: "ready", enabled: false`; review status and resume explicitly. Current
server authorization, receipts and forgetting fences govern subsequent delivery.

After an uncertain response, read status before issuing another write. A
`recovering` record supports `finish` with its fresh revision, the same archive
hash, archive and recovery-key reference, and `confirm: true`. All archive fields
remain required by this control even if its local copy was already published.
The replacement inbox key and current service authority must still be usable.
There is no automatic replay, overwrite or empty-inbox fallback. If no local
intent was saved, reconcile the original and replacement grants with the
administrator before another attempt.

`discard` applies only to an unfinished recovery. With a fresh revision,
retirement reference and explicit confirmation, it revokes the replacement grant
before removing that unfinished inbox's database files. The archive, producer
files and key files remain; the old grant is not reactivated. A recorded discard
can finish cleanup after interruption without repeating completed revocation.

For an established device, `retire` disables it after confirmed grant revocation
and **keeps** its local inbox and keys. It is not a general erase command. Grant
retirement does not forget server memories or revoke the API key's ordinary
principal rights. Use the separate approved operations for those actions.

Source checks do not establish packaged acceptance. Broader identity/policy
migration, historical coverage, remaining policy capabilities, retained-history and
backpressure acceptance, and the complete six-platform packaged journey remain
open under the [L1 requirements](../research/2026-10-21-durable-capture-implementation.md#required-before-l1-can-be-released).
