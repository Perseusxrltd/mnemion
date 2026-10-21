# Durable conversation capture: implementation checkpoint

**Unreleased implementation.** This is development work for
[L1 of the layered librarian](2026-10-20-layered-librarian.md), not a claim that
published Studio provides the complete journey. Existing sources keep their
mirror behavior. All [65 product requirements](../PRODUCT_REQUIREMENTS.md) and
L1–L7 remain in scope; this checkpoint does not close L1 or R07. The current
[app and agent guide](../service/durable-capture.md) describes the implemented
enrollment, limits, removal and recovery boundaries.

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

## Implemented components

| Component | Current implementation |
| --- | --- |
| Native enrollment | Studio offers explicit retained capture only for a new conversation connection. The administrator approves the source policy and exact device-key grant before native enrollment. App and private agents use the same typed `source.custody` object; existing mirrors cannot silently convert. |
| Encrypted selected inbox | The native controller creates an independent random 256-bit key and seals it through OS credential storage. Selected items and a verified capture checkpoint commit together under AES-256-GCM. Both messages and complete modes use the existing renderer. Messages mode cannot retain a raw transcript or hide raw text in its source evidence. |
| Local capture and scheduling | The normal desktop runner commits available selected JSONL evidence before any service request in a scan. Accepted events survive restart and producer removal/rotation; unfinished tails wait. Missing source files can stop new capture while already accepted evidence remains deliverable. |
| Durable service custody | Explicit administrator consent, immutable selection/source identity, exact device-key grants, current audience/role checks, immutable event receipts and idempotent pages. Existing provider permission leases remain unchanged. |
| Delivery and reconciliation | The runner saves exact pages before delivery, looks up uncertain receipts and resends only the same page. Current revocation and forgetting fences apply to backlog. Revoked grants retain local pending evidence without attempting ingestion; observed revocation also stops later local intake. |
| Private scan observations | Last success, failure, interrupted attempt and next check survive restart. App and native status separate local acceptance, pending content, server acknowledgements, unknown pages, incomplete scans and capacity. Explicit repair preserves damaged diagnostics and resets history for every source on the device to unknown without changing sources, credentials or capture data. |
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

- Finish durable coverage/gap accounting and selected, omitted and unsupported
  event breakdowns, including offline age and separately observed index readiness.
  Join observed, locally accepted and server-acknowledged progress without turning
  unknown history into zero gaps. Consolidated progress remains unavailable until
  the corresponding L2/L3 work exists.
- Complete the bounded enrollment/capability preview, source/session include and
  exclude controls, explicit retention selections, attachment/field availability
  and policy revisions for accepted segments. The two content modes are partial
  controls, not the full Selected/Conversation/Detailed/Paused preset contract.
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
