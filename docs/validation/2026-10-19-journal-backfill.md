# Existing-memory Git backfill, 19 October 2026

Scope: 4.22.0 source, advancing
[issue 39](https://github.com/Perseusxrltd/mnemion/issues/39). This is a separate
administrator-approved export of current native memory versions. Merely enabling
a journal does not approve exporting older memories.

## Service and Git evidence

The 17 new PostgreSQL cases pass with the normal restricted application and
publisher identities. They cover original IDs, Unicode text, revision author and
date preservation; actual Git read-back; idempotent approval and version capture;
current-revision selection; quarantine/deletion exclusion; later deletion of a
queued record; pause, cancellation, process replacement and policy changes;
organization plus space administrator requirements; and another administrator
resuming after the original approver loses access.

Scanner checks distinguish rejected content from unavailable infrastructure.
An unavailable scanner leaves the cursor unchanged and requires repair/resume.
Rejection details stop at 50 records and contain no memory text. Oversized legacy
revisions are rejected before loading their content into the application; the
fixture uses the disposable database operator because normal application roles
cannot modify immutable historical revisions. Revoking the publisher during
scanning rejects capture without advancing the cursor.

Two real background publisher instances process the same approved job and
produce exactly 12 events and 12 Git records, without duplicate versions. The
approval check uses a narrow boolean database function: the private publisher
can verify current authorization without gaining visibility into administrator
or grant tables. This fixed a real failure found by the background-worker tests.

Including the existing writeback, filing and complete-recovery cases, 34 focused
Python cases passed across the initial run and targeted corrections. Full restore
retains the backfill job identity/cursor, pauses journal publication and prevents
unreviewed background capture. An additional 27 agent-contract, real HTTP/SDK,
MCP and issue-association cases passed. All 17 TypeScript SDK cases passed,
including retrying uncertain approval with the same idempotency key and gating
the new operations on service version 4.22 or later.

Repository formatting/lint, the locked Python dependency check and release
metadata validation passed. The final production build staged a matching 4.22
Studio bundle with 439 files (3,662,730 bytes) and 125 dependency notice components.

## Real browser flow

Chromium used the ordinary workspace-key form and production web build against
a disposable HTTP service, PostgreSQL and bare Git destination. Three native
memories predated journal setup. The actual host configuration limited each
batch to two candidates. The UI required both approvals, displayed two of three
records checked, paused, required renewed approval to resume, completed and
expanded the rejected-memory explanation. The existing **Push now** control
flushed delivery during this browser check; independent worker tests above cover
automatic background publication.

Final independent Git read-back recorded **three examined, two queued, one
rejected and two published records**. The synthetic personal-data record was
absent from Git. Paused and completed screenshots were visually checked, including
the completed card at a 1600 × 1400 browser viewport. A subsequent style-only
adjustment aligns the progress bar, spacing and counters with the existing theme.
The disposable service and browser were stopped. No live workspace data or
customer credentials were used, and no paid model calls were made.

## Upgrade correction and limits

The frozen 4.21 release candidate failed three CI cases because their expected
migration lists ended at 023 while the candidate correctly applied 024. Its other
1,369 service cases passed on Python 3.12; those results did not override the
failed release gate. Version 4.22 carries the source-file health fix and corrects
these tests to apply all shipped migrations, then verify preserved password/OAuth
sessions, refresh/consent flows and existing journal settings. All three corrected
upgrade cases pass, including confirmation that migration does not create a
backfill job. The frozen 4.21 source was not modified or published.

The first local contract run encountered an ignored Studio bundle from an older
version. Repeating against the current production frontend passed all 27 cases;
the product's mismatched-bundle rejection remains intact.

Backfill uses no embedding or language model. This evidence does not evaluate
retrieval quality, convert the old external-buffer schema, reconstruct a fully
writable database from journals or prove large-fleet throughput. Capture progress
is distinct from local Git acknowledgement and verified off-host replication.
Native installations, artifact publication and public upgrades remain separate
automated gates in [release status](../RELEASE_STATUS.md). The complete requirement
count remains 17 of 64; this bounded improvement does not finish all of issue 39.
