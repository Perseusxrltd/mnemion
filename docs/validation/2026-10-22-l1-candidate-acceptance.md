# Durable capture: first local-source acceptance

Reviewed **22 October 2026**. The first L1 journey is qualified for release
preparation: an approved Codex JSONL source, encrypted offline intake, restart,
delivery, current permissions, forgetting and recovery through Studio and native
agent controls. Independent headless capture has its own installed journey.
This is the implementation acceptance for **4.45.0**; its final release,
public-download and actual-deployment gates remain separately recorded in
[live release status](https://github.com/Perseusxrltd/mnemion/blob/main/docs/RELEASE_STATUS.md).

All [65 requirements](../PRODUCT_REQUIREMENTS.md), broader provider capture and
the complete [L1–L7 librarian plan](../research/2026-10-20-layered-librarian.md)
remain retained. This record does not mark R07 or the overall product complete.

## Installed evidence

[Native run 39814732365](https://github.com/Perseusxrltd/mnemion/actions/runs/39814732365)
completed successfully at **17:40:44 UTC** on source
`d358726366bfef0e4cbddcb69741512de1d2fd78`. All 18 jobs passed. The six installed
receipts were then preserved and qualified against GitHub archive digests, exact
run/source identities, the frozen probe contract and native runtime manifests.
Each receipt passed all **59 required true fields**. The probe writes a receipt
only after its seven capture phases pass all **96 capture assertions**, alongside
the existing hosting, vault, account and recovery checks. These counts overlap;
they are not separate totals of independent tests.

| Installed target | Qualified artifact |
| --- | --- |
| Linux x64 | `12443321791` |
| Linux arm64 | `12442034923` |
| Windows x64 | `12443413867` |
| Windows arm64 | `12445808545` |
| macOS x64 | `12443349703` |
| macOS arm64 | `12443606671` |

The [machine-readable evidence](2026-10-22-l1-candidate-acceptance.json) records
artifact hashes, source contracts, CI and shared-source receipt hashes. Windows
ARM uses the documented x64 engine/database emulation; the desktop is ARM64.
These development installers still identified themselves as 4.44.2. They are
different bytes and source from the public 4.44.2 hotfix and were never substituted
for that release. The final 4.45.0 pipeline must qualify its own exact artifacts.

The earlier native attempts and their Windows policy-path failures and missing
Apple Silicon runners remain in the
[implementation history](../research/2026-10-21-durable-capture-implementation.md#current-installed-qualification).
The corrected Windows comparison verifies the enrolled canonical path after
checking the original folder identity; it does not relax recovery permissions.

## Acceptance against the original milestone

| Required behavior | Accepted evidence | Retained boundary |
| --- | --- | --- |
| Preview and choose what enters the inbox | Installed app/agent enrollment, matching policy preview, selected paths, JSON-field exclusions, protected device keys and administrator grants. | Only exposed, approved records are available; no attachment retrieval or hidden provider reasoning. |
| Keep accepted content through an outage and restart | Installed offline intake, split Unicode, producer rotation/removal, persistent encrypted queues and independent headless restart. | Bytes never observed before producer loss remain an explicit gap. Intake needs a running source computer and available local storage. |
| Show coverage and delivery truthfully | Selected/omitted/unsupported counts, accepted prefix, unknown history, queue and receipt state, bounded history and independently observed index progress. | Local acceptance, server acceptance and vector readiness are different. L2/L3 consolidation remains unavailable. |
| Reconcile delivery and current authority | Real committed replies lost before the client sees them, restart without reposting, stable identities/revisions, reader revocation and persistent family forgetting. | Current server grants decide delivery and reading. Offline remembered membership cannot grant access. |
| Recover and replace policy without losing custody | Installed encrypted archive export/inspection, new OS-protected keys, paused recovery, approved policy replacement, old-grant retirement and lost-retirement-reply reconciliation. Source process-exit checks cover durable intent and finish/discard. | Organization/source-identity migration and automatic mirror conversion remain open. Original files and external archives are outside local purge receipts. |
| Respect limits and retention | Full source checks for actual SQLite page limits, reduced caps, disk reserve, fair source scheduling, rollback, reclamation and history fences; installed quota controls and reviewed server expiry. | Limits stop new intake without silently dropping accepted work. Local pending evidence has no automatic expiry. Server cleanup can be pending after a deadline. |
| Provide app and agent control on supported platforms | The same seven capture phases passed on all six installed targets, including independent packaged headless operation. | This is a bounded functional journey, not a company-fleet capacity benchmark or proof on every OS minimum. |

The exact-source [Product checks run 39814626137](https://github.com/Perseusxrltd/mnemion/actions/runs/39814626137)
passed all 12 required jobs. It includes the service matrix, migrations, storage,
policy, interruption, coverage and permission regressions, plus the existing
client, container, Mac runtime and legacy checks. No passing group was repeated
for this document review.

The [actual-Codex shared-host journey](2026-10-22-shared-codex-capture.md) adds
**28 assertions** using Codex CLI 0.163.0's retained producer files, the same
source app and an independent isolated PostgreSQL/API on the VPS. Source
`38eb3021d517a193b47501f902b4595a49d44178` remains its recorded identity. Comparing
all 574 runtime inputs to the native source found only the Windows probe's path
comparison changed; capture and service runtime bytes did not change. Other
changes were documentation or the existing allowlisted generated metadata.
The shared journey therefore was not repeated or relabeled with a later commit.
Its original two harness failures remain preserved. The completed continuation
did not replay uncertain mutations, and its isolated database and forward were
stopped with no production memory writes or paid model calls. Synthetic index
vectors establish indexing state, not embedding quality.

## Release and continuing scope

The release batch includes the existing Codex-format, startup shutdown, native
crypto and Windows atomic-write corrections, plus capture recovery and release
automation fixes. Version preparation now handles both roadmap-header layouts
without removing the live public-status link. Its current-layout regression
failed before the correction; all **28 release-automation checks** then passed.
Updated guides retain their commands, examples and old section links while
stating the required runtime version and linking to current availability.

Managed services cross five new capture migrations, **030–034**. Use the existing
[reviewed host upgrade](../service/managed-upgrades.md) with its verified backup,
migration journal and recovery gates. Automatic compatible hotfix policy is
unchanged. An older service cannot authorize the new retained-capture mode;
existing mirror connections keep their behavior. Capture requires explicit
selection and source/device approval after installation.

Still open: broader actual-provider/plugin acceptance, complete inaccessible
history, general text-secret redaction, attachment retrieval, larger-history and
cross-device coordination, representative fleet measurements, wider migrations
and all later librarian layers. Issues **44/45** retain their actual cloud-client
and deployment acceptance work. The separately paused PC note publisher remains
paused pending its independent guard/QC approval. Neither this qualification nor
installing 4.45 resumes that publisher.
