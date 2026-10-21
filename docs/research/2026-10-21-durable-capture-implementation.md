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
| Policy versions and administrator controls | A further unreleased batch adds immutable policies bound to grants, reviewed defaults for new grants, and explicit retention or revocation of existing authorizations through the shared hosted/desktop panel and MCP/HTTP. Original-policy archive recovery requires explicit reauthorization. Regression, actual backup/ledger restore, migration, native controller and Linux browser administration checks plus app/native builds passed. The integrated checkpoint's failed health-response expectation is retained; its correction passed the later per-file backfill CI below. Packaged acceptance and existing-device selection/organization migration remain open. |
| Portable inbox archive | Unreleased checkpoint `7aca19e9` exports and inspects encrypted local evidence, and restores a new private inbox under its original binding. Core, helper/controller, migration and Linux app export/restart-inspection checks passed. These checks do not establish the separate device-recovery delta or packaged acceptance. |
| Device recovery | An unreleased source checkpoint re-encrypts an inspected archive for a new approved grant and inbox key, retires the old grant and installs a new paused native source. The original organization/source/namespace/policy stays fixed. Protected intents support explicit finish/discard after interrupted local publication. Source, controller, operator and migration checks plus the three-phase Linux source journey passed. All three earlier failed journeys are retained below; six-platform packaged and full L1 acceptance remain open. |
| Independent headless capture | An additional unreleased delta gives `mnemion-connect` explicit JSON custody and stdin controls for paused enrollment, resume, status, encrypted backup and fixed-policy device recovery. Protected file/environment references replace automatic desktop OS sealing. Local intake precedes service access. Source regression, migration and updater checks passed, including polling and verified managed-runtime integration; packaged acceptance remains open. Configurations without `capture` retain mirror behavior. |
| Encrypted selected inbox | The native controller creates an independent random 256-bit key and seals it through OS credential storage. Selected items and a verified capture checkpoint commit together under AES-256-GCM. Both messages and complete modes use the existing renderer. Messages mode cannot retain a raw transcript or hide raw text in its source evidence. |
| Local capture and scheduling | The normal desktop runner commits available selected JSONL evidence before any service request in a scan. Accepted events survive restart and producer removal/rotation; unfinished tails wait. Missing source files can stop new capture while already accepted evidence remains deliverable. |
| Bounded retained backfill | An unreleased checkpoint commits verified prefixes at existing fragment boundaries and resumes unchanged files on later scans. Per-file work allowances preserve selection and event identities; deferred coverage remains awaiting verification. Focused Python/controller and migration checks, native/app/documentation builds, all 12 CI jobs on `763a8341` and an isolated Linux measurement passed. Packaged acceptance remains open; those checks do not establish the later connection-budget work. |
| Connection intake budgets and rotation | A further unreleased batch bounds local intake cooperatively across files and saves encrypted sweep/cursor state before each attempt. Catalog changes preserve rotation and evidence; archive validation and device-key rotation include the schedule. Healthy intake or delivery backfill gets a five-second follow-up, with a fresh matching receipt required for managed runs. Scoped service/controller and migration checks passed; original setup/assertion failures remain recorded. Current full CI and packaged acceptance remain open. This does not remove history caps or coordinate separate connections/devices. |
| Durable service custody | Explicit administrator consent, immutable source identity and selection for each device grant, current audience/role checks, immutable event receipts and idempotent pages. Existing provider permission leases remain unchanged. |
| Delivery and reconciliation | The runner saves exact pages before delivery, looks up uncertain receipts and resends only the same page. Current revocation and forgetting fences apply to backlog. Revoked grants retain local pending evidence without attempting ingestion; observed revocation also stops later local intake. |
| Private scan observations | Last success, failure, interrupted attempt and next check survive restart. App and native status separate local acceptance, pending content, server acknowledgements, unknown pages, incomplete scans and capacity. Explicit repair preserves damaged diagnostics and resets history for every source on the device to unknown without changing sources, credentials or capture data. |
| Encrypted coverage accounting | The inbox retains per-file prefix observations and one bounded aggregate, with selection counters committed alongside accepted evidence. Missing/changed/unobserved history, continuous non-empty queue start, authenticated contact and receipt acknowledgement remain distinct. This development delta is still under validation. |
| Source index observations | An additional unreleased delta reads current revision/index states for the authorized shared source across devices. It saves partial and completed sweeps separately, with observed generation and time interval. Source, controller and migration checks passed; installed acceptance remains open. |
| Device resource admission | Pending selected payload and actual SQLite database pages have separate per-source and aggregate device limits. New intake also needs free disk headroom. Reducing limits preserves accepted evidence and leaves bounded delivery/forgetting work available. |
| Local history and deletion capacity | The new unreleased delta exposes separate retained-record counters and mutable local history/database quotas. Held-data deletion records bypass lowered admission caps; foreign-fence overflow persists an intake pause without rolling back known purges. Focused service, native controller and migration checks passed; full CI and packaged acceptance remain open. |
| Free-page reclamation | An additional unreleased delta returns unused SQLite pages before intake and after delivery, preserving every logical record. Incremental work and legacy conversion have separate bounds; storage status reports actual bytes and deferred/failure reasons. Focused source, controller and migration checks passed; installed acceptance remains open and reference/history/scope caps remain unchanged. |
| Pause and removal | Pause works offline. Retained removal requires a pause, explicit `discard_local_inbox: true` and confirmed server revocation before local discard. A current workspace administrator can retire the exact saved grant when the device key is unavailable. Its optional `retirement_credential` is used only through the private removal path and never saved by the operation. Recorded retirement can finish cleanup offline without credentials. |
| Forgetting and recovery | One captured fragment's raw evidence, projections, parts and retained revisions are withdrawn atomically. Late deliveries stay denied. Current negative state and grant revocations survive restoring an older backup. Revoked custody also stops new background inference and vector publication. |

## Current limits and observations

The local queue defaults to 256 MiB of pending selected payload per source,
configurable from 1 to 1,024 MiB, with a 1 GiB aggregate pending limit on the
device. Database admission defaults to 512 MiB per source, configurable from
64 to 2,048 MiB, with 2 GiB across the device, counting actual SQLite pages.
New intake requires at least 512 MiB free disk plus room for its transaction.
Each inbox defaults to 100,000 entries separately for accepted events,
producer-event identities, producer-fragment references and deletion records;
the new history control allows 1,000–500,000. Producer scopes remain capped at
10,000. The desktop source RAM allowance
defaults to 256 MiB and accepts 128–2,048 MiB, with sampled enforcement.

A limit below current usage blocks new admission without trimming the queue.
Inspection, ordinary delivery and held-data forgetting remain subject to usable
disk and current authorization. The [new deletion-capacity correction](#deletion-fences-and-history-limits-source-delta)
retains held-data denials above lowered limits and pauses intake when additional
foreign fences cannot fit; focused source checks passed and packaged acceptance remains open.
Bounded delivery bookkeeping may use reserve above a
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
preserves each grant's immutable policy; the local enrollment
binds the same policy. Explicit-policy fragments carry `capture_policy_revision`,
checked by both inbox and service alongside the approved mode/path and declared
file boundary. The collector enforces record-size admission. Changing an existing
inbox's selection requires reviewed migration. Legacy sources without a policy
keep their existing
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

## Free-page reclamation source delta

This **unreleased** delta is separate from the earlier headless checkpoint.
New inbox creation enables incremental vacuum.
`capture_storage.py` runs under the existing inbox lock, outside an active
transaction, from the shared capture cycle before intake and after delivery.
Each incremental pass allows 64 MiB of returned pages and a 0.5-second
cooperative time budget. Progress checks can interrupt SQLite work; this is not
an instantaneous hard deadline for filesystem operations.

An older database converts with whole-database `VACUUM` only after both pending
events and pending pages have settled through confirmed storage or forgetting.
It requires free disk of at least twice the database size plus 1 MiB, uses
temporary files on disk and the same cooperative time interruption. The
incremental byte allowance does not bound this conversion. Every logical event,
receipt, checkpoint, producer identity and negative fence remains; conversion
commits or rolls back without a retention
change. Small free-page amounts can remain available for SQLite reuse.

The optional `capture.storage` observation gives exact database and remaining
free-page bytes after the final pass, plus reclaimed bytes accumulated over both
passes in that scan. Final-pass state is idle/reclaimed/deferred/failed, with
bounded time, byte, disk-reserve, pending-legacy or SQLite-failure reasons as
appropriate. Older absent/null observations remain unknown. The native validator
checks consistency with the capture report; Studio shows the result in its
expandable coverage/history details. Cleanup status remains independent of
delivery success and does not invoke a model.

`capture-storage-regression-tests.log` records **110 passed in 54.72 seconds**
across storage, inbox, encrypted archive/transfer, persistent source status,
desktop durable capture and headless durable capture. This includes backup after
cleanup and rejection of invalid or content-bearing observations. The initial
10 storage cases passed in 2.36 seconds and overlap this regression; the counts
are not added.

Separately, `capture-storage-controller-tests.log` records **58 passed, zero
skips, in 197.818285 ms**. `capture-storage-migration-preflight.log` records
**29 passed in 51.72 seconds**, fingerprint
`894b0b916aa612e9b7d3bdc73dafbb427f0fd7827b450c56085bb6c7b51706e9`.
Whole-tree Ruff lint and formatting checks passed across 625 files.
`capture-storage-source-inputs.json` records the pre-check source digest
`04420cd40d87b8a5d9ace10ea07cf6fbe841575c39d105a4ae0e83e42145774b`.
These are scoped source checks; all installed-platform proof, release and full
L1 acceptance remain open.

Returning free pages does not prune any logical history, lift the
100,000-event/reference or 10,000-scope caps, add expiry or satisfy the remaining
bounded-history and backpressure requirements. The
[operator guide](../service/durable-capture.md#reclaim-unused-database-pages-unreleased)
describes the observed fields and deferred behavior.

## Capture policy versions source delta

This **unreleased** batch adds `capture_policy_versions: "v1"`. Migration 033
preserves each existing source and grant as policy version 1, including original
mode-only policies. Policy versions are immutable; a reviewed transition changes
the source default for new grants. Existing grants are explicitly retained on
their original policies, including permission for future capture, or all
unrevoked grants are revoked. Source identity, custody space, audience, accepted
memories and deletion fences remain unchanged; no local queue is rewritten.

The shared hosted/Studio administrator panel and `capture.source.list`,
`capture.policy.review`, `capture.policy.versions` and `capture.policy.change`
use the same server contract. Review covers the entire unrevoked-grant set while
source/device/history pages remain bounded. A change requires the current source
edit version, review token and explicit consent. Exact retries keep the same
transition UUID and request; replay does not revoke later-created grants.
The [administrator procedure](../service/durable-capture.md#manage-source-defaults-and-device-authorizations-unreleased)
documents the request envelope and confirmation steps.

An archive's exact original policy can be reauthorized on a new grant with
`previous_grant_id` and `confirm_previous_policy: true`. Local recovery still
preserves that archive's original selection and identity. The current custody
recovery ledger includes immutable policy history and each grant's bound version;
validation rejects unknown or conflicting versions and a default downgrade.
An older ledger maps each source and grant to its original version 1. This does
not provide in-place selection/organization migration or remove the local
enrollment guard against existing capture history.

The batch also corrects revocation observation when row-level security hides a
retired source/connector/device authorization. A narrowly scoped SQL boolean
checks only the current tenant/principal and exact device key/grant. A known
inactive authorization returns `403 capture_grant_inactive`, allowing the runner
to stop later local intake while preserving its inbox; an unknown grant remains
404. No hidden source or grant metadata is returned by this fallback.

`capture-policy-versions-source-inputs.json` pins **547 runtime files**, digest
`6f4f061189f70c28504e88422ff0aabd961934f2a77bc73e5b0ce832be145e55`.
`capture-policy-versions-regression-tests.log` records **97 passed in 156.67 seconds**.
The later `capture-policy-versions-final-tests.log` records **12 passed in
17.50 seconds**: 11 repeated policy cases and one new actual `pg_dump`/restore
scenario, for 98 distinct affected Python cases across these two runs. A backup
containing policy 1 was restored with a current ledger containing policies 1–3.
The source kept default 3, the original/recovered grants kept policy 1, a later
grant kept policy 2, and the deleted memory stayed forgotten. The run also
rejects a version-2 ledger grant missing its explicit `policy_version`.

Separately, `capture-policy-versions-migration-preflight.log` records **30 passed
in 100.49 seconds**, fingerprint
`2598c9e18d8436d8c279f1f34bfaf9851d6b3ba2416cc044895da87a6a5136af`.
`capture-policy-versions-native-tests.log` records **58 passed, zero skips, in
213.888783 ms**, and `capture-policy-versions-native-build.log` records the
successful native build. The app build passed. No runtime edits intervened
between the source receipt and these checks. Whole-tree Ruff checks passed,
with 629 files passing the formatting check; whitespace checks passed.

`capture-policy-versions-browser.receipt.json` records a passing Linux source
journey at **07:15:47 UTC**, with the same runtime digest. It used the actual
component, TypeScript SDK, HTTP and PostgreSQL in an isolated fixture: three
policy-1 grants stayed on policy 1 after the default changed to 2; individual
revocation left two unrevoked grants; reviewed revoke-all created policy 3 and
left none. History remained `[1, 2, 3]`, with source and space IDs unchanged.
At widths **1,280 and 390 pixels**, there was no horizontal overflow or error
alert, and the edit guard cleared after completion. Product console errors were
zero; one fixture-only `favicon.ico` 404 remains recorded. Fixture database and
browser were closed, temporary credentials were removed, and the receipt records
zero production writes and paid model calls. This is Linux browser source proof;
installed-platform acceptance remains open.

The first eight-case run retained **seven passes and one fixture failure**:
the test queried the nonexistent `memories.content` column. The test was
corrected. The first browser fixture failed to import its private harness module;
its launch path was corrected before the successful journey. Both fixture
failures remain recorded separately from the passing results.
Earlier baseline `fc4e25ca` passed all 12 jobs in
[CI 39555330786](https://github.com/Perseusxrltd/mnemion/actions/runs/39555330786);
that run predates this policy batch. The integrated policy checkpoint `09f259e1`
then failed [CI 39561318253](https://github.com/Perseusxrltd/mnemion/actions/runs/39561318253).
The run finished with nine successful jobs and three failed service jobs.
`capture-policy-versions-ci-313.log` records **one failure, 1,928 passes and
15 skips**, with 87% coverage: the exact health-response expectation omitted
the newly advertised `capture_policy_versions: "v1"`. The inspected Python 3.12
log records one failure, 1,935 passes and eight skips; Python 3.14 records one
failure, 1,928 passes and 15 skips. All three failures were that same expectation.
The later per-file backfill checkpoint corrects it while retaining the exact assertion and
response-byte bounds. The original failed CI remains evidence; earlier focused
passes do not make it an accepted checkpoint.

These source results do not establish six-package archive recovery, complete
history, full L1 or release acceptance. Existing-device selection and
organization migration remain open, as do the remaining policy, coverage,
retained-history and backpressure requirements. Stable 4.44 and all earlier
checkpoint proofs keep their original scope.

## Bounded retained backfill source delta

This **unreleased** delta gives each producer file its own continuation window:
64 newly rendered fragments or 32 MiB of newly parsed input per pass. The input
allowance is the smaller of 32 MiB and one-eighth of remaining pending-payload
headroom, with a 1 KiB floor. Checks occur at existing fragment boundaries, and
a soft stop reserves the final quarter of that file's configured scan time for
verification. A finishing fragment, prefix hashing and read-ahead prevent these
allowances from being hard byte, RAM or global scan-bandwidth ceilings.

Selected evidence, verified prefix and selection accounting commit together.
An incomplete checkpoint resumes even when file metadata is unchanged. The
renderer keeps standard fragmentation and event identities in both capture
modes; retained-prefix reuse avoids decrypting/updating every old reference.
Prefix verification remains required, and mirrors keep full-inventory behavior.
`capture_scan_pending` identifies normal incomplete backfill when no source or
delivery error takes precedence; already accepted events can finish delivery.
Deferred scopes stay in the awaiting-verification count without adding failed
scopes or interrupted intervals. Removed unexamined suffixes remain unresolved
history, including after a later failed scan.

Native saved status now distinguishes `phase: "backfill"` from attention and
completion. It requires a validated incomplete `capture_scan_pending` report
with successful delivery contact; it preserves prior success/failure observations
and the actual next scan time after restart. Both app source panels show
**Backfilling** for this state. Pending and already delivered batches are
eligible, while missing/invalid reports and actual errors cannot claim this
progress. Headless activity retains its separate `finished` state and incomplete
report. The saved-status/controller cases cover reopening, history and schedule
preservation, and invalid claims.

`capture-windows-initial-tests.log` records **eight passed in 27.95 seconds**.
The cases compare both modes against one-pass identities, reopen real inboxes,
exercise the soft deadline and duplicate ACP events, preserve lost suffixes
including on failure, and resume an archived partial checkpoint. A real headless
CLI run accepted 64 events offline, reached 128 online and completed at 130,
draining delivery between windows. These initial checks predate the native
saved-status delta.

`capture-windows-final-source-inputs.json` pins **547 runtime files**, digest
`e8d85cf21d0afc21bf1bd5b8dea148d73111ba9ab9e9a0972e6bce7a4ebf23f4`.
`capture-windows-final-regression.log` records **136 passed in 137.99 seconds,
no skips**. This includes the eight initial backfill cases, existing
render/inbox/coverage/delivery/archive/recovery/headless/policy regressions, new
saved-status cases and the corrected exact health-response expectation. The
initial eight are not additional passes. The runtime digest still matched.

Separately, `capture-windows-migration-preflight.log` records **30 passed in
116.80 seconds**, uncached, fingerprint
`905cf8022901b54ab688c4ee1244d5a2308f6b1ab7130d4642a4096e44b81bf1`.
`capture-windows-native-tests.log` records **64 passed, zero skips, in
524.335982 ms**; `capture-windows-native-build.log` records the successful native
build. The app/documentation build, 630-file formatting and whole-tree Ruff
also passed. `capture-windows-final-ci-status.json` records **all 12 jobs passed**
for checkpoint `763a8341` in
[CI 39565726199](https://github.com/Perseusxrltd/mnemion/actions/runs/39565726199).
These checks predate the connection-budget/cadence batch below and do not
establish packaged acceptance.

With the final source, `window-benchmark-final-20261021/result.json` measured
**40,000 synthetic rows / 33,588,890 source bytes** across three reopened passes
in an isolated Linux process. Total observed time was **3.48 seconds**, peak RSS
**67.57 MiB**, and final pending selected payload **67,078,418 bytes**. An unchanged
follow-up scan added no events. The receipt records no HTTP requests, production
writes or paid model calls. The earlier `window-benchmark-20261021/result.json`
measurement, before the saved-status changes, remains recorded at 3.26 seconds
and 67.58 MiB peak RSS. These are synthetic local intake measurements, with no
delivery; neither establishes a resource guarantee or installed acceptance.

The 100,000 event/reference and 10,000 scope caps, existing byte limits and
retained-history requirements remain. That checkpoint did not establish
multi-file fairness or aggregate scan bandwidth. All six packaged targets and
full L1 acceptance remain open. It does not change stable 4.44 or any roadmap
requirement status.

## Connection intake budget and rotation source delta

This **unreleased** batch adds a `ScanBudget` to each retained
connection's local intake pass: 256 producer-file attempts, 256 rendered
fragments, 64 MiB of actual input reads including prefix verification/read-ahead,
and 30 seconds or the configured per-file maximum when smaller. Failed attempts
also consume the allowance. The timer begins before catalog work, with at least
one attempt permitted after a slow catalog. Current fragment completion and
verification can overrun the cooperative limits; the existing per-file window,
hard per-file deadline and exact admission checks remain. Delivery, cleanup and
work from separate connections/devices are outside this shared intake budget.

`CaptureSchedule`, stored as encrypted `coverage-schedule` metadata, contains a
catalog hash, remaining sweep slots and last attempted scope. Stable scope-ID
rotation resumes after that cursor, including after process restart. A changed
catalog restarts the sweep but retains the cursor and evidence. `scan_started`
atomically saves the attempt/cursor and checking observation before file reads;
it does not assert acceptance. Unvisited work stays deferred, actual interrupted
attempts remain distinguishable, and previous failures cannot become invisible
merely because their files were not attempted in the current pass.

Archive auditing validates the schedule schema and device-key rotation
re-encrypts it with the other observations. The original capture/event identities,
policy, checkpoints, receipts and deletion fences remain.

The shared `backfill_pending` predicate requires an incomplete report, successful
delivery contact, no failed optional control report and one of two consistent outcomes:
`capture_scan_pending` with intake incomplete, or `capture_delivery_pending`
with intake complete and delivery incomplete. The latter covers queued events
or unfinished forgetting sweeps; index observations remain separate. Both are
validated native `backfill` progress and preserve prior success/failure history.
Native status saves its next scan five seconds after finish; direct `--watch`
uses the same follow-up interval. Managed runs require
a fresh private `capture_backfill` receipt from the actual launched runtime,
matching connector ID/runtime version, exit 2 and `completed: false`. The old
receipt is removed before launch. Missing/invalid receipts and capture-aware
runtimes without the field keep normal polling. Partial work does not become a
successful scan or new successful-scan provenance. Runtime/update leases and
pause/resource/admission checks remain; failures, paused/complete scans and
legacy mirrors keep ordinary polling. `remote_sync: false` disables optional
triggers/reporting while preserving delivery and prompt continuation. This is a
fixed cadence, not a new profile.

`capture-scheduling-initial-tests.log` records **11 passed and one setup error in
28.88 seconds**. The real headless case did not start because its imported
`conversation_source` fixture was missing. The fixture import was corrected;
the original error remains evidence.

`capture-scheduling-cadence-tests.log` then records **14 passed and two failures
in 88.07 seconds**. The 257-file case incorrectly expected one pass to deliver
everything despite the existing four-page/50-event delivery limits; local
status showed 200 stored and 57 pending. The failure-polling case expected exit 0
after Ctrl-C, which intentionally exits 130. These assertion failures are
retained. Review also identified that healthy remaining delivery used ordinary
polling and appeared partial; the added `capture_delivery_pending` behavior
addresses that separate gap. That partial run included a passing 97-record
watcher case, which is not separate final-candidate evidence.

`capture-scheduling-final-source-inputs.json` records this source checkpoint's
**547 runtime files**, digest
`2cdbb6099d4eb3fcf4e84a53a8ce5ca5d8124a31a6237570b83b5033ad188abe`.
`capture-scheduling-final-native-tests.log` records **68 passed, zero skips, in
564.473063 ms**, and `capture-scheduling-final-native-build.log` records the
successful build. Separately, `capture-scheduling-final-migration-preflight.log`
records **30 passed in 138.30 seconds**, fingerprint
`cb6a8680d74fda612ec00361111559be9f598c59273bcd8a410973c0d456a5d4`.
`capture-scheduling-final-regression.log` records **149 passed and one failure
in 229.89 seconds**. The CLI fixture assumed the 256-file allowance would always
be reached; the cooperative 30-second limit correctly stopped that loaded run
at 174 files. Runtime code and its digest are unchanged. Only that end-to-end
case was rerun in `capture-scheduling-watch-retry.log`: **one passed in
42.39 seconds**. The corrected fixture uses nine files of 64 small records and
accepts any positive first pass within budget. Its real HTTP/PostgreSQL watcher
recovered from offline intake, reported both `capture_scan_pending` and
`capture_delivery_pending`, then completed with **576 stored events, zero pending
and zero uncertain intervals**.

Together, the 149 unchanged-source results and corrected-case retry establish
**150 distinct affected service cases passed**. The original full-run log remains
failed; the earlier 11- and 14-pass runs are not added to this total. Final input
verification still matches the 547-file digest above. These checks, the 68 native
controller cases and 30 migration cases establish their source scope.
`capture-scheduling-qualified-tests.receipt.json` records that qualification,
the original failed full log, verified source inputs, and zero production writes
or paid model calls. Current full CI, total event/scope/history/storage
requirements, all six packaged targets and full L1 acceptance remain open.

The earlier `763a8341` source, all 12 CI jobs and Git-driven website synchronization
were verified separately from this unreleased batch.
Earlier per-file proof and the retained policy-CI failure keep their original scope.

## Deletion fences and history limits source delta

This **unreleased** correction has focused service, controller and migration
qualification; full CI and packaged acceptance remain open. On scheduling checkpoint
`6b883fba`, `capture-fence-capacity-initial-tests.log` records **four failed in
2.92 seconds** using real encrypted inboxes. Lowering the event allowance blocks
forgetting already-held pending or settled lineages, and blocks applying a
receipt that confirms those accepted items were forgotten. A full deletion-record
allowance can also make a fence for a lineage absent from the local inbox prevent
held-data deletions from committing for that authenticated page.

The [inbox correction](../../mnemion/connectors/conversation_inbox.py) retains an
authenticated denial for any already-held lineage even above a lowered event
limit, including receipt settlement as forgotten. When an unheld foreign fence
cannot fit, its page still commits known purges, retains the retry cursor and
saves an encrypted intake pause. A directly supplied overflowing fence restarts
the sweep so an earlier lineage cannot be skipped. Existing accepted delivery
is still attempted. Raising capacity alone does not clear the pause: a later
authenticated sweep must finish successfully. No deletion history is removed
to make space. Archive inspection validates the pause rather than silently
resetting malformed metadata.

Native `custody`, headless `capture` and preview settings now share strict integer
`history_limit_events` (default 100,000; 1,000–500,000) and
`database_limit_mib` (default 512; 64–2,048). They preserve the source, grant,
inbox key and policy identity; preview fingerprints include the settings.
Pending-content defaults and aggregate limits remain unchanged.

The [history model](../../mnemion/capture_history.py), app's advanced status and
headless saved report expose `mnemion-capture-history-v1`: `events`,
`producer_events`, `fragments`, `scopes`, `delivery_pages`, `denials`,
`event_limit`, `scope_limit`, `database_bytes`, `database_limit_bytes`,
`fence_history_blocked` and `over_limit`. The event allowance applies separately
to events, producer events, fragments and denials. Scope allowance remains
10,000; delivery pages are observed separately. Database allowance can be
reduced by aggregate device usage. `over_limit` means strictly exceeded;
the persistent fence pause can also exist without it. Older absent/null history
is unobserved. `capture_fence_capacity` is an attention condition, not healthy
five-second continuation, and a blocked sweep cannot report delivery complete.

`capture-history-inbox-tests.log` records **27 passed in 8.69 seconds**, covering
the original four failures and existing inbox cases. The later combined run,
`capture-history-final-regression.log`, records **166 passed in 307.41 seconds**.
It includes actual HTTP overflow with accepted delivery and later held-data
deletion, persistent pause and full-sweep recovery, authenticated archive and
new-key restoration, and desktop/headless quota changes preserving identity.
The final native controller run records **77 passed, zero skipped** in
645.19 ms; **30 migration checks passed in 170.80 seconds**.

The first native run retained one failed test assertion: it expected the detailed
capture reason at the top-level activity, which intentionally reports `partial`.
The corrected check verifies that activity and the nested `capture_fence_capacity`
reason, normal retry interval and persistence. No runtime behavior was changed
to satisfy that assertion. The final service qualification below replaces three
cadence test cases and adds one journal case, for **167 distinct service cases**.
Original failures remain retained. Lifetime history, page and archive bounds,
coordination across independent devices, migration, six packaged targets and
full L1 acceptance remain open.

The preceding scheduling source checkpoint and Git-driven website synchronization
([39571717286](https://github.com/Perseusxrltd/mnemion/actions/runs/39571717286)) passed.
Its [CI 39571717128](https://github.com/Perseusxrltd/mnemion/actions/runs/39571717128)
finished with ten successful jobs and failures on Python 3.13 and 3.14.
Both failed three mocked cadence cases because the full pytest/coverage process
exceeded the capture child's default 256 MiB allowance before the mock scan ran.
The cadence test now isolates that unrelated process guard and asserts both
mock scans ran; the real CLI guard remains covered by its independent subprocess
test. Python 3.13 also exposed a journal privacy test that assumed ten bounded
batches would always finish 53 records. It now allows at most one batch per
record plus completion, requiring forward progress in every unfinished batch.
Product memory, privacy-scanning and batch-time limits are unchanged.
`capture-history-ci-regressions.log` records **10 passed in 18.00 seconds**,
including the four corrected cases and six existing headless-control checks.
The original CI logs remain preserved. Replacement full CI is still required.

## Installed capture boundary gate

The existing installed-hosting gate already includes capture enrollment through
the app, offline intake, app restart, encrypted archive export, administrator
retirement and recovery onto a separately authorized device. Two additional
launches now extend that gate through the [native boundary probe](../../studio/electron/native-capture-boundaries-probe.ts).
They use the installed engine's private agent controls and the real app,
PostgreSQL service and OS credential store in a disposable workspace.

The new journey enrolls a source agentically, changes its history and storage
limits through the app, accepts a complete message beside an unfinished UTF-8
record, completes that record, and rotates the log after another unfinished
tail. It checks exact accepted event IDs, fragment byte ranges and digests,
policy revision, stable queue age, and the unresolved bytes left by rotation.
Completing an open fragment produces another immutable event revision; the
earlier accepted revision is retained. An audit query uses `max_per_source: 0`
to inspect every matching fragment. Ordinary recall keeps its existing default
of one result per original source.

A [loopback-only relay](../../studio/electron/native-capture-relay.ts) drops a
reply only after the real service has committed and completed its response.
Later capture traffic remains unavailable until the next launch. The second
launch must reconcile that saved page with a receipt read, without another page
write or new memory revision. It also checks separately observed indexing,
reader revocation while queued, forgetting both revisions of a fragment,
replaying its original delivery page, and a reviewed policy transition that
revokes the old device's delivery authority. The administrator then retires the
paused device through the app while its later accepted message is still queued.

These checks are wired into the normal six-target
[installed-hosting script](../../studio/electron/scripts/smoke-installed-hosting.mjs).
Adding the script is not packaged acceptance. The corrected private Linux source
preview passed both launches and all 19 required boundary checks against 550
runtime inputs, fingerprint
`cf684aa970dccf99689c3fa00e47b7421c8a573c210b62d3b150ddc11eb83964`.
It used the real UI, helper, local service and libsecret, with no production
memory writes or paid model calls. Its failed earlier observations are retained:
an endpoint-bound login handle was correctly refused as a transferable key;
the second launch needed to await normal host startup; and an audit query needed
to request all fragments instead of the ordinary grouped recall. TypeScript
builds initially caught missing optional-value guards in the probe itself.
Those were fixture corrections, not weakened product checks. All six packaged
runs remain pending; no new release or L1 completion is claimed here.

## Independent native engine capture lifecycle

The independent connector is now reachable through `mnemion-service connect`
and the bundled `mnemion-engine connect` entrypoint in development source.
Both use the existing `mnemion-connect` parser options and execution body.
Capture controls still receive bounded JSON on private stdin, with credentials
and encryption keys supplied through protected references. Importing the
service command parser does not import the full connector implementation.
Public 4.44.0 does not include this new command or retained capture.

The normal installed-hosting gate now includes an independent connector phase.
It creates no desktop-managed source and starts the actual engine with the
`connect` command. Its approved, paused enrollment generates a private inbox
key, then keeps one accepted memory through two offline watcher launches, even
after the original producer file is removed. Offline pause, encrypted backup
and authenticated inspection preserve that pending evidence. A changed key
and a missing initialized database each refuse to reset or replace the inbox.
The original queued memory later arrives once, with its identity and version
intact.

The phase then forgets that memory on the server, restores the older pending
archive to a new device grant and encryption key, and checks the current
deletion fence before any repeat page write. It captures a new memory, retires
both grants and cleans up the disposable fixture. This extends the required
six-target gate; adding it is not evidence that the packaged targets passed.

The corrected Linux source preview passed all 13 phase checks with the real
app, service, CLI processes, PostgreSQL and OS key store. Its 552 runtime inputs
have fingerprint
`38e9c143ced506a6bfaf5d959182772384ac39f16371757db253b471a398a2ab`.
The earlier failed preview is retained: the synthetic Codex file omitted its
session header and was correctly counted as unsupported. Only the fixture was
corrected. Fourteen entrypoint cases and six existing headless-control cases
passed; the fresh migration preflight passed all 30 cases. No production memory
writes or paid model calls occurred. Installed acceptance remains pending.

The [headless guide](../service/headless-capture.md) documents the shared
entrypoints and actual package locations. A direct watcher still needs its own
startup/restart handling. The existing `--watch --managed-state` path follows
verified runtime updates on an adopted Linux/macOS host; this command does not
add standalone Windows watcher supervision or automatic restart.

## Damaged inbox controls and lightweight-client correction

This further **unreleased source delta** fixes a reproduced local-control bug:
a missing or malformed enrollment record, or altered protected-key ciphertext,
previously prevented saving a pause. An exact pause or unchanged source now
preserves its accepted evidence and existing failure when saved settings remain
readable and valid. An unchanged damaged sibling cannot block another source's
controls. Resume, other edits and retirement retain their validation; this does
not repair an unreadable settings file or reset an inbox.

The original three failing pause cases remain in the private evidence. The final
scoped run passed **67** cases covering the new damage controls, scheduling,
encrypted inbox, command entrypoints and headless controls. A fresh migration
preflight passed **30** cases. The Linux source boundary journey now passes
**24** checks across two real Electron launches, including actual app/agent
pause after missing or damaged enrollment/database files, unchanged keys and
evidence, refused invalid enrollment resume, and reopening the accepted queue
after restoring only the exact matching fixture files. The qualified receipt
`capture-damage-qualified-preview.receipt.json` pins 555 runtime files to
`a24e8375500a4cf7f3ac8d0d765eb92dff6ac2e48454581648195e0808fc4610`.
No production memory writes or paid model calls occurred.

The first complete [six-target native run 39588502974](https://github.com/Perseusxrltd/mnemion/actions/runs/39588502974)
failed on every target during the lightweight client suite, before packaging.
Ordinary connector imports unnecessarily loaded the encryption runtime, which
is deliberately absent from that client. Shared errors and pure scheduling
decisions now live in lightweight modules, preserving their previous import
paths. The exact locked Python 3.13 client environment passes **235** cases with
**13** platform skips and no encryption dependency installed. The normal CI
Studio job now checks that environment before the six-platform packaging gate;
maintenance monitoring also retains independent desktop validation failures.

These results establish the stated source checks only. A corrected six-target
packaging run, broader damaged-key/recovery acceptance and the remaining L1
contracts are still required. Public **4.44.0** does not include this milestone.

## JSON field exclusions and installed capture navigation

This additional **unreleased source batch** gives app and agent users an optional
`exclude_fields` list in a `mnemion-capture-policy-v2` policy. Up to 32 distinct
literal ASCII field names are normalized and sorted; matching JSON keys and
their values are removed recursively before retained payloads or readable
projections are created. The same rule applies to explicitly selected mirrors.
It leaves producer files and string contents untouched, including JSON embedded
inside strings. It is not a general detector of secrets in conversation text.

Existing v1 policies omit an empty exclusion list, preserving their exact
serialized policy and fingerprint. Reserved identity/structural names cannot be
excluded directly. A field-selection limit fails visibly before accepting that
fragment; previously accepted evidence and checkpoints are retained. Preview
uses the same bounded transformation and reports its capability explicitly.
New choices require a new preview and approved policy; older memories, queued
evidence and backups keep their original policy. Existing-device selection
migration remains a separate requirement.

The initial dedicated run recorded **12 passes and one failure**: the new
work-limit error was collapsed into a generic source-unavailable message. The
product now preserves that reason through the helper and app; the corrected,
expanded suite passed **15** cases. These include frozen v1 compatibility,
both capture modes, explicitly selected mirrors, untouched producer files,
retention of ordinary string values, field/depth work bounds, original-prefix
preservation and actual encrypted archive inspection/recovery. A separate
affected service run passed **73** cases, native controller checks passed **79**,
and a fresh migration preflight passed **30**. Native and app/documentation
builds passed. These are source results, not six-platform acceptance.

The preceding general [CI run 39592497905](https://github.com/Perseusxrltd/mnemion/actions/runs/39592497905)
passed all 12 jobs on `d9b40cca`. The corresponding
[six-target run 39592777333](https://github.com/Perseusxrltd/mnemion/actions/runs/39592777333)
passed its 12 prerequisite jobs but failed all six installed-app jobs. Unlike
the earlier thin-client failure, it reached the installed hosting checks. The
completed logs show all six failures stopped at `capture-enroll`, waiting
for workspace controls while the preceding packaged-documentation check had
left the app on Help. The capture dispatcher now explicitly returns to the
workspace, matching the ordinary host probe. Acceptance guards and authorization
checks are unchanged. A new isolated source harness enters that actual
dispatcher from Help so it exercises the formerly missed transition.

The new source journey passed **31** checks across three real Electron launches:
enrollment, offline intake, reopening the OS-protected key, delivery after
producer-file removal, portable archive inspection and recovery, another
restart, later selected capture and fixture cleanup. Each launch began capture
validation from the bundled Help page. The reviewed field policy survived the
encrypted archive and recovered grant; excluded text was absent from delivered
content while selected messages remained available. All launches exited cleanly
and the private PostgreSQL host stopped. There were zero production memory
writes and zero paid model calls.

`capture-fields-qualified-preview.receipt.json` pins **556** runtime inputs to
`502ad7fa5a93fe0f4a6f2e8d2c0ac95443e5d1305faab93e5de2b74f277949ab`.
The subsequent [general CI run](https://github.com/Perseusxrltd/mnemion/actions/runs/39598649170)
passed all 12 jobs on `8aacc859`. Its [six-target validation](https://github.com/Perseusxrltd/mnemion/actions/runs/39598747700)
finished with 15 successful jobs and three failures. Both Linux architectures
and Apple Silicon completed their installed-app journeys. Both Windows jobs
failed during boundary replay because the probe used Chromium `safeStorage`
to decode a source key protected by the app's direct Windows DPAPI backend.
Intel macOS completed the desktop capture phases, then failed when its
independent connector emitted an unstructured diagnostic. These are preserved
failures, not full packaged acceptance; the corrections and diagnostic work
below are later source. Public **4.44.0** and the full L1 requirements remain.

## Saved-key controls and platform validation

This **unreleased source batch** keeps otherwise-valid saved sources readable
when their expected credential strings are missing or damaged within the
existing size bounds. An operator can inspect and pause the source or control
another unchanged source. Whole-file JSON, public settings, credential types,
unexpected credential roles and oversized fields retain their validation.
New enrollment, resume and other edits still require valid protected settings.

The private pause operation writes only the selected source's disabled flag
under the current settings revision and lock. It reads current disk records
instead of saving cached credentials, so stopping a source cannot restore a
key that disappeared while the app was open. This does not turn file deletion
into immediate API-key revocation: an already running operation may hold a key
in memory. Server revocation remains the authority for ending its access.

Administrator retirement can also proceed after loss of the local API or inbox
key. The original tenant, connector, source, grant, namespace, policy, path and
principal must still match enrollment, whose saved key digest must retain its
valid format. Current server revocation is required before deleting accepted
local evidence. This path grants no capture, re-enrollment, decryption or
migration authority, and never creates a replacement inbox or key.

The original six damaged-key cases failed during settings load; that baseline
is retained. The final affected service run passed **80** cases, the native
controller run **88**, and fresh migration preflight **30**. They cover missing,
malformed and junk-suffixed credentials, unrelated-source controls, current-disk
pause, refused resume, unchanged accepted evidence and current administrator
retirement. Mismatching original enrollment or malformed enrollment digests
still refuse retirement before a remote request. The service and migration
inputs remain unchanged since those checks. The expanded controller suite also
covers the observation-recovery correction below.

The boundary probe now uses the app's actual platform credential backend for
both saved source keys and its private fixture keys. This corrects the diagnosed
Windows backend mismatch without changing product encryption. Quota edits wait
for their actual enabled form controls. Independent connector failures retain
bounded command/code-location diagnostics without printing exception messages,
private paths or credentials; unstructured output still fails validation.
Six focused diagnostic checks and the native build passed. The Intel macOS
failure is not yet diagnosed or accepted.

The expanded source boundary journey requires **29** checks, including a real
restart with missing API and damaged inbox keys, refused resume, exact-key
recovery preserving accepted evidence, and administrator retirement after a
second key loss. Its first local attempt stopped before enrollment because the
isolated libsecret control socket exceeded Linux's path limit; the next exposed
the quota-form timing assumption. A separate attempt timed out while the private
harness observed host startup, before capture validation. These failed fixtures
remain intact. The private harness now retries only that exact read-only status
timeout within its original startup deadline; product limits are unchanged.

A later run passed all ten enrollment checks, then exposed an actual recovery
status bug. Exact restored keys and accepted inbox/enrollment bytes verified,
but the controller still showed unknown history because it had loaded while
keys were missing. A focused regression retained one pass and one failure.
After a confirmed pause changes protected credentials or the status epoch, the
controller now rereads only that source's matching saved observations. It keeps
the source paused and leaves other live activities alone. Different keys do not
recover the old report. The complete 88-case controller run passed after this
correction; the original failing native fixture remains intact.

The updated independent headless source journey passed all **13** checks in a
real Electron launch through the official dispatcher from Help, with actual
CLI processes, PostgreSQL and libsecret. Offline process restarts, encrypted
recovery and later deletion fences passed; its host stopped cleanly, with zero
production memory writes or paid model calls. The qualified receipt is
`capture-key-controls-headless-qualified-preview.receipt.json`.
That headless proof pins the preceding `9c3e5a91` runtime digest; the subsequent
change is confined to the desktop controller and its regression fixture. The
final boundary preview passed all **29** checks across two actual app launches,
including restart, exact-key observation recovery and administrator retirement.
Both launches exited cleanly and the private PostgreSQL host stopped, with zero
production memory writes or paid model calls. Its qualified receipt,
`capture-key-controls-qualified-preview.receipt.json`, pins **557** current
runtime inputs to
`0137e830971628769eab164a68b25995b0fb4b5b676939d86ba4168eecaa770e`.
Complete six-target packaged acceptance and the remaining L1 requirements
remain open. No new release is claimed. The batch is on main at `9095372a`.
Website synchronization completed successfully without a corporate site code
deployment.

### Native matrix checkpoint

[Native run 39613577682](https://github.com/Perseusxrltd/mnemion/actions/runs/39613577682)
uses frozen source `9095372a7b56679e8ab8d4e18bb59d32721a3746`.
Linux x64/ARM64 and Windows x64 jobs passed; Windows ARM64 remains pending.
Intel macOS failed in its first headless preview with unclassified stderr.
Apple Silicon was cancelled before runner assignment; GitHub annotations
confirm hosted capacity prevented that execution.

An early installed empty-source preview now runs before workspace creation,
using the same installed engine from the application process. Four diagnostic
redaction checks and its Linux source dispatcher/CLI preview passed; native
execution remains pending. The empty fixture has no conversation contents,
working service credential or model call. Its bounded diagnostics redact
environment values, credentials and paths, and still fail on unstructured
output. Other capture phases retain code-only diagnostics and now report exit
status and structured-response counts. The stream reader preserves split UTF-8
and examines the final unterminated line. This is diagnostic work, not a
diagnosed Mac product fix or additional installed acceptance.

## Supervised headless inbox-key forwarding

A later unreleased correction forwards an explicitly configured
`capture.inbox_key.env` through an existing registered Linux/macOS Supervisor
connector. Previously only service/provider references survived that launch
boundary, leaving the new retained runner unable to reopen an environment-backed
inbox key. The correction uses the same private-settings precedence, dedicated
credential checks and missing-reference refusal as those existing references.
It adds no general environment inheritance, new custody authority or implicit
registration. File references keep their existing reload behavior.

Six focused regressions now pass, including actual child-process key reading
from inherited and private-settings values, plus refusal of missing or reserved
references before launch. The corrected baseline failed all six checks on the
preceding implementation. Earlier fixture failures are also retained: the first
key-reader fixture passed a string where the configuration reader requires a
`Path`. Its mixed run had 29 passes and two fixture failures; four of those passes
are covered again by the six new checks. The distinct affected coverage is
25 existing headless/managed cases, six credential checks and the real journey
below, not the sum of repeated run totals.

The real Supervisor journey also passed on Linux: a registered connector retained
one memory while its target workspace was unavailable; after the producer file
was removed, its owned process was killed. Supervisor restarted it with a new
PID, the same protected inbox key reopened, and the accepted memory delivered
exactly once to the isolated PostgreSQL-backed workspace. Private process logs
contained no inbox key, and Supervisor stopped cleanly. The final journey's wait
also tolerates legitimately absent initial observations. It used no production
memories or paid model calls. Both macOS supervision CI jobs now include these
regressions; their actual results remain pending.

The current **557** runtime inputs have digest
`4d965a0ee58eba33d15205993876b4759a2ba3ec54d828d893929e17a7da90a7`.
Only `mnemion/service/supervision.py` differs from the preceding native matrix's
runtime inputs; that running matrix is not validation of this later change.
The later Supervisor source `466efe57` has CI pending.
Independent Windows supervision, boot registration, broader managed lifecycle
acceptance and all remaining L1 requirements remain open. Public **4.44.0** is
unchanged.

## Source and deletion boundaries

The staged service exposes a `durable_capture: "v1"` capability. An administrator
configures custody through the source PUT and approves the device through the
grant PUT before local enrollment. Native `source.configure` accepts
`custody: {source_id, grant_id, keep_accepted: true, pending_limit_mib,
history_limit_events, database_limit_mib}`. The client
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
  Pause do not provide automatic expiry or attachment fetching. The new optional
  JSON-field exclusion rule requires its remaining packaged acceptance and does
  not provide general redaction of secrets embedded in text.
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
