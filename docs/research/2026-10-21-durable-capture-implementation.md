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
and service 75% thresholds remain unchanged. Full corrected CI and native
acceptance remain pending. The separate [4.44 security hotfix](../releases/4.44.0.md)
does not ship this unfinished capture milestone.

## Implemented components

| Component | Current implementation |
| --- | --- |
| Native enrollment | Studio offers explicit retained capture only for a new conversation connection. The administrator approves the source policy and exact device-key grant before native enrollment. App and private agents use the same typed `source.custody` object; existing mirrors cannot silently convert. |
| Capture policy and local preview | An additional unreleased delta adds Selected/Conversation/Detailed choices, relative JSONL file rules, size caps and explicit mirror/retained selection through the same app/agent configuration. A bounded local preview returns counts and capability statuses; explicit-policy retained fragments carry the immutable approved policy fingerprint. Source, Linux journey and separate recovery/migration checks passed; full L1 acceptance remains open. |
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
- Complete verified encrypted export/recovery and reviewed migration for changes
  of device, capture selection, identity or dedicated key. Retain existing mirror
  behavior and past forgetting decisions; current files alone are insufficient.
- Complete the independent headless retained-source enrollment, scheduling and
  lifecycle journey. Ordinary `mnemion-connect` configurations still use their
  existing mirror protocol; desktop helper wiring does not establish that journey.
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
