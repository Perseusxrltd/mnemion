# Keep selected conversations after chat logs disappear

**Unreleased implementation.** This guide describes the current development
source. Check [release status](../RELEASE_STATUS.md) for published availability.
Both Studio and the workspace server must support retained capture; the server
advertises `durable_capture: "v1"` in `GET /health/live`. This work advances L1
of the [layered librarian](../research/2026-10-20-layered-librarian.md); full L1
and R07 acceptance remain open.

Retained capture commits the selected conversation items to an encrypted local
inbox before making any service request in a scan. Once accepted locally, those
items can still be delivered after the original JSONL file rotates or disappears.
Delivery checks the workspace's current authorization and forgetting decisions.

## Choose retention before enrollment

Use [desktop source setup](desktop-sources.md#set-up-a-source) with a **new
conversation connection**, its own non-administrator application and an explicitly
mapped audience. Existing conversation mirrors keep their existing inventory and
removal policy. Changing a mirror into retained capture requires a reviewed
migration; this guide does not provide that migration.

Map yourself too if you need to read the captured memories. Organization
administration alone does not grant access to a source's content. With no mapped
people or agents, only the dedicated source application can read its copies.

1. In **Connections → Run on this computer**, choose the conversation folder.
2. Choose **What to remember**: **Conversation** for supported user and assistant
   messages, **Detailed** for messages and exposed session events, or **Selected**
   to choose filename patterns and either content mode. Review the controls below.
3. As a workspace administrator, select **Keep captured memories when original
   chat logs rotate or are removed**. Review the audience and the pending content
   limit. The approved policy is fixed for this inbox: changing its selection,
   file/record size rules, identity or dedicated key requires a reviewed migration.
4. Review **Session filters and capture sizes**, source RAM, maximum files and
   pending-content limits, then select **Preview capture**. Review its bounded
   sample and unavailable capabilities. Changing these choices requires a new preview.
5. Leave the application key empty to have Studio create a dedicated key, or
   supply the existing dedicated key **and its key ID**. The key ID binds the
   device grant; it is separate from the inbox's encryption key.
6. Confirm publication to the mapped identities and select **Save and start
   scanning**. Studio first configures the server's retention policy and device
   grant, then verifies and saves the local enrollment with OS-protected keys.

Initial enrollment requires a reachable workspace. After enrollment, Studio can
accept available complete records while the workspace is offline, within the
local limits below. Keep Studio running, with **Run in background** and **Start
at login** enabled for unattended scans. Quitting the app stops its runner.

The inbox contains only the approved capture selection. In `messages` mode,
raw tool and reasoning records remain in the producer files; they are not hidden
inside the inbox's source evidence. Unfinished JSONL tails wait for a later scan.
Material removed before a successful local commit cannot be recovered by this
feature. A completed scan covers the available input; it does not prove that
every historical conversation was captured.

### Content, file selection and retention

These controls remain **unreleased**. The [recorded source validation](../research/2026-10-21-durable-capture-implementation.md#capture-policy-and-preview-source-delta)
covers component checks, a Linux source journey and separate recovery/migration
checks; six packaged targets and complete L1 acceptance remain open. The app and
[local agent interface](desktop-operator.md#preview-conversation-capture-unreleased)
use the same `capture_policy` and configuration checks.

| Choice | Current behavior |
| --- | --- |
| Conversation | `messages`: copies supported user and assistant message text. Unknown formats produce no message copy. |
| Detailed | `complete`: also retains the selected producer's complete records, including tool activity and reasoning traces actually exposed in its files. |
| Selected | Chooses relative JSONL filename patterns and either `messages` or `complete` content. |
| Pause | Uses the existing source pause control; it does not rewrite the approved policy. |

Session selection currently means **file selection**, using relative paths such
as `team/*.jsonl` and exclusions such as `team/private/*.jsonl`. It does not select
session IDs, messages or individual fields inside a file. Patterns are
case-sensitive, use forward slashes, and `*` can match subfolders. The default
include is `*.jsonl`; new matching files become eligible automatically. Each
include/exclude list allows up to 64 distinct patterns of at most 512 characters.
Absolute paths, parent traversal and backslashes are refused in these patterns.
Filename rules apply to all three presets; built-in private-file exclusions
remain in force.

`source_mirror` uses the existing source reconciliation/removal behavior.
`until_deleted` requires retained custody and keeps accepted selection after
producer rotation/removal, subject to explicit forgetting and current access
decisions. Automatic expiry, field redaction, attachment-binary fetching and
hidden provider reasoning are unavailable. Exposed attachment descriptions or
links may still be ordinary selected text; links are not followed.

File and record caps default to **1,000 MB per file** and **2,000 KB per complete
input record**. The policy permits up to 1 TB per file and 16 MB per record, with
the record cap no larger than the file cap; these use decimal bytes. The existing
RAM, files-per-scan, pending-content and database limits remain separate.

For an explicit policy, accepted fragments carry its `capture_policy_revision`
fingerprint. The local inbox and service check the approved fingerprint, content
mode and relative path; the collector enforces the file/record limits. Retained
policy changes require reviewed migration. Older `complete`/`messages`
configurations without `capture_policy` keep their mode-only behavior and existing
fragments; an old retained inbox is not silently given a new policy or revision.

### Preview the selection

Preview is local and returns relative filenames, per-file outcomes, complete-line
selection counts, configuration/policy fingerprints and capability statuses.
It saves no source content, returns no raw body, requires no workspace credential
and invokes no model. Enrollment still verifies server capability, consent and
the dedicated device grant separately.

The preview considers at most **8 matching files**, reads at most **128 KiB per
file and 1 MiB in total**, visits at most **10,000 directory entries**, and uses
a **3-second soft deadline** checked between entries. The configured file-count
limit can reduce the sample further. A filesystem operation can outlast that
soft deadline. Only complete newline-terminated records in sampled prefixes
contribute to counts; duplicates and later context are reconciled during capture.

`catalog: complete` means directory traversal finished within these bounds, not
that every file body was examined. `limited` marks a traversal/sample limit and
`unavailable` marks an observed access problem. Per-file outcomes distinguish
sampled prefixes, changed/unreadable files, size limits, private control data and
invalid JSONL. A preview with no sampled records does not prove an empty history.

Saving an explicit policy requires its matching `configuration_hash` as native
`preview_hash`. It binds normalized folder and selection/resource settings, not
file contents or future changes. A preview is not a local acceptance receipt;
normal capture rechecks the source before committing selected evidence.

## Read capture and delivery status

**Run on this computer** and **Sources on this computer** show the last saved
capture observation. The native `source.status` action returns the same values
in `activity.report.capture`.

| Observation | Meaning |
| --- | --- |
| `locally_accepted` | Selected events committed locally during the reported scan. These are events/fragments, not a count of conversations or messages. |
| `pending_events`, `pending_bytes` | Locally accepted content still awaiting a confirmed server outcome. Pending content has no automatic expiry. |
| `stored_events` | Events acknowledged as stored by the workspace. |
| `forgotten_events` | Events covered by the workspace's current forgetting decisions. |
| `remote_committed_events` | Delivery acknowledgements received during the reported scan, including `stored` and `forgotten` outcomes. |
| `unknown_pages` | Saved delivery pages awaiting reconciliation. A lost reply does not prove failure or authorize a different page. |
| `capture_complete`, `reason_code` | Whether that local scan finished and any observed source, capacity, integrity or authorization problem. An incomplete scan can leave earlier accepted evidence available. |
| `delivery_complete` | The observed pending queue and current forgetting sweep finished without a delivery error. |
| `database_bytes`, `device_database_bytes`, `device_pending_bytes`, `over_limit` | Local storage observations and whether the inbox exceeds an admission limit. |
| `coverage` | Encrypted prefix accounting, history uncertainty, queue/contact observations and saved source index observations, described below. |

Delivery reuses each saved page's exact identity and body. After an uncertain
reply, the runner looks up the receipt before resending the same page. It applies
current forgetting fences and checks the source, device key, grant and audience
again at server commit. A revoked grant cannot deliver queued evidence. Once
revocation is observed locally, further intake under that enrollment stops.

Local acceptance, server acknowledgement, indexing readiness and librarian work
are separate stages. An empty queue or successful HTTP reply does not establish
semantic-search readiness or completed librarian processing. Saved scan history
also reports the last success, failure or interrupted attempt; an unknown or
unsaved observation must remain unknown in an agent's report.

### Read prefix coverage

The prefix fields in `activity.report.capture.coverage` describe the last accepted
prefixes of tracked producer files where accounting is known. Each file's latest
counters replace its previous contribution; they are **not lifetime totals** or
counts of unique conversations, messages or retained fragments. Missing files
keep their last known observations. The coverage record is encrypted in the
inbox, and accepted-prefix accounting commits with the selected items and
verified checkpoint.

In the app, expand **Capture coverage and history** to view these observations.
Interpret selection using the saved `capture_mode`. `records.lines` counts
complete, newline-terminated input lines in the accounted prefixes and equals
`records.selected + records.omitted + records.unsupported`:

| Selection count | Meaning |
| --- | --- |
| `records.selected` | Lines contributing selected message text in `messages` mode. In `complete` mode, all accepted complete input lines are selected as raw records. |
| `records.omitted` | Lines omitted by the message selection, including blank lines, recognized non-message records and duplicates excluded by the reader. |
| `records.unsupported` | Complete lines the selected message reader does not understand. A parsing/read failure is reported separately as a failed scan. |

A selected line may contain several messages and fields that are not selected.
These are not field or attachment coverage counts. Complete mode's zero
unsupported count reflects raw selection, not support for every record format.
Selection also stays separate from current storage, forgetting and delivery
outcomes; a selected fragment can be covered by an existing forgetting fence.
An unfinished final line is outside these counts until a later accepted prefix.

| Coverage observation | Meaning |
| --- | --- |
| `catalog` | `unobserved`, `available` or `unavailable`. Initial zero counters with an unobserved catalog are not a measured empty history. |
| `tracked_scopes`, `checking_scopes`, `failed_scopes`, `missing_scopes` | Tracked producer files and their latest observed verification state. A missing file is not treated as forgotten. |
| `observed_bytes`, `examined_prefix_bytes`, `unaccepted_observed_bytes` | Last recorded source sizes, examined complete prefixes, and their difference. Unaccepted source bytes can include unfinished tails or failed reads; they are separate from queued selected-payload `pending_bytes`. |
| `unknown_prefix_scopes` | Files without known selection accounting, including earlier checkpoints that predate it. Zero selection counts do not fill that missing observation. |
| `uncertain_scopes`, `uncertain_intervals`, `unresolved_previous_bytes` | Files with uncertain history, unavailable/interrupted observation periods, and known unaccepted bytes carried from earlier observed generations. These do not measure everything that may have disappeared. |
| `tracked_from`, `observed_at`, `complete_prefix_at` | Tracking start, last catalog observation, and the last time all tracked prefixes finished without checking, failed or missing scopes. A prior complete-prefix timestamp does not establish current or historical completeness. |
| `queue_nonempty_since` | Start of the observed continuous non-empty queue period, retained across restarts. It is reported as null when empty; a later empty-to-non-empty transition starts a new period. Older pending queues can have an unknown start. This is not the oldest fragment's age. |
| `last_contact_at` | Last successful authenticated delivery preflight verifying the saved, matching active device grant. An arbitrary HTTP response or failed authorization check does not update it. |
| `last_acknowledged_at` | Last validated page receipt applied locally, including reconciled receipts and stored/forgotten outcomes. It does not timestamp index completion. |

Time since contact is not a measured continuous outage, and queue age is not
offline duration. These remain the last saved observations. History before
tracking and records never exposed by the producer are always unknown. A later
successful scan retains missing/changed-history uncertainty; it cannot prove
what vanished between observations. Prefix and delivery observations do not
establish index readiness; source index observations are reported separately below.
**L2/L3 consolidation progress remains unavailable.**

Coverage component checks and Electron/frontend builds passed. A synthetic source
preview worked in a real browser. The
[development validation record](../research/2026-10-21-durable-capture-implementation.md#coverageaccounting-source-delta)
preserves the detailed-mode failure and successful rechecks. Installed-artifact
acceptance and the remaining L1 requirements remain open.

### Read source index observations

An additional **unreleased development delta** exposes
`activity.report.capture.coverage.index` under **Capture coverage and history**.
Its [source validation](../research/2026-10-21-durable-capture-implementation.md#index-observation-source-delta)
is separate from the earlier prefix-only checkpoint; installed acceptance remains
open. It covers **service-accepted events for the authorized shared source
across its devices**. Local `pending_events`, `stored_events` and
`forgotten_events` describe this inbox, so those totals have a different scope.

After normal delivery, the runner requests at most two index pages, each covering
up to 1,000 events, checking the existing delivery time allowance before each
request. Network request timeouts still apply. The authenticated
`GET /v1/capture-grants/{grant_id}/index-progress` endpoint rechecks current grant,
key and source access. Observation reads existing service state without invoking
models or starting indexing work. If no time remains, the saved observation stays
unchanged.

Observation queries use a revision/generation job index, a one-second pool wait,
a 500 ms lock timeout and a two-second statement timeout. A busy observer returns
503 and preserves the previous saved result; it does not undo delivery receipts.

Each event is classified using its memory's current revision and the active
embedding generation observed on that page:

| Count | Meaning |
| --- | --- |
| `events` | Service-accepted events examined during the sweep. |
| `lexical_indexed` | Visible ordinary current revisions counted as text indexed. Equals `vector_indexed + waiting + failed`, so it overlaps the vector count. |
| `vector_indexed` | The current revision has a stored embedding for the observed active generation. |
| `waiting` | No matching vector and no failure meeting the rule below. This can include paused inference; it does not establish that a job is running. |
| `failed` | No matching vector, with a failed job for this revision/generation and no pending or leased job for it. |
| `withheld` | Review state or source visibility excludes the revision from ordinary search. |
| `forgotten` | The event has no retained memory link, or its memory is deleted. |
| `unknown` | The referenced memory or its current revision could not be observed. |

The six states from `vector_indexed` through `unknown` partition `events`.
These count accepted event records, including retained fragments and revisions;
they are not counts of distinct conversations or ideas. Stored index
observations do not guarantee a search result: current permissions, review state
and query filters still apply.

The encrypted record keeps an unfinished `active` sweep and the last `completed`
sweep separately across restarts. The app displays the completed observation
when one exists and labels newer partial progress separately. `status` is
`unobserved`, `available`, `unavailable` or `unsupported`; an unavailable or
unsupported refresh preserves saved results. `last_attempt_at` records the last
saved attempt, while each sweep carries its own generation, page count,
`started_at` and `observed_at`. `inference_paused` reflects its last observed page.

A completed sweep reached the end of its event-ID traversal. Its timestamps
cover a sequence of observations, **not an atomic census**. Revisions can change,
and newly accepted events earlier than the cursor can appear in the next sweep.
A changed generation restarts the active sweep from the beginning; partial
results do not replace a prior completed observation, which retains its original
generation and timestamps. L2/L3 consolidation progress remains unavailable.

## Storage and resource limits

| Limit | Current value |
| --- | --- |
| Pending selected content per source | Default 256 MiB; configurable from 1 to 1,024 MiB |
| Pending selected content across this device's saved sources | 1 GiB |
| Inbox database admission per source | 512 MiB |
| Aggregate inbox database admission on this device | 2 GiB |
| Free disk required for new intake | At least 512 MiB, plus room for the incoming transaction |
| Retained event references per inbox | 100,000; producer tracking is also bounded |
| Producer scopes per inbox | 10,000 |
| Source RAM | Default 256 MiB; configurable from 128 to 2,048 MiB |

Content limits count the selected payload, independently of database
overhead. Raising the payload limit does not raise the database or reference
limits. Database admission counts SQLite pages. Bounded delivery bookkeeping can
use reserve above the database limit so reconciliation and forgetting can still
finish; this is not extra allowance for new capture.

At capacity, new intake stops and already accepted evidence stays available.
Lowering a limit does not trim the queue or silently discard events. Delivery
and forgetting remain available, subject to usable disk space and current
authorization. Free storage or let the backlog deliver, then check status again.
The [desktop resource limits](desktop-sources.md#capture-and-resources), including
the sampled RAM limit and process deadline, also apply. Capture does not need a
local model; server indexing follows the workspace's model policy.

## Pause, remove and forget

**Pause on this computer** works offline. It saves the pause, stops this device's
scan and retains its inbox and committed progress. Resume starts from that saved
state and delivery rechecks current authorization.

To remove retained capture, pause it first, then select **Remove from this
computer → Revoke device grant and discard local inbox**. This permanently
discards the local inbox, including pending content and deliveries whose outcome
is still unknown. The workspace must confirm that the device grant, or its
source, is revoked before local data is discarded. Original chat files, server
memories and the application key's other permissions remain. Revoke an unused
application key separately in **People & apps** when intended.

If the saved device key is lost, expired or revoked, use a current administrator
connection for the **same workspace**. Removal from **Connections** automatically
uses that matching administrator session.
Alternatively, expand **Device key unavailable?** under **Sources on this
computer** and supply the optional **Administrator key** for the displayed
workspace. The removal operation uses this credential only to check and revoke
the saved grant; it does not save the credential, replace the source's key or
authorize new capture. The native helper checks the exact saved grant binding,
and the server checks the caller's current rights. A refused credential leaves
the inbox in place.

A lost revocation reply leaves local data in place. Read fresh status before
retrying: the removal flow checks the existing grant and can recognize an
already-completed revocation. If confirmed retirement was saved locally but
cleanup was interrupted, cleanup can resume offline from that record without
a surviving device or administrator credential. Leave the optional removal
credential empty for that local cleanup. A lost reply without a saved retirement
record still requires server confirmation. Offline pause remains available
while server confirmation is unavailable.

Server revocation and forgetting have different effects. Revoking a device grant
stops its capture delivery; revoking a source also denies access to its custody
space. Neither action is a request to erase its stored memories. To forget a
captured fragment, use the normal memory-forgetting action and review
`capture_forget`: it withdraws that fragment's retained raw evidence, projections,
parts and revisions together and may include adjacent messages. Its retained
count is an observation; the write rechecks the current family atomically.
Later deliveries of the same fragment stay forgotten. This is not semantic
deletion of matching text across unrelated files, new generations or imports.

## Recovery boundaries

The new [portable archive work](#back-up-and-inspect-an-inbox-unreleased) provides
export/inspection and a library for restoring a new local inbox. Native restore,
enrollment on another device and reviewed policy/device migration remain open.

Each inbox uses a separately generated, random 256-bit key sealed by the OS
credential store. Selected payloads, checkpoints and coverage records are
encrypted with AES-256-GCM in private local storage. The dedicated API key does
not derive or replace that encryption key. Neither key is returned by
`source.status`.

Only a new, pending enrollment may initialize an empty inbox, before any intake.
Missing or damaged keys, an initialized database that has disappeared, or an
enrollment/binding mismatch stop capture visibly. The runner does not silently
create an empty replacement and claim previous work was preserved.

Unlock OS credential storage when it is merely locked. For lost or corrupted
state, preserve the existing files and restore the verified matching inbox,
enrollment, settings and usable protected key. A new computer cannot infer past
accepted or forgotten ranges from today's chat files. Restoring the original
verified state or completing an explicitly reviewed migration is required; new
IDs, a new key or a fresh source are not a recovery substitute. An OS-sealed key
is not automatically portable between accounts or computers, and a server
backup cannot reconstruct undelivered local evidence.

An expired or revoked device API key can be handled through the
[administrator removal fallback](#pause-remove-and-forget). That fallback
permits retirement and explicit local discard; it does not recover a missing
encryption key or restore capture. Replacing an established inbox's key through
an ordinary settings update remains unsupported.

**Repair saved scan history**, also exposed as `source.repair`, repairs only
observations. It preserves the damaged diagnostic file and resets scan history
for **every source on this computer** to unknown. Settings, credentials, inboxes
and capture checkpoints remain. It does not recover lost evidence, restore
encryption keys or prove a previous scan succeeded. Repair does not start a scan;
normal automatic checks resume at their next interval.

### Back up and inspect an inbox (unreleased)

This development work remains unreleased. Core, helper and controller checks
and local builds passed; the Electron export/restart-inspection journey and
packaged acceptance remain pending. Its
[archive proof](../research/2026-10-21-durable-capture-implementation.md#portable-inbox-archive-source-delta)
is separate from the earlier policy, index and stable-release evidence.
**Sources on this computer** now exposes **Back up this capture inbox** for
retained sources and a separate **Inspect a capture backup** control.

1. Pause the retained source and wait for active scans to finish. Export needs
   the current source settings and access to its OS-protected inbox key.
2. Open **Back up this capture inbox**, choose a **new** archive file, and
   generate or supply a separate recovery key. Save the key separately and
   confirm that it will remain available if the computer is lost.
3. Select **Create encrypted backup**. The exporter checks a consistent inbox
   snapshot, encrypts the bundle and verifies the written ciphertext before
   returning its archive identity and saved counts.
4. To check an archive independently, open **Inspect a capture backup**, choose
   the file, supply its recovery key and select **Verify backup**. Inspection
   works offline without the original source settings or OS-sealed inbox key.

The encrypted bundle retains the original binding and policy, selected pending
payloads, saved delivery pages/receipts, checkpoints, deletion fences, producer
references and coverage/index observations. It also carries the inbox encryption
key inside the encrypted manifest. The separate recovery key is required to
open it. No workspace API credential or producer files are included. Already
delivered memory bodies that have left the local queue require a workspace
backup; archive counts describe the saved local snapshot.

Inspection returns bounded identity, policy and status information, with
`authenticated: true`, `workspace_credentials_included: false` and
`source_enrolled: false`. It returns neither raw messages nor secret keys and
makes no model or workspace request. If an export reply is lost or uncertain,
inspect the chosen file before deciding whether another export is needed; an
existing destination is never overwritten. Native actions are documented in
the [agent guide](desktop-operator.md#capture-inbox-archives-unreleased).

The library can restore an inspected archive into a **new private inbox
directory**, preserving its original grant binding and inbox key. This is a
foundation for local restoration under the same grant. It does not enroll a
source, replace an existing inbox, reseal keys for a new OS account, migrate a
device/policy or resume capture. Current authority and later server forgetting
decisions still need separate verification. Those native recovery journeys,
portable migration and six-platform acceptance remain open.

## Agent and administrator setup

Remote administration uses the server's capture APIs. The local runner uses the
same OS-account [private desktop interface](desktop-operator.md) as Studio;
a network memory credential does not authorize control of the computer. Discover
the current [agent operation schemas](agent-control.md) before submitting a
request. These operations are part of the unreleased implementation:

| Operation | HTTP route |
| --- | --- |
| `capture.source.configure` / `capture.source.status` / `capture.source.revoke` | `PUT` / `GET` / `DELETE /v1/connectors/{connector_id}/capture-sources/{source_id}` |
| `capture.grant.configure` | `PUT /v1/capture-sources/{source_id}/grants/{grant_id}` |
| `capture.grant.status` / `capture.grant.revoke` | `GET` / `DELETE /v1/capture-grants/{grant_id}` |
| `capture.pages.accept` | `POST /v1/capture-grants/{grant_id}/pages` |
| `capture.pages.receipt` | `GET /v1/capture-grants/{grant_id}/pages/{page_id}` |
| `capture.fences` | `GET /v1/capture-grants/{grant_id}/fences` |

After registering the new `conversations` connector with `access_mode:
"published"` and mapping its audience, an administrator approves the source
with a stable `source_id`. The initial source PUT body is:

```json
{
  "expected_version": 0,
  "namespace": "selected-source",
  "name": "Selected conversations",
  "members": ["application:approved-assistant"],
  "capture_mode": "messages",
  "keep_accepted": true
}
```

Use the original approved namespace if it differs from `selected-source`.
Updating the name or audience uses the current source version from GET. The
source identity and capture selection remain immutable. Then approve a stable
`grant_id` through the device-grant PUT with
`{"device_key_id": "DEDICATED_APPLICATION_KEY_UUID"}`. Only an administrator
can authorize the source and grant; the source's application key cannot grant
itself custody or expand its audience.

Read `source.status` locally, then send `source.configure` with its fresh
`expected_revision`, the complete [source settings](desktop-sources.md#local-agent-controls)
and the dedicated credential through private stdin. Add these fields to the
`source` object, using the IDs approved above:

```json
{
  "capture_mode": "messages",
  "custody": {
    "source_id": "APPROVED_SOURCE_UUID",
    "grant_id": "APPROVED_GRANT_UUID",
    "keep_accepted": true,
    "pending_limit_mib": 256
  }
}
```

This is a settings fragment, not a complete `source.configure` request. Native
enrollment creates and seals the independent inbox key; do not supply one through
the public source object. Keep the same mode, namespace, source and grant on
later settings updates. An uncertain administrative reply requires reading the
existing source/grant or local status before another write.

The runner owns page construction and retries. Pages contain 1–50 selected
evidence events, with at most 1,500,000 bytes of canonical JSON. Reusing an ID
with different content is rejected. `capture.pages.accept` is classified as
private input; use the private CLI/transport path described by discovery rather
than putting conversation payloads into ordinary agent tool arguments.

Native removal requires `source.pause` with `enabled: false`, followed by
`source.remove` with a fresh `expected_revision`, `id`, `confirm: true` and
`discard_local_inbox: true`. Its optional `retirement_credential` supplies a
current administrator credential for that workspace when the device key is
unavailable. Pass it only through the private desktop pipe; it is never saved
by removal or used for intake. The app can pass a matching administrator session
handle for native resolution. Omit the field when completing cleanup after
retirement was already recorded locally; no surviving credential or HTTP request
is then needed. Native history repair requires its current
`repair_token` and `confirm: true`, with no active source scan; its source ID
identifies the displayed context, not a source-only reset.

Full archive recovery/migration, the complete installed Windows/macOS/Linux journey
and full L1 acceptance remain pending. This workflow does not replace those
gates or narrow the [65 product requirements](../PRODUCT_REQUIREMENTS.md) and
L1–L7 scope.
