# Durable conversation capture: implementation checkpoint

**Unreleased implementation.** This is development work for
[L1 of the layered librarian](2026-10-20-layered-librarian.md), not a claim that
published Studio provides the complete journey. Existing sources keep their
mirror behavior. All [65 product requirements](../PRODUCT_REQUIREMENTS.md) and
L1–L7 remain in scope; this checkpoint does not close L1 or R07. The current
[app and agent guide](../service/durable-capture.md) describes the implemented
enrollment, prefix/queue observations, limits, removal and recovery boundaries.

## Development proof, 21 October 2026

The Linux x64 source preview passed both `capture-enroll` and `capture-resume`
at 01:13 UTC, using Electron 44.7.0, real libsecret storage, the actual app UI and
native PostgreSQL with an interpreter-based engine. It exercised the mapped
audience and consent form, offline local intake, pause, refusal of unconfirmed
discard, producer removal, app restart/reconnection, queued delivery and lexical
recall with the tool trace excluded. It also verified administrator retirement
after device-key revocation while retaining the server memory.

Private evidence is retained under `2026-10-20-durable-conversation-inbox/`.
`preview.5IOWGZNA/result.json` records the two passing phases;
`linux-source-journey.receipt.json` pins source digest
`160fb165f7d86842ff116ade44d2df4f9304f220fd7a58f2a7db61afb0a8abc1`.
That digest precedes the later server history-metadata correction below. This is
Linux source proof, not packaged or other-platform acceptance; the receipt
records zero production memory writes and zero paid model calls.

The original `capture-combined-checks.log` remains **116 passed, 1 failed**:
an administrator without content access received an incorrect
`has_capture_history` flag. The correction exposes only a boolean under the
existing source-policy authority, without granting event-row or memory reads.
All four targeted scenarios now pass: administrator metadata/content isolation,
cross-tenant isolation, stale-version rejection and older-history enrollment.
`capture-history-authority-checks.log` preserves three passes plus the later
SDK-fixture failure (`json=` instead of `body=`);
`capture-history-authority-recheck.log` records the corrected older-history
scenario's pass. These receipts do not rewrite the original combined result.

The new [native capture probe](../../studio/electron/native-capture-probe.ts)
is wired into the [installed-hosting check](../../studio/electron/scripts/smoke-installed-hosting.mjs)
for all six required desktop targets. Its packaged executions remain pending.

Development [CI run 39527490005](https://github.com/Perseusxrltd/mnemion/actions/runs/39527490005)
identified a missing capture helper in the container build and stale upgrade-table
and health-contract expectations. The helper is now included, and all **15**
targeted upgrade/health checks passed, including the released schema 29 to capture
schema 30 transition with existing keys, grants and memories preserved. The six
new capture modules are measured by the service coverage suite; the legacy 45%
and service 75% thresholds remain unchanged. Subsequent
[CI run 39539827891](https://github.com/Perseusxrltd/mnemion/actions/runs/39539827891)
passed all 12 jobs on the policy checkpoint `0ed2130`, before the archive delta
below. Packaged capture acceptance remains pending. The separate
[4.44 security hotfix](../releases/4.44.0.md)
does not ship this unfinished capture milestone.

## Implemented components

| Component | Current implementation |
| --- | --- |
| Native enrollment | Studio offers explicit retained capture only for a new conversation connection. The administrator approves the source policy and exact device-key grant before native enrollment. App and private agents use the same typed `source.custody` object; existing mirrors cannot silently convert. |
| Capture policy and local preview | An additional unreleased delta adds Selected/Conversation/Detailed choices, relative JSONL file rules, size caps and explicit mirror/retained selection through the same app/agent configuration. A bounded local preview returns counts and capability statuses; explicit-policy retained fragments carry the immutable approved policy fingerprint. Source, Linux journey and separate recovery/migration checks passed; full L1 acceptance remains open. |
| Portable inbox archive | Unreleased checkpoint `7aca19e9` exports and inspects encrypted local evidence, and restores a new private inbox under its original binding. Core, helper/controller, migration and Linux app export/restart-inspection checks passed. These checks do not establish the separate device-recovery delta or packaged acceptance. |
| Device recovery | An unreleased source checkpoint re-encrypts an inspected archive for a new approved grant and inbox key, retires the old grant and installs a new paused native source. The original organization/source/namespace/policy stays fixed. Protected intents support explicit finish/discard after interrupted local publication. Source, controller, operator and migration checks plus the three-phase Linux source journey passed. All three earlier failed journeys are retained below; six-platform packaged and full L1 acceptance remain open. |
| Independent headless capture | An additional unreleased delta gives `mnemion-connect` explicit JSON custody and stdin controls for paused enrollment, resume, status, encrypted backup and fixed-policy device recovery. Protected file/environment references replace automatic desktop OS sealing. Local intake precedes service access. Source regression, migration and updater checks passed, including polling and verified managed-runtime integration; packaged acceptance remains open. Configurations without `capture` retain mirror behavior. |
| Encrypted selected inbox | The native controller creates an independent random 256-bit key and seals it through OS credential storage. Selected items and a verified capture checkpoint commit together under AES-256-GCM. Both messages and complete modes use the existing renderer. Messages mode cannot retain a raw transcript or hide raw text in its source evidence. |
| Local capture and scheduling | The normal desktop runner commits available selected JSONL evidence before any service request in a scan. Accepted events survive restart and producer removal/rotation; unfinished tails wait. Missing source files can stop new capture while already accepted evidence remains deliverable. |
| Durable service custody | Explicit administrator consent, immutable selection/source identity, exact device-key grants, current audience/role checks, immutable event receipts and idempotent pages. Existing provider permission leases remain unchanged. |
| Delivery and reconciliation | The runner saves exact pages before delivery, looks up uncertain receipts and resends only the same page. Current revocation and forgetting fences apply to backlog. Revoked grants retain local pending evidence without attempting ingestion; observed revocation also stops later local intake. |
| Private scan observations | Last success, failure, interrupted attempt and next check survive restart. App and native status separate local acceptance, pending content, server acknowledgements, unknown pages, incomplete scans and capacity. Explicit repair preserves damaged diagnostics and resets history for every source on the device to unknown without changing sources, credentials or capture data. |
| Encrypted coverage accounting | The inbox retains per-file prefix observations and one bounded aggregate, with selection counters committed alongside accepted evidence. Missing/changed/unobserved history, continuous non-empty queue start, authenticated contact and receipt acknowledgement remain distinct. This development delta is still under validation. |
| Source index observations | An additional unreleased delta reads current revision/index states for the authorized shared source across devices. It saves partial and completed sweeps separately, with observed generation and time interval. Source, controller and migration checks passed; installed acceptance remains open. |
| Device resource admission | Pending selected payload and actual SQLite database pages have separate per-source and aggregate device limits. New intake also needs free disk headroom. Reducing limits preserves accepted evidence and leaves bounded delivery/forgetting work available. |
| Pause and removal | Pause works offline. Retained removal requires a pause, explicit `discard_local_inbox: true` and confirmed server revocation before local discard. A current workspace administrator can retire the exact saved grant when the device key is unavailable. Its optional `retirement_credential` is used only through the private removal path and never saved by the operation. Recorded retirement can finish cleanup offline without credentials. |
| Forgetting and recovery | One captured fragment's raw evidence, projections, parts and retained revisions are withdrawn atomically. Late deliveries stay denied. Current negative state and grant revocations survive restoring an older backup. Revoked custody also stops new background inference and vector publication. |

## Current limits and observations

The local queue defaults to 256 MiB of pending selected payload per source,
configurable from 1 to 1,024 MiB, with a 1 GiB aggregate pending limit on the
device. Database admission is 512 MiB per source and 2 GiB across the device,
counting actual SQLite pages. New intake requires at least 512 MiB free disk
plus room for its transaction. Each inbox also bounds retained event references
at 100,000 and producer scopes at 10,000. The desktop source RAM allowance
defaults to 256 MiB and accepts 128–2,048 MiB, with sampled enforcement.

A limit below current usage blocks new admission without trimming the queue.
Inspection, delivery and forgetting remain available subject to usable disk and
current authorization. Bounded delivery bookkeeping may use reserve above a
database admission limit, reported as over-limit. It is not extra capture
allowance. Pending selected evidence has no automatic expiry.

Local acceptance, service commitment, indexing readiness and librarian processing
are distinct states. Transport success does not prove semantic readiness. The
source-status report is an observation, not a raw-capture receipt. Clearing saved
ciphertext is logical local cleanup; it does not promise forensic erasure from
storage hardware, old backups or previously published Git commits.

## Coverage/accounting source delta

Development checks observed 65 existing affected Python cases passing. A new
mixed batch had 20 passes and one detailed-mode/session-header failure; the fix
then passed its targeted recheck. The latest run passed all 11
[coverage cases](../../service_tests/test_capture_coverage.py), including damaged
checkpoint reporting, plus the public-command/standalone-schema contract check.
All 35 Electron controller checks passed. Electron and frontend
builds passed, as did Python lint and formatting for nine changed modules. A
real-browser source preview with synthetic data worked; its only observed console
error was the fixture's missing favicon. Expanded details were inspected at a
720-pixel window width and remain collapsible. These receipts cover development source;
installed-artifact acceptance and complete L1 acceptance remain open. The earlier
journey and test receipts above predate this delta.

The [typed coverage model](../../mnemion/capture_coverage.py)
and [encrypted observations](../../mnemion/connectors/capture_observations.py)
are separate from the device's repairable scan-diagnostic history.

Parser accounting partitions **complete input lines**, with
`selected + omitted + unsupported = lines`. Message selection counts lines
contributing supported text, understood omissions/deduplication, and unsupported
input separately. A line can contain multiple messages or unselected fields;
these counters do not account for individual fields or attachments. Complete
mode selects the accepted raw lines, so its zero unsupported count is not a
claim that every producer record is understood. The saved capture mode defines
the interpretation. No raw message-mode archive is added by this accounting.

The inbox encrypts per-file observations and a bounded aggregate using its
existing key. A verified prefix's counters commit in the same transaction as
selected items and the capture checkpoint; a failed acceptance cannot advance
them. Aggregation replaces the prior contribution for that scope, including
when a generation changes. The totals describe **last accepted prefixes where
accounting is known**, not lifetime intake, distinct messages or current server
memories. Status reads the aggregate without decrypting every producer checkpoint.

Catalog state distinguishes unobserved, available and unavailable. Initial zero
counters do not assert an empty history. Missing scopes retain their previous
observations, and older checkpoints without selection accounting remain unknown
until re-examined. Missing files, generation changes, rewrites and unavailable
or interrupted observation periods preserve uncertainty. Previously observed
but unaccepted bytes remain separately reported after a generation change.
They cannot measure records that disappeared unseen. History before tracking
always remains unknown, even after a later successful scan.

`queue_nonempty_since` is a persistent empty-to-non-empty transition timestamp;
status reports null when the queue is empty and the next such transition starts
a new period. It is not an individual event age or a continuous outage measure.
`last_contact_at` advances only after authenticated delivery preflight verifies
the matching active grant. `last_acknowledged_at` advances when a validated page
receipt is applied locally, including reconciliation and forgotten outcomes.
Neither observation establishes indexing completion. At the committed
prefix-only checkpoint `15a678b`, index readiness remained unobserved. The
[status guide](../service/durable-capture.md#read-prefix-coverage) documents the
source-byte, selected-payload and history counters separately. **L2/L3
consolidation progress remains unavailable.**

## Index-observation source delta

This **unreleased development delta** follows the prefix-only checkpoint
`15a678b`. Six targeted [database, permission and restart checks](../../service_tests/test_capture_index_progress.py)
have passing receipts. They cover worker commit, current revision and model
generation, bounded authenticated pagination and revocation, failed/withheld/
forgotten classifications, resumable sweeps and recovery after a source-lock
timeout. The broader batch recorded 19 passes and one fixture validation failure
(a revision lacked its required reason); the corrected case and new busy-source
case then passed. Final focused checks passed after the strict progress validator
and narrow SQL projection changes.

All 39 desktop controller checks, 29 migration checks, the delivery/prefix/API
contract checks and Electron/frontend builds passed. The new panel was visually
inspected at 720 pixels with zero browser errors or warnings. These results do
not establish installed-artifact, six-native or complete L1 acceptance.

The [service observer](../../mnemion/service/capture_progress.py) reads current
memory revisions and the observed active embedding generation through the typed
`CaptureIndexPage` response. Each authorized page covers at most 1,000 accepted
events for the **shared source across its devices**, including forgotten events.
Lexical/vector, waiting, failed, withheld, forgotten and unknown counts have the
definitions in the [status guide](../service/durable-capture.md#read-source-index-observations).
Lexical counts overlap the vector/waiting/failed states; event counts are distinct
from unique memories and from this device inbox's pending/stored/forgotten totals.
The observer invokes no model and starts no indexing work.

Normal delivery requests at most two index pages after its other work, checking
the existing time allowance before each request; network timeouts remain separate.
The revision/generation job index avoids a full job scan per observed memory.
Queries use a one-second pool wait, a 500 ms lock timeout and a two-second
statement timeout, with busy-source recovery covered by the focused checks.
The inbox validates source, grant, cursor and bounded
counts, then encrypts the accepted page contribution. `IndexProgress` preserves
an active sweep and the prior completed sweep separately across restarts.
Generation changes discard the active accumulation and restart at the beginning;
partial or unavailable observations preserve the completed result with its
original generation and timestamps. An unsupported server remains explicit.

Sweep start/end timestamps describe a sequence of page observations. Revisions
can change and earlier-ID events can arrive during that sequence, so reaching
the final page is not an atomic census or a promise of current search results.
The app labels saved, partial and completed observations and keeps their scope
separate from local delivery. **L2/L3 consolidation remains unavailable.**

## Capture policy and preview source delta

This additional **development delta remains unreleased**.
Separate source runs passed 6 policy checks, 50 regression cases, 46 native
controller checks and 1 public-contract check. Local native, frontend and desktop
build checks passed. The earlier capture, index and 4.44 release receipts retain
their original scope.

A Linux source journey passed preview and enrollment, then exposed a saved-status
serialization failure: recursively omitting nulls removed required nullable
capture coverage/index fields, so Studio rejected the report before another
scan. The corrected status view preserves those fields in current and
last-success capture reports. A 31-case status/wire regression run passed,
including finish, reopen and next-scan behavior. Earlier attempted journeys and
harness-version mismatch receipts remain retained.

The corrected Linux source journey passed at **03:34:07 UTC on 21 October 2026**,
with the OS credential store available in both enrollment and resume phases.
It verified encrypted local acceptance, restart with the same protected key,
delivery after producer removal and administrator-assisted removal/cleanup.
Both phases recorded zero production-memory writes and zero paid-model calls.
Its source-input digest is
`f7466da8452f58a75ac0b8a63cbf3a71f148d09ddd460742cbbee11e725bac2d`.
This proof predates a later recovery-only correction and covers those recorded
inputs; the passing native journey was not rerun for that correction.

Review then found that service restore omitted the new capture-policy column and
needed policy validation and immutable-binding checks. The correction passed
**2 dedicated recovery checks in 14.45 seconds**: an actual snapshot plus a later
ledger restored a policy-bearing source with current denial/grant state preserved;
the separate check rejected an existing policy's removal/change and invalid
retention. The final migration preflight passed **29 checks in 56.01 seconds**,
with fingerprint
`48372ae8999b3dc3fe0f89c504316e1732d4675ef7f5bb53a9bcece75fb70c88`.
These source and service-recovery proofs leave portable inbox recovery,
six packaged targets and complete L1 acceptance open.

A separate **720×800 layout check** used the actual `CapturePreviewPanel` and
production CSS with synthetic data and a long filename. Counts remained readable
without horizontal overflow. Its only console error was the temporary fixture's
favicon 404; this is layout evidence only.

The [typed policy](../../mnemion/capture_policy.py) defines Selected with either
content mode, Conversation with `messages`, and Detailed with `complete`.
Existing Pause remains a lifecycle control. Session selection uses relative
JSONL filename globs, including exclusions; it does not inspect session IDs or
redact fields inside a file. Patterns are case-sensitive, `*` matches subfolders,
and built-in private-file exclusions remain mandatory. File/record size caps
default to 1,000,000,000 and 2,000,000 bytes; the record cap cannot exceed the file
cap. Source RAM, file-count, pending-content and database limits remain separate.

The [local preview](../../mnemion/desktop_capture_preview.py) considers at most
eight matching files, reads at most 128 KiB per file and 1 MiB total, visits at
most 10,000 directory entries and checks a three-second soft deadline between
entries. It returns relative paths, per-file outcomes and sampled complete-line
counts without raw bodies, saved source content or model calls. A complete
catalog describes traversal, not full file contents. Duplicate/context handling
and changing files can yield different counts during actual capture.

App and agent call the same preview/configuration path. The returned
`configuration_hash` must match native `preview_hash` for explicit-policy sources;
it binds the normalized selection/resource settings rather than the sampled
bytes. Capability statuses explicitly report no attachment-binary reads, no
external-link following, unavailable hidden reasoning, unsupported field
redaction and no automatic expiry. Server capability and authority are checked
separately during enrollment.

`source_mirror` retains existing reconciliation/removal behavior;
`until_deleted` requires administrator-approved retained custody. The server
stores the immutable policy in its source/grant contract; the local enrollment
binds the same policy. Explicit-policy fragments carry `capture_policy_revision`,
checked by both inbox and service alongside the approved mode/path and declared
file boundary. The collector enforces record-size admission. A different policy
requires reviewed migration. Legacy sources without a policy keep their existing
`complete`/`messages` behavior and mode-only fragments; they are not silently
migrated. Portable recovery, broader policy controls, headless operation, bounded
history and all six packaged acceptance journeys remain open. The
[app guide](../service/durable-capture.md#content-file-selection-and-retention)
and [native example](../service/desktop-operator.md#preview-conversation-capture-unreleased)
describe the current supported controls.

## Portable inbox archive source delta

This **unreleased foundation**, recorded at checkpoint `7aca19e9`, retains its
own proof separately from the device-recovery delta below. The original
combined run retained **6 failed, 26 passed**: export compared a write receipt's
`authenticated: false` with the successful read-back receipt's `true`. After
correcting that comparison, the [archive suite](../../service_tests/test_capture_archive.py)
passed **8 cases**. A later bounded delivery-membership lookup and damaged-page
case passed **9 archive checks**. The original 26 passes include 24 crypto-regression cases;
those were not rerun or promoted into new archive/native acceptance. A separate
helper test passed, and **48 native controller checks** passed, including export
unsealing only the inbox key and inspection without source settings or OS key
storage. Local native, frontend and desktop builds passed. The final migration
preflight passed **29 checks**, fingerprint
`994435e6a384e5e4789f1c14044100beb5189bd0cf159e6465f3c3b2d8e2fee7`.
The exact archive checkpoint `7aca19e9` subsequently passed
[CI run 39543234033](https://github.com/Perseusxrltd/mnemion/actions/runs/39543234033),
and its website sync succeeded. These results precede the device-recovery delta.
Earlier policy, index, Linux journey and 4.44 release proofs retain their
original scope.

The extended real Linux Electron journey passed both phases at **04:15 UTC**
after the bounded lookup and recovery-key field styling. It exported through
the app while the workspace was offline, inspected the same identity/counts
through the native agent, reopened the backup after app restart, then verified
it again after administrator retirement removed the original source and its
saved credentials. The 720-pixel app view had no horizontal overflow. Test
archive and recovery-key fixtures were removed; no production memory writes or
paid model calls occurred. `preview.QcJAa3re/result.json` and
`capture-archive-final-source-inputs.json` retain the private proof, source digest
`e04f5821fa1b0f17f05119e4ef016eb7c608f4b9df67fe992fb64a3bfe39751b`.
The earlier passing `preview.OlQ6dTAd` journey remains recorded separately.
This is source development proof for archive export/inspection. It does not
establish packaged acceptance or the later native restoration/migration work.

The [archive core](../../mnemion/connectors/capture_archive.py) snapshots a
caller-locked inbox, audits its schema and retained encrypted values, then writes
and verifies an encrypted bundle. Its manifest carries the original binding,
policy, limits and inbox key under a separate recovery key. The database retains
selected pending evidence, exact pending pages/receipts, checkpoints, denials,
producer references and saved coverage/index sweeps. It includes no workspace
API credential or producer files. Already delivered memories require separate
workspace backup; the archive exports the retained local custody state.

Inspection authenticates/decrypts in private staging, checks database integrity
and bounded evidence records, and returns identity/policy/status information
without raw messages or keys. Bounds include a 2 GiB database, 512 KiB manifest,
8 MiB individual SQLite values, one million rows per table and at most 51
delivery-membership rows in memory during page validation. Export/inspection
uses no workspace request or model invocation. A lost export reply calls for
inspection of the saved file, preserving the no-overwrite rule.

`restore_new_inbox` requires the inspected archive hash and a new private
destination. It preserves the original binding, pending delivery state and
inbox key; damaged archives, wrong keys, changed hashes, cancellation and existing
destinations cannot publish a replacement inbox. This is local restoration under
the same grant. The caller must still protect the returned key and separately
verify current enrollment/authority; the library does not create or activate a
native source, migrate its policy/device, or grant workspace access.

The current native wiring adds `source.backup` for a paused retained source with
its current revision and OS-protected inbox key, and `source.backup.inspect`
without requiring the original source settings/key. **Sources on this computer**
exposes export and verify controls, including a separately saved recovery key.
The [app guide](../service/durable-capture.md#back-up-and-inspect-an-inbox-unreleased)
and [agent inputs](../service/desktop-operator.md#capture-inbox-archives-unreleased)
keep these operations separate from the later native restore/enrollment delta,
reviewed migration, six packaged targets and full L1 acceptance.

## Device recovery source delta

This **unreleased checkpoint passed its focused source acceptance**. Its evidence is
separate from archive checkpoint `7aca19e9`, the policy/index proofs and the
released 4.44 security update:

| Run | Observed result and scope |
| --- | --- |
| `capture-device-transfer-initial-tests.log` | **8 passed in 10.98 s** across the [transfer core](../../service_tests/test_capture_transfer.py) and [real HTTP recovery](../../service_tests/test_capture_device_recovery.py) checks. |
| `capture-device-restore-helper-initial-tests.log` | **7 fixture errors in 13.59 s**: the fixture omitted `normalize`'s required `private_roots` argument. This run did not validate the helper cases. |
| `capture-device-restore-helper-fixture-fixed-tests.log` | **6 passed, 1 failed in 18.71 s**; the remaining failure was the wrong-copy diagnostic. |
| `capture-device-restore-copy-reason-test.log` | **1 passed, 6 deselected in 9.18 s** after preserving `source_conversation_copy_unverified` through the inbox boundary. This targeted recheck does not rerun the other helper cases. |
| `capture-device-controller-initial-tests.log` | **51 passed in 356.6 ms**, including new restore uncertainty, private-key handling, pending list, finish and discard checks. |
| `capture-device-final-regression-tests.log` | **25 passed in 55.70 s** in a later combined transfer, real HTTP recovery, helper, archive and backup regression. These overlap earlier cases and are not additional distinct checks. |
| `capture-device-migration-preflight.log` | **29 passed in 110.14 s**; the later frontend/controller fixes did not change these Python inputs. |
| `capture-device-read-poll-fixed-controller-tests.log` | **52 passed in 200.9 ms**, including a new regression for metadata polling concurrent with source operations. This supersedes the earlier controller run for the polling fix. |
| `capture-device-authority-fixed-controller-tests.log` | **52 passed in 174.6 ms** after resolving the protected retirement session handle through the native bridge; the extended check verifies resolution and absence of key leakage. |
| `capture-device-operator-boundary-tests.log` | **26 passed in 1.9226 s** across desktop operator and workspace-connection boundaries. The successful journey's runtime input digest remained unchanged. |

The Python migration fingerprint is
`83775dba121e62b9900910de925a3d01c6d1696d8e0ef79541d6521705e0ea19`.
Python inputs remained unchanged through the frontend/controller corrections;
the migration preflight was not rerun or promoted to different Python inputs.

The native/controller and desktop frontend builds passed before the first
three-phase Linux attempt, `preview.qaJtcFkO`. That attempt failed in
`capture-enroll` **before any source enrollment**: the new `CaptureRestore` empty
state compared two undefined selection values, then accessed `preview.value`.
The private error and screenshot are retained. Source now requires `preview &&`
before that comparison, and the corrected desktop frontend build passed.

The second attempt, `preview.jFwri4zH`, passed enrollment but failed before the
backup mutation: background recovery-list polling occupied the controller's
mutation slot. `recoveries()` now coalesces concurrent read-only metadata calls
independently of mutations. Mutating actions still revalidate their intent and
source revision, and closing the controller waits for the outstanding read.
The polling-specific 52-check controller run above and the rebuilt native
controller passed.

The third attempt, `preview.NOfJ6Eu3`, used
`capture-device-read-poll-fixed-source-inputs.json`, digest
`693b7d4849939d8c066a8e58f4547cb9542823cf6890ed67539e324e4e5b574e`.
Its complete `capture-enroll` phase passed, including consent, offline queue,
app backup and narrow layout. `capture-resume` delivered the old queue and removed
the old source, then app restore failed with `capture_retirement_credentials`:
the controller passed the renderer's protected session handle directly to the
helper. It now resolves that handle through the existing origin-bound native
retirement-credential bridge. The authority-specific controller run above and
the native rebuild passed. All three failed journey receipts remain retained;
the third attempt's passed enrollment does not make its recovery phase pass.

The fourth attempt, `preview.sYtog70x`, passed **all three phases** at
**2026-10-21T05:06:18.782382Z**. Its `result.json` and individual phase receipts
are bound to `capture-device-authority-fixed-source-inputs.json`, digest
`f287a9188ff7be73a8da5b3c261fa074f66b1571ad50079b6e0e175c9d184006`:

| Phase | Observed source behavior |
| --- | --- |
| `capture-enroll` | Actual consent, independent OS-protected inbox key, encrypted offline queue, pause before restart, app backup and agreement with agent inspection; narrow layout passed. |
| `capture-resume` | Queue/key survival after restart, delivery after producer removal, administrator retirement, then actual app archive recovery under the original policy/source with new OS-sealed keys and grant. The recovered source was paused and app/agent results agreed. |
| `capture-restored-resume` | New key reopened after another app restart; source stayed paused until explicit resume. Old queued memory was not duplicated, new memory was captured and fixture cleanup passed, with `acceptedEvents: 2`. |

Every phase reported OS credential storage available, **zero production memory
writes and zero paid model calls**. The recovered receipt was readable at
720×1000 in `native-capture-recovery.png`, which was visually reviewed. Independent
cleanup verification found no capture fixture, archive or selected/recovered
producer folders left behind. Runtime inputs still matched the successful
journey digest after the operator checks. This completes the bounded Linux
source proof; all six packaged acceptance journeys and full L1 remain open.
The earlier archive checkpoint retains its separate export/inspection proof.

The [transfer core](../../mnemion/connectors/capture_transfer.py) authenticates the
inspected archive hash and creates a new private inbox with a new supplied key.
It permits only `grant_id` to change in the binding: organization, connector,
capture source, namespace, mode and optional policy must match exactly. Encrypted
payloads, pages/receipts, checkpoints, producer references and coverage/index
observations are re-encrypted without changing evidence identities or deletion
fences. Historical receipts retain their issuing grant. Existing destinations,
changed archives and interrupted re-encryption cannot publish a replacement.
The core does not issue grants, enroll a native source or resume capture.

The HTTP checks cover an old acknowledgement lost after server acceptance,
additional undelivered backlog and forgetting added after backup. Replacement
delivery preserves event identity, applies current negative state and leaves the
original grant revoked. Recovery does not reactivate old authority or treat a
saved archive as proof of current permission.

The [native helper](../../mnemion/desktop_capture_restore.py) and controller add
`source.restore`, `source.restore.list`, `source.restore.finish` and
`source.restore.discard`. Restore takes an inspected archive, current source
revision, matching local preview, paused replacement settings, a newly approved
dedicated credential/grant and explicit previous-device retirement consent.
Mode-only archives also require a matching preview for this action. It checks
captured prefixes for checkpoint files present in the selected producer folder;
missing logs do not prevent backlog recovery and do not become known history.
The archive itself includes no producer files or workspace API credential.

The native controller generates a new random inbox key and OS-seals both it and
the replacement device credential. The helper verifies current source, audience,
connector and grant authority before retiring the original grant. The one-use
retirement credential is not saved, and retiring a grant does not revoke its API
key's unrelated rights. Once retirement is confirmed, a private intent with
OS-sealed replacement settings precedes local inbox/settings publication. A new
source is installed paused. The original archive and existing inboxes are never
overwritten; authorization/retirement requests invoke no model.

An uncertain mutation is not replayed automatically. Read source status and the
bounded pending-intent list first; listing requires neither credentials nor OS
key access. Explicit finish uses the saved replacement keys and current service
authority, and needs the same archive/recovery key if its local copy was not yet
published. It does not duplicate an already installed source or reverse a later
explicit enable choice. Explicit discard first revokes the replacement grant,
then removes unfinished local evidence and the intent while preserving the
archive. An already installed source requires ordinary source removal. The
[helper cases](../../service_tests/test_desktop_capture_restore.py) cover local
interruptions before copy publication, before settings and after settings; the
separate results above preserve each run's limits.

The [app recovery boundaries](../service/durable-capture.md#recover-onto-another-device-unreleased)
and [private agent inputs](../service/desktop-operator.md#recover-a-capture-device-unreleased)
describe this fixed-policy device replacement. Broader organization/source/policy
migration, complete historical coverage, current index acceptance, L2/L3 and
all six packaged journeys remain open.

## Headless retained capture source delta

This **unreleased** addition is separate from the accepted desktop/Linux source
journey above and from stable 4.44. The [operator and agent guide](../service/headless-capture.md)
documents the exact JSON configuration, bounded local preview and
`--capture-control` requests. An explicit `capture` object binds the approved
tenant, principal, connector, source, grant, namespace and policy. Configuration
alone cannot enroll or resume. Initial enrollment verifies current authority and
creates a paused inbox; existing mode-only policies remain supported under their
default selection limits. Existing mirror configurations do not convert.

The independent runner uses protected file/environment key references, including
an inbox key separate from its API credential. It does not automatically use the
desktop OS store. The shared capture cycle commits selected complete evidence
before opening a service credential/client. Saved activity distinguishes a live
scan from an interrupted process; its report is the latest attempt, not lifetime
coverage. Queue, prefix and source-wide index observations retain their bounded
scopes, and L2/L3 consolidation remains unavailable. Sampled per-process RAM
enforcement, per-inbox limits and aggregate admission under the configured
private state root constrain local work without deleting accepted evidence.

Direct polling uses strict protected credential reads and observes local
paused-to-resumed state between remote polls. On an adopted Linux/macOS host,
the managed path can launch retained intake while service readiness is false,
but preserves runtime/update leases and the update-journal gate. Verified runtime
preflight must advertise `capture_protocol: 1`; older runtimes explicitly refuse
retained configurations. Mirror readiness behavior is unchanged, and managed
configuration snapshots omit absent optional fields for rollback compatibility.

Local backup/inspection use the existing encrypted archive without exporting an
API credential. New-grant recovery stages and authenticates the archive, validates
present producer prefixes, destination and capacity before retiring the old
grant, and refuses reuse of its inbox key. Original organization, connector,
source, namespace and policy remain fixed. An explicit `recovering` record
supports finish/discard after publication failures; successful recovery remains
paused. Headless retirement retains the established inbox, whereas discard is
limited to an unfinished replacement. These are distinct from the native
desktop control names and OS-protected enrollment above.

The initial **seven** real CLI/HTTP/PostgreSQL checks passed in **23.24 seconds**
before the recovery-ordering, protected polling and managed-readiness follow-ups.
`headless-capture-regression-tests.log` then recorded **70 passed in 76.19 seconds**,
including 21 new headless cases and existing desktop, transfer, runner and managed
regressions. The new cases cover actual CLI interruption after local commit and
restart recovery, offline managed intake, old-runtime refusal, paused wakeup,
sampled RAM enforcement, and prefix/collision/capacity/key rejection before old
grant retirement. The application source snapshot is recorded in
`headless-capture-source-inputs.json`, digest
`8e0bac3ab5d6dc042b04523f966fef674868b0d6f6fc9898a439b92638d5dea0`.
Separately, `headless-capture-migration-preflight.log` records **29 passed in
55.54 seconds**, fingerprint
`554868bb00470959202563c8be0ac3d068298bc2438dd2086cada2c5102d4e48`;
`headless-capture-updater-regression.log` records **30 passed in 3.37 seconds**.
The application source digest remained unchanged. These overlapping suites are
reported separately. They are source checks; no installed-artifact or six-target
acceptance is claimed, and the remaining L1 requirements below are unchanged.

## Source and deletion boundaries

The staged service exposes a `durable_capture: "v1"` capability. An administrator
configures custody through the source PUT and approves the device through the
grant PUT before local enrollment. Native `source.configure` accepts
`custody: {source_id, grant_id, keep_accepted: true, pending_limit_mib}`. The client
binds its local encryption to tenant, connector, source, grant, namespace and
capture selection. An ordinary source key cannot grant itself custody or expand
its audience. Source edits require the current version; stale administrative
requests cannot restore removed members. Capture selection, identity and the
dedicated key remain immutable for that inbox.

Forgetting a captured fragment may include adjacent messages. Memory details
provide `capture_forget`, including the observed retained-memory count and scope.
The app confirmation and agent descriptions explain this before deletion. A
fragment family is scoped to the producer file, its generation and the starting
byte of the fragment. This is not semantic forgetting across new generations or
arbitrary re-imports. Ambiguous migration must not invent a new origin identity.

Revoking a capture grant stops ingestion and receipt access. It does not revoke
the API key's ordinary principal rights. Revoking the exact key ends its ordinary
API access; revoking the source removes access to its custody space. Retained
removal discards only the device's local inbox after confirmed revocation. It
preserves original chat files, server memories and the API key's other rights.

The removal helper checks the current grant against the exact saved enrollment.
A refused or expired device credential preserves the inbox. Studio's Connections
page can resolve its matching workspace administrator handle; Sources on this
computer also offers an optional administrator-key field. A private native agent
can supply `retirement_credential` for the same operation. None of these paths
saves a replacement source key or authorizes new capture. A lost revocation
reply is reconciled against current server status. Once a confirmed retirement
record is saved locally, interrupted cleanup can finish offline with no surviving
credential. This fallback is implemented; focused checks and installed platform
acceptance provide separate evidence.

## Local recovery boundaries

Only the first pending enrollment may initialize an empty inbox, before any
intake. A missing initialized database, missing or corrupt protected key, or
changed enrollment binding stops capture visibly; it is never silently reset.
Current files on a fresh device cannot establish past accepted or forgotten
ranges. Recovery needs the matching verified inbox, settings, enrollment and
usable protected key, or an explicitly reviewed migration. OS-sealed keys are
not automatically portable, and server backups do not reconstruct undelivered
local evidence.

Administrator retirement permits explicit discard after a lost device API key;
it does not decrypt a damaged inbox, recover an encryption key or migrate capture.
History repair resets only observations for the whole device and does not start
a scan. It cannot stand in for evidence or key recovery.

## Required before L1 can be released

- Finish acceptance of the encrypted coverage/gap accounting, including selected,
  omitted and unsupported complete-line counts and persistent queue/contact
  observations. Finish acceptance of separately observed index progress and the
  remaining historical coverage work. Join observed, locally accepted and
  server-acknowledged progress without turning unknown history into zero gaps or
  queue age into measured offline duration. Consolidated progress remains unavailable until the
  corresponding L2/L3 work exists.
- Finish acceptance of the bounded preview, filename/session selection, explicit
  retention and per-fragment policy revisions. Complete the broader policy and
  preset contract: current Selected/Conversation/Detailed choices and existing
  Pause do not provide automatic expiry, field redaction or attachment fetching.
  Keep unavailable capabilities explicit and retain reviewed migration requirements.
- Complete packaged archive export/inspection and device-recovery acceptance,
  including protected-key enrollment and interrupted publication/finish/discard.
  The new fixed-policy device/grant replacement does not close those journeys
  or provide migration of the original organization, source identity or capture
  selection. Retain the broader reviewed migration requirement, existing mirror
  behavior and past forgetting decisions; current files alone are insufficient.
- Complete acceptance of the independent headless retained-source enrollment,
  scheduling and lifecycle journey. Its explicit JSON `capture` configuration
  and local controls passed the bounded source checks above; packaged acceptance
  remains open. Configurations without `capture` keep the existing mirror
  protocol. Desktop helper or source-journey proof does not establish headless
  acceptance.
- Complete bounded retained-history behavior and L1 acceptance for backpressure,
  retention and aggregate limits, including interrupted enrollment and current
  permission changes. Existing admission caps and the Linux source journey do
  not close those acceptance tasks.
- Run the complete packaged journey on all six required targets: Windows,
  macOS and Linux, each x64 and arm64. Accept offline pause, refusal of unconfirmed
  discard, administrator retirement, restart during cleanup, lost/corrupt keys or
  inboxes, and verified recovery against the final source and required contracts.
  Keep the normal permission, integrity, recovery and release gates intact.

The coverage and policy items above retain sections 2–3 of the original private
`l1-next-milestone-audit.md` and the public [completion audit](../implementation/completion-audit.md).
The public website and documentation already consume Git sources; no separate
website edit is needed for this checkpoint. Keep those guides aligned with
accepted behavior and actual release availability through the existing flow.

Component checks are maintained in the repository: [persistent observations](../../service_tests/test_desktop_source_status.py),
[local inbox custody](../../service_tests/test_conversation_inbox.py),
[JSONL capture](../../service_tests/test_durable_conversation_capture.py),
[HTTP delivery](../../service_tests/test_capture_delivery.py),
[desktop helper and retirement](../../service_tests/test_desktop_durable_capture.py),
[native controller](../../studio/electron/scripts/test-desktop-sources.mjs),
[server custody](../../service_tests/test_capture_custody.py) and its
[review checks](../../service_tests/test_capture_custody_review.py). Completed
receipts establish their stated scope; this checkpoint makes no new claim of
installed platform or release acceptance.
