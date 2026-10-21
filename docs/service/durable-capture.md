# Keep selected conversations after chat logs disappear

**Unreleased implementation.** This guide describes the current development
source. Check [release status](../RELEASE_STATUS.md) for published availability.
For desktop use, both Studio and the workspace server must support retained
capture; the server advertises `durable_capture: "v1"` in `GET /health/live`.
This work advances L1 of the [layered librarian](../research/2026-10-20-layered-librarian.md); full L1
and R07 acceptance remain open.

Retained capture commits the selected conversation items to an encrypted local
inbox before making any service request in a scan. Once accepted locally, those
items can still be delivered after the original JSONL file rotates or disappears.
Delivery checks the workspace's current authorization and forgetting decisions.

For the independent development runner, use the [headless capture guide](headless-capture.md).
It describes explicit paused enrollment, protected key references, scheduling
and recovery through `mnemion-connect --capture-control`. Its source checkpoint
checks passed; packaged acceptance remains open. The Studio controls below and
stable 4.44 availability remain separate.

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
   chat logs rotate or are removed**. Review the audience, pending content,
   local history and encrypted storage limits. The approved policy is fixed for this inbox: changing its selection,
   file/record size rules, identity or dedicated key requires a reviewed migration.
4. Review **Session filters and capture sizes**, source RAM, maximum files and
   local quotas, then select **Preview capture**. Review its bounded
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
mode and relative path; the collector enforces the file/record limits. Changing
an existing inbox's selection still requires reviewed migration. The additional
unreleased [administrator controls](#manage-source-defaults-and-device-authorizations-unreleased)
can change the default for new grants while preserving each existing grant's
approved policy or explicitly revoking it. Older `complete`/`messages`
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
| `capture_complete`, `reason_code` | Whether local intake finished. `capture_scan_pending` means verified progress was saved and intake remains; `capture_delivery_pending` means intake finished but queued delivery or the forgetting sweep remains. Other reasons identify observed errors. |
| `delivery_complete` | The observed pending queue and current forgetting sweep finished without a delivery error. An empty queue alone does not prove the sweep finished. |
| `database_bytes`, `device_database_bytes`, `device_pending_bytes`, `over_limit` | Local storage observations and whether the inbox exceeds an admission limit. |
| `coverage` | Encrypted prefix accounting, history uncertainty, queue/contact observations and saved source index observations, described below. |
| `history` | Optional retained-record counts, effective admission limits and deletion-history pause. Missing or null means unobserved; see [history usage](#read-history-usage-and-change-local-quotas-unreleased). |
| `storage` | Optional free-page cleanup observation, separate from intake and delivery success. Missing or null means unobserved, including older saved reports; see [database cleanup](#reclaim-unused-database-pages-unreleased). |

During [bounded backfill](#continue-a-bounded-backfill-unreleased), capture can
remain incomplete while delivery completes for every event accepted so far.
`capture_scan_pending` is reported when no source or delivery error takes
precedence. Once intake is complete, healthy remaining delivery or forgetting
work reports `capture_delivery_pending`, with `capture_complete: true` and
`delivery_complete: false`. By default, delivery attempts at most four pages of
up to 50 events per cycle; a larger queue can need several cycles. Continue with
the saved inbox, exact pages and checkpoint.

For either continuation reason, the app saves a validated incomplete report
with successful delivery contact as `activity.phase: "backfill"`; both source
panels show **Backfilling**. This
preserves any prior `last_success_report` and `last_failure`, and saves the next
scan time across restart. It does not invent a success or failure for normal
deferred work. Pending and fully delivered batches can both be backfilling.
A missing or invalid report cannot establish this state; actual errors or
an unavailable delivery service still need attention.

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
| `tracked_scopes`, `checking_scopes`, `failed_scopes`, `missing_scopes` | Tracked producer files and their latest observed verification state. `checking_scopes` includes backfill deferred until a later scan. A missing file is not treated as forgotten. |
| `observed_bytes`, `examined_prefix_bytes`, `unaccepted_observed_bytes` | Last recorded source sizes, examined complete prefixes, and their difference. Unaccepted source bytes can include deferred backfill, unfinished tails or failed reads; they are separate from queued selected-payload `pending_bytes`. |
| `unknown_prefix_scopes` | Files without known selection accounting, including earlier checkpoints that predate it. Zero selection counts do not fill that missing observation. |
| `uncertain_scopes`, `uncertain_intervals`, `unresolved_previous_bytes` | Files with uncertain history, unavailable/interrupted observation periods, and known unaccepted bytes lost from an earlier observation, including removed unexamined suffixes. These do not measure everything that may have disappeared. |
| `tracked_from`, `observed_at`, `complete_prefix_at` | Tracking start, last catalog observation, and the last time all tracked prefixes finished without checking, failed or missing scopes. A prior complete-prefix timestamp does not establish current or historical completeness. |
| `queue_nonempty_since` | Start of the observed continuous non-empty queue period, retained across restarts. It is reported as null when empty; a later empty-to-non-empty transition starts a new period. Older pending queues can have an unknown start. This is not the oldest fragment's age. |
| `last_contact_at` | Last successful authenticated delivery preflight verifying the saved, matching active device grant. An arbitrary HTTP response or failed authorization check does not update it. |
| `last_acknowledged_at` | Last validated page receipt applied locally, including reconciled receipts and stored/forgotten outcomes. It does not timestamp index completion. |

Deferred scopes are awaiting verification; deferral alone does not add a failed
scope or an interrupted observation interval. A suffix removed before its next
window stays visible as unresolved history, including when the later scan fails.

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
| Inbox database admission per source | `database_limit_mib`: default 512 MiB; configurable from 64 to 2,048 MiB |
| Aggregate inbox database admission on this device | 2 GiB |
| Free disk required for new intake | At least 512 MiB, plus room for the incoming transaction |
| Entries in each local history counter | `history_limit_events`: default 100,000; configurable from 1,000 to 500,000 |
| Producer scopes per inbox | 10,000 |
| Source RAM | Default 256 MiB; configurable from 128 to 2,048 MiB |

Content limits count the selected payload, independently of database
overhead. Raising the payload limit does not raise the database or reference
limits. Database admission counts SQLite pages. Bounded delivery bookkeeping can
use reserve above the database limit so reconciliation and forgetting can still
finish; this is not extra allowance for new capture.

At admission capacity, new intake stops and already accepted evidence stays available.
Lowering a limit does not trim the queue or silently discard events. The new
deletion-history handling below preserves authenticated forgetting of held data
above the event limit. Delivery and cleanup remain subject to usable disk space
and current authorization; delivering the queue does not erase its history.
The [desktop resource limits](desktop-sources.md#capture-and-resources), including
the sampled RAM limit and process deadline, also apply. Capture does not need a
local model; server indexing follows the workspace's model policy.

### Read history usage and change local quotas (unreleased)

In **Source settings and key**, set **Maximum entries per history counter** and
**Maximum encrypted storage for this source (MiB)**. These are strict integer
fields `custody.history_limit_events` and `custody.database_limit_mib` in native
settings, or the same fields under `capture` in the [headless configuration](headless-capture.md#write-the-configuration).
They also participate in the preview fingerprint. Re-preview explicit-policy
settings before saving. Changing only these quotas preserves the source, grant,
inbox key and approved capture policy; it does not migrate existing evidence.

Expand **Capture coverage and history**, or read
`activity.report.capture.history` (`mnemion-capture-history-v1`):

| Field | Meaning |
| --- | --- |
| `events` | All locally accepted event records: pending, stored and forgotten. |
| `producer_events`, `fragments` | Retained producer-event identities and saved producer-fragment references. These are separate counters, not message totals. |
| `denials` | Exact retained deletion records, including applicable fences for lineages absent from this inbox. |
| `event_limit` | Admission allowance applied separately to `events`, `producer_events`, `fragments` and `denials`, not their sum. |
| `scopes`, `scope_limit` | Tracked producer-file identities and the unchanged 10,000-scope limit. |
| `delivery_pages` | Retained delivery-page records. This observation does not introduce a separate page quota. |
| `database_bytes`, `database_limit_bytes` | Actual SQLite page bytes and this observation's effective database allowance, which aggregate device usage can reduce below the configured per-source value. |
| `over_limit` | Whether one of the four entry counters, scopes or database bytes exceeds its corresponding limit. Equality alone is not over-limit, but the next admission can still be blocked. |
| `fence_history_blocked` | A persistent intake pause because an authenticated deletion fence could not be retained. This is independent of `over_limit`. |

These are saved scan observations. Older absent/null history stays unknown, and
a changed quota does not rewrite an earlier report. Source settings show the
configured limits; the next scan records their effective values.

Authenticated forgetting of a lineage already held locally retains its exact
denial even above a lowered history limit, including forgotten delivery
receipts. If a fence for an unheld lineage cannot fit, the same fence page still
commits known held-data purges, leaves its cursor unadvanced and persists an
encrypted intake pause. Already accepted delivery is still attempted; history
is never deleted to make space. `capture_fence_capacity` needs attention and is
not a healthy five-second backfill condition.

Raise the history allowance enough to retain the outstanding fences, then scan
again. The pause clears only at the successful end of an authenticated fence
sweep, not merely when settings change or one page succeeds. Intake runs before
that sweep, so another scan can be needed after it clears. Explicit **Pause**
remains separate and stops both intake and delivery.

The [focused source, controller and migration checks](../research/2026-10-21-durable-capture-implementation.md#deletion-fences-and-history-limits-source-delta)
passed after four reproduced failures, including real HTTP delivery while
fence history is full and preservation across device-key recovery. Finite
history, scope, delivery-page and archive
bounds, coordination across independent devices and all packaged/L1 acceptance
remain open.

### Continue a bounded backfill (unreleased)

Each producer file (scope) can save part of its history and resume on the next
scan, even if the file's size and modification time have not changed. The new
work allowance is **64 newly rendered fragments or 32 MiB of newly parsed input
per file per pass**. The input allowance shrinks to one-eighth of the inbox's
remaining pending-byte budget, with a 1 KiB floor and the 32 MiB maximum.
Exact selected-payload admission limits still apply.

These limits are checked at existing fragment boundaries. A fragment finishes
before stopping, preserving normal segmentation, selected output and event
identities. A fragment may produce several selected events. The allowances are
cooperative work limits, not hard byte or RAM ceilings. A soft stop leaves the
final quarter of that file's configured scan time for verification; verification
can still exhaust the deadline. Prefix hashing and read-ahead are outside the
new-input allowance.

Selected evidence, the verified prefix checkpoint and selection accounting
commit atomically. Retained-prefix reuse avoids decrypting and updating every
old fragment reference; it does not remove source-prefix verification. The
existing mirror protocol keeps its full-inventory behavior.

These per-file windows alone do not bound work across a connection or device,
provide multi-file fairness, or remove the event, scope, storage and retained-history
limits above. [Focused source, controller and migration checks](../research/2026-10-21-durable-capture-implementation.md#bounded-retained-backfill-source-delta),
the app/documentation build and an isolated Linux intake measurement passed.
All 12 CI jobs also passed for that checkpoint, `763a8341`. The later connection
budget has separate source evidence below; installed-platform and full L1
acceptance remain open.

### Share an intake pass across files (unreleased)

A further development batch adds cooperative allowances across one retained
connection's local intake pass:

| Work | Allowance per pass |
| --- | --- |
| Producer-file attempts, including failures | 256 |
| Rendered fragments across those files | 256 |
| Actual producer input read, including prefix verification and read-ahead | 64 MiB |
| Elapsed local intake time | 30 seconds, or the configured per-file scan time when smaller |

The timer starts before catalog work. One file attempt is allowed even after a
slow catalog; the current fragment and verification can exceed the byte/time
allowances. Existing per-file windows, exact admission limits and the hard
per-file scan deadline still apply. These budgets exclude delivery and database
cleanup and do not combine work across separate connections or devices.

An encrypted schedule records the catalog hash, remaining sweep slots and last
attempted scope. Files rotate in stable scope-ID order, resuming after that
scope across restarts. A catalog change restarts the sweep while preserving the
rotation cursor and all accepted evidence. The attempt, cursor and checking
observation commit before reading the file; a killed attempt remains distinct
from deliberately unvisited work. A cursor advance does not prove acceptance.

Unvisited files keep their deferred or failed coverage. An unvisited file's
earlier failure still prevents a complete report while it remains in the
catalog; disappearance is recorded separately as missing history. Archive
inspection validates the saved schedule, and device-key rotation preserves it.

Healthy intake or delivery backfill now schedules another scan **five seconds
after the current pass finishes**. It requires a matching `capture_scan_pending`
or `capture_delivery_pending` report, successful delivery contact and no failed
optional control report. Native status saves that next scan
time; the headless watcher uses the same interval. [Managed headless runs](headless-capture.md#run-scans-and-choose-scheduling)
also require a fresh matching private runtime receipt. This changes follow-up
scheduling, not the incomplete result or prior success/failure history. Failed,
paused, complete and legacy mirror scans keep ordinary polling. It is not a new
configurable profile; pause, resource and admission controls still apply.

[Scoped source, controller and migration checks](../research/2026-10-21-durable-capture-implementation.md#connection-intake-budget-and-rotation-source-delta)
passed, including a real headless watcher that completed intake and delivery of
576 synthetic events after an outage. The initial setup and assertion failures
remain recorded. These are source checks; current full CI, history/storage
requirements, all six packaged targets and full L1 acceptance remain open.

### Reclaim unused database pages (unreleased)

An additional development delta returns unused SQLite pages to disk without
removing any logical event, receipt, checkpoint, producer identity or denial.
It adds no expiry. New inboxes enable incremental vacuum; the shared desktop
and headless cycle attempts cleanup before intake and after delivery. Each
incremental pass has a **64 MiB page allowance** and a **0.5-second cooperative
time budget**. SQLite progress checks and checks between work steps can interrupt
cleanup, but a filesystem operation can outlast that budget; it is not an
instantaneous hard deadline.

An older inbox first needs a whole-database conversion. This runs only when no
events or delivery pages remain pending, including records settled by confirmed
storage or forgetting. It requires free disk of at least twice the current
database size plus 1 MiB and uses the same cooperative time budget.
The conversion is not bounded to 64 MiB; SQLite commits the completed conversion
or rolls it back. A deferred conversion leaves the existing inbox available.
Incremental work also checks disk reserve before each step. Unused pages may
remain for reuse or a later eligible scan.

Studio shows cleanup observations under **Capture coverage and history**.
Agents read `activity.report.capture.storage`, format
`mnemion-capture-storage-v1`:

| Field | Meaning |
| --- | --- |
| `database_bytes` | Observed SQLite page bytes after the final cleanup pass, matching the capture report's database size. |
| `reclaimable_bytes` | Unused SQLite page bytes still available for reuse or later reclamation. This is not pending-content size. |
| `reclaimed_bytes` | Actual reduction in database page bytes accumulated across both passes of this scan, not a lifetime total. |
| `state` | `idle`, `reclaimed`, `deferred` or `failed`; `idle` can still leave free pages below the cleanup threshold. |
| `reason` | Final-pass bounded reason: `time_budget`, `byte_budget`, `disk_reserve` or `pending_legacy` when deferred; `sqlite_failure` when failed; otherwise null. |

The final pass can report deferred or failed cleanup even after some bytes were
reclaimed. Cleanup status does not acknowledge a delivery or establish index
readiness. It does not reduce retained history counters (default limit
**100,000 each**) or **10,000 producer-scope** counts, or solve the remaining
bounded-history requirement.
The [focused source, controller and migration checks](../research/2026-10-21-durable-capture-implementation.md#free-page-reclamation-source-delta)
passed; all installed-platform, release and full L1 acceptance remain open.

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

The [portable archive checkpoint](#back-up-and-inspect-an-inbox-unreleased)
provides export/inspection and a library for restoring a new local inbox. A
separate [device recovery delta](#recover-onto-another-device-unreleased) now
adds native enrollment under a replacement grant, with the original source and
policy retained. This development work and its installed acceptance remain open;
changing the original source identity or policy is still unsupported.

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

This development work remains unreleased. Core, helper/controller, migration
and Linux Electron export/restart-inspection checks passed at archive checkpoint
`7aca19e9`; packaged acceptance remains pending. Its
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
device/policy or resume capture. The separate coordinator below adds a reviewed
replacement-device path. Current authority, later server forgetting decisions,
broader migration and six-platform acceptance retain their own gates.

### Recover onto another device (unreleased)

This unreleased implementation passed its three-phase Linux source journey on
2026-10-21 at **05:06 UTC**. App recovery preserved the source/policy, installed
new protected keys and a grant, remained paused after restart, delivered without
duplicating old memory, captured new memory and cleaned up its fixtures. Source,
controller, operator and migration checks also passed. The
[development evidence](../research/2026-10-21-durable-capture-implementation.md#device-recovery-source-delta)
retains all three earlier failed journeys. Six-platform packaged acceptance and
full L1 acceptance remain open.

Inspect the original archive with its separate recovery key and retain the
returned hash. An administrator must approve a new dedicated device key and
grant for the **same** organization, connector and capture source. The namespace,
capture mode and policy also stay unchanged, including a mode-only policy in an
older archive. This recovery changes the device authorization and local inbox
key; it cannot change what evidence was selected or which source owns it.

In Studio, use the original conversation connection with a current workspace
administrator session and open **Recover an existing capture inbox**. Choose and
verify the archive, preview the selected folder and approve previous-device
retirement, then select **Recover as a paused source**. The app creates the
replacement dedicated key and approved grant for this operation.

With the additional policy-version capability, recovery explicitly requests the
archive's original policy using its previous grant, even if the source default
has since changed. See [original-policy authorization](#approve-original-policy-recovery).
The [new policy checkpoint](../research/2026-10-21-durable-capture-implementation.md#capture-policy-versions-source-delta)
records separate service/recovery checks for this authorization. The earlier
Linux source journey above predates this batch; all six packaged recovery
journeys remain open.

Select and preview the replacement conversation folder. The archive contains no
producer files. If files corresponding to saved checkpoints are present, their
captured prefixes must verify before retirement. Missing files do not prevent
recovering accepted backlog, but their history remains missing or unobserved;
the operation does not reconstruct them.

The native operation needs unlocked OS credential storage, fresh source settings
and explicit confirmation of previous-device retirement. It authenticates the
archive, re-encrypts its inbox under a new random 256-bit key, checks current
replacement authority and confirms revocation of the original grant. It then
publishes a protected recovery intent and installs a **new, paused** source.
Existing inboxes are never overwritten. The replacement device credential and
inbox key are OS-sealed; the one-use retirement credential is not saved. Grant
retirement does not revoke the old API key's unrelated rights.

Pending evidence, exact pages, checkpoints, forgetting fences and saved
observations retain their identities; historical receipts still name their
original issuing grant. Resuming later delivery rechecks current authority and
server forgetting. Successful local recovery does not prove complete history,
current index readiness or L2/L3 consolidation.

After an uncertain reply, inspect `source.status` and `source.restore.list`;
there is no automatic replay. A saved intent supports explicit
`source.restore.finish` using the protected replacement keys and current server
authority. If its inbox copy was not yet published, finishing also needs the
original archive and recovery key. Explicit `source.restore.discard` first
revokes the replacement grant and then removes the unfinished local evidence;
it preserves the archive and does not reactivate the original grant. An already
installed source must use ordinary source removal instead. The
[agent guide](desktop-operator.md#recover-a-capture-device-unreleased) describes
the inputs and interrupted-operation controls.

## Manage source defaults and device authorizations (unreleased)

This additional development batch requires `capture_policy_versions: "v1"` in
`GET /health/live`. In **Connections**, an administrator can open a published
conversation connection's **Retained conversation capture** panel from Studio
or the hosted workspace. These are shared server controls: the page does not
read producer files, change local settings, decrypt inboxes or invoke a model.

Each device grant binds an immutable `policy_version`. The source's current
policy is the default for newly created grants; it does not replace existing
approvals. **Device authorizations** separates unrevoked grants from those that
can currently authenticate and shows each grant's approved version. These are
authorization observations, not counts of online computers or pending messages.
Source, device and policy-history lists are paginated, at most 100 per page.

1. Select the retained source and review **Device authorizations** and
   **Approved policy history**, including earlier mode-only approvals.
2. Open **Change the policy for new device authorizations**. Choose the preset,
   relative JSONL path patterns and read limits. Each new local enrollment still
   needs its own folder preview and confirmation.
3. Explicitly choose how to treat existing authorizations: **Keep their previously
   approved policies**, which also permits future capture under those rules, or
   **Revoke every existing authorization**, covering all unrevoked grants for this
   source, including keys that cannot currently authenticate.
4. Select **Review policy change**. The app obtains a fresh source version and
   review token covering the whole unrevoked-grant set, not only the visible page.
   Review the effect, confirm the checkbox and select **Approve policy change**.
   Changed settings or device permissions require a fresh review.

The transition preserves the source, custody space, mapped audience, accepted
memories and deletion fences. It does not rewrite queued content. Revocation
stops server delivery; a runner stops further intake when it observes that
revocation. Offline inbox evidence remains available for explicitly approved
recovery. To revoke one authorization independently, use its **Revoke** action
and confirmation; this does not delete server memories or erase the local inbox.

### Equivalent MCP and HTTP steps

Discover the current schemas with `mnemion_operations` and `mnemion_operation`.
Use `mnemion_read` for `capture.source.list`, `capture.policy.review` and
`capture.policy.versions`. Supply connector/source IDs and any `after`/`limit`
query values in `request.parameters`. Source and device cursors are UUIDs;
policy-history cursors are policy-version integers. Routes are listed in
[administrator setup](#agent-and-administrator-setup).

Use `review.source.version` as `expected_version`, rather than its
`policy_version`, and preserve the returned `review_token`. Choose a new
`transition_id` UUID for this reviewed change. The following is a template for
`mnemion_write`; replace the IDs, version, review token and selection with the
freshly reviewed values:

```json
{
  "operation": "capture.policy.change",
  "request": {
    "parameters": {
      "connector_id": "CONNECTOR_UUID",
      "source_id": "SOURCE_UUID",
      "transition_id": "NEW_TRANSITION_UUID"
    },
    "body": {
      "expected_version": 1,
      "review_token": "REPLACE_WITH_REVIEW_TOKEN",
      "capture_policy": {
        "format": "mnemion-capture-policy-v1",
        "preset": "selected",
        "capture_mode": "messages",
        "include": ["team/*.jsonl"],
        "exclude": [],
        "retention": "until_deleted",
        "max_file_bytes": 1000000000,
        "max_record_bytes": 2000000
      },
      "previous_grants": "retain",
      "confirm": true
    }
  }
}
```

For HTTP, put the IDs in the policy-transition route and send only the inner
`body` object as JSON. `previous_grants` must explicitly be `retain` or `revoke`;
`confirm` must be true. A retired source, unchanged policy or stale review is
refused. Name/audience edits through the ordinary source PUT remain separate.

After an uncertain write, inspect source status and policy history before
retrying through the [agent gateway](agent-control.md#retry-and-outcome-rules).
Keep the exact same transition UUID and body for an exact retry. A committed
transition returns its original receipt without revoking grants created later;
reusing its UUID with a different request conflicts. The response's source may
already have a newer default, so inspect the returned transition separately.

### Approve original-policy recovery

When authorizing a replacement for an inspected archive, an administrator can
request the exact policy of its original grant. Use `capture.grant.configure`
with the original source ID and a **new** grant ID, or
`PUT /v1/capture-sources/{source_id}/grants/{grant_id}`, with this body:

```json
{
  "device_key_id": "REPLACEMENT_DEVICE_KEY_UUID",
  "previous_grant_id": "ARCHIVE_ORIGINAL_GRANT_UUID",
  "confirm_previous_policy": true
}
```

Both recovery fields are required together. The previous grant must belong to
the same source. This expressly reauthorizes its original selection, including
an older mode-only policy; omitting these fields on a new grant selects the
current source default. A revoked grant is not reactivated. Read the replacement
grant's policy and use the unchanged archive policy during local recovery.
Studio's archive-recovery path requests this original-policy approval when the
server advertises the capability, under the existing explicit recovery consent.

Authorizing a grant does not restore an archive, resume a device or migrate an
existing inbox's selection. Fresh local enrollment still refuses a source with
capture history. Broader selection/organization migration, complete history,
all six packaged recovery journeys and full L1 acceptance remain open. This
policy version batch passed its scoped source and browser administration checks;
it remains unreleased and is not in stable 4.44.

## Agent and administrator setup

Remote administration uses the server's capture APIs. The desktop runner uses the
same OS-account [private desktop interface](desktop-operator.md) as Studio;
a network memory credential does not authorize control of the computer. Discover
the current [agent operation schemas](agent-control.md) before submitting a
request. The independent [headless runner](headless-capture.md) uses an explicit
JSON capture configuration and local stdin controls; it does not require Studio.
These operations are part of the unreleased implementation:

| Operation | HTTP route |
| --- | --- |
| `capture.source.list` | `GET /v1/connectors/{connector_id}/capture-sources` |
| `capture.source.configure` / `capture.source.status` / `capture.source.revoke` | `PUT` / `GET` / `DELETE /v1/connectors/{connector_id}/capture-sources/{source_id}` |
| `capture.policy.review` | `GET /v1/connectors/{connector_id}/capture-sources/{source_id}/policy-review` |
| `capture.policy.versions` | `GET /v1/connectors/{connector_id}/capture-sources/{source_id}/policies` |
| `capture.policy.change` | `PUT /v1/connectors/{connector_id}/capture-sources/{source_id}/policy-transitions/{transition_id}` |
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
Updating the name or audience uses the current source version and default-policy
fields from GET. The source identity and every approved policy version remain
immutable; a [reviewed transition](#manage-source-defaults-and-device-authorizations-unreleased)
can change the default for new grants. Then approve a stable `grant_id` through
the device-grant PUT with
`{"device_key_id": "DEDICATED_APPLICATION_KEY_UUID"}`. Only an administrator
can authorize the source and grant; the source's application key cannot grant
itself custody or expand its audience. Match local capture settings to the
returned grant's policy, which can differ from the source's current default.

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
    "pending_limit_mib": 256,
    "history_limit_events": 100000,
    "database_limit_mib": 512
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
