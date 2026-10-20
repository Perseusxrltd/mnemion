# Restore editable memories from a native journal

Source **4.29.0** adds resumable large-inventory recovery, extending the
reviewed recovery introduced in 4.26. Both accept a complete
[native Git journal](git-journal.md). Check the automatic
[published release status](../RELEASE_STATUS.md) for installer availability.
The same recovery is available in Studio, the Python/TypeScript clients and
private agent operations.

This restores the current memory projection. Use a
[complete workspace backup](recovery.md) to recover the original organization,
accounts, keys, grants, attachments, vault, evaluations and full native revision
history. A journal and its catalog cannot establish that an unavailable remote
host had no newer unpublished changes.

## In the app

1. Obtain a trusted, complete copy of the journal from the correct repository,
   branch and prefix. Keep the original bytes. Include `catalog.json`, all
   dated JSONL files, numbered continuations and `_archive`.
2. Create or select a **private native space** with only your administrator
   grant and no Git publication configuration. Open **Git journal → Restore a
   native journal**. Organization and space administration are both required.
3. Leave **Keep original memory IDs** selected for a replacement host. If those
   IDs already belong to memories or held identities in this organization,
   choose **Create independent copies** in a new private space instead. A
   collision never overwrites an existing record or grants access to it.
4. Select the directory that directly contains `catalog.json`. Supply original
   memory IDs withdrawn after this snapshot, including IDs absent from its
   files. Leave the withdrawal field empty only after checking the latest
   available history. Secret checks always run; recognizable personal-data
   checks default on.
5. Select **Upload & review complete journal**. Progress is saved after every
   256 KiB chunk. **Pause** stops after the current step. After reopening the app,
   choose the upload under **Saved recoveries**, select the original folder if
   bytes remain, then **Continue upload & review**. Another device can resume
   with the same administrator account, destination and exact original files.
6. Review counts and paged identity decisions. Acknowledge the complete inventory,
   recovery scope and resumable batches, then **Restore reviewed memories**.
7. Inspect the recovered records. They are editable and available to keyword
   search immediately; normal semantic indexing follows. Share or publish the
   space separately after review.

The complete upload is checked before any restoration is authorized. Withdrawals
and current quarantines are reviewed and applied before any positive content.
Restoration then commits batches of at most 64 identities and 2 MiB of staged
record bytes. **Continue approved recovery** resumes a paused restoration without
reapplying accepted batches. It does not repeat the upload.

A changed destination stops the affected batch. Earlier batches remain saved.
Use **Review current destination again** to retain those results, check remaining
work against current state, and approve a fresh review. The counters then describe
that new review. **Cancel & clean staging** stops future batches and queues private
staging for deletion; it never removes already-restored memories. Starting another
recovery leaves the previous one available until it expires or is cancelled.

A failed batch leaves no partial memories, origin records, withdrawals or indexing
jobs **within that batch**. The older small-inventory API still applies its whole
preview in one transaction; it has the separate limits below.

## Identity, versions and withdrawals

Original-ID mode preserves each original memory UUID across replacement
organizations and hosts. The original tenant, space, event ID, writer, timestamp,
version, metadata and important flag remain provenance. The importing
administrator creates local revisions; old writers do not become principals.
Original metadata is retained under `metadata.journal_recovery.metadata`.
Original claims are not promoted to verified facts.

Copy mode derives IDs from the destination space and complete original identity.
Repeat the same mode and destination to retain those IDs. Choosing a new copy
destination creates new identities; reconcile its withdrawals separately.

Complete projection applies every permanent forget before any positive record,
regardless of input order or a later claimed upsert. Native deletions and
physically purged memories stay withdrawn. Explicit additional withdrawals are
retained even when no positive record was present.

Quarantines are retained even if the available journal has no earlier content.
Such an origin has no fabricated memory text and is not searchable. An older
snapshot cannot release it. A newer complete journal can supply a reviewed
release. Existing recovered memories become quarantined without losing local
text. Local changes made before a quarantine remain protected after a later
source release.

Newer source revisions can update an untouched recovered memory after a fresh
review. Local edits or manual review decisions are preserved. The same source
version with different canonical bytes is a conflict. Older source versions
are ignored. These rules are recovery reconciliation, not a background sync
policy or a complete replay of historical native revisions.

## Completeness, privacy and capacity

The catalog's unique event count must match the whole submitted inventory.
Duplicate event IDs must have identical canonical records. Conflicting
origin/version claims, truncated lines, unexpected namespaces, incorrect file
paths, missing files and incompatible continuation catalogs stop the recovery.
Schema 1 and schema 2 journals are supported.

| Path | Complete input | Files | Physical records | Memory identities |
| --- | --- | --- | --- | --- |
| App and resumable API, server 4.29+ | 2 GiB including catalog | 8,192 | 1,000,000 | 100,000 |
| Small API and app on server 4.26–4.28 | 1 MiB | 256 | 10,000 | 1,000 |

Additional withdrawals are limited to 10,000 for the resumable path and count
against its identity limit. Duplicate physical lines count against its record
limit. A record is bounded to 384 KiB; native memory text and metadata retain
their existing limits. The normal 2,000,000-byte HTTP envelope remains unchanged.

**Never split a native journal or reduce its catalog to fit:** omitted history
could contain the only withdrawal. Beyond these limits, use complete workspace
backup recovery. The older external-buffer format has a separate
[importer](legacy-buffer.md).

The app reads file slices and retains file handles, not the complete journal text.
The server stages canonical event hashes and the latest record per identity in
PostgreSQL. The upload is separate from searchable memories, uses no model, and
cannot add grants or publish content. Current organization administration, private
space administration and the original uploader identity are checked for every
request, including after revocation, restart or restore. Ordinary agent memory
keys do not gain recovery administration.

Staging is ordinary **private database content**, not an encrypted secrets vault.
Full host backups can include it and follow their own retention. An administrator
can retain two active uploads, at most eight retained uploads and 4 GiB of declared
staging across their spaces. Progress expires after 24 hours without an accepted
step; status reads and exact chunk retries do not extend it. Completed uploads
expire 24 hours after their last step. Cancellation requests earlier cleanup.
The worker removes expired rows in bounded steps, independently of the uploader;
physical cleanup can take longer under load or while the worker is stopped. It
cannot erase pre-existing backups. Keep source files until recovery is confirmed.

Resume rereads the acknowledged prefix locally and compares a chained SHA-256
transport receipt before sending the remainder. Same-length changed files are
refused. Each fixed-size chunk is independently hashed and committed with its
parser progress; exact retries do not duplicate events. The transport receipt is
not a raw file SHA-256 or proof of Git delivery.

The small API instead uses a bounded in-memory SQLite index and retains no upload.
Both paths scan current positive content and original metadata for secrets before
restoration. Oversized provenance is refused rather than truncated. Known
withdrawals remain enforceable even when an old positive record would be rejected.

Input files are user-supplied evidence. Catalog completeness is not proof of
authenticity, remote Git delivery, current hosting, or the absence of later
withdrawals. Every receipt says `source_only: true` and
`remote_delivery_verified: false`. No Git push, external fetch, decryption,
scanner executable or source-supplied instruction runs during recovery.

## Small API, SDKs and agents

| Interface | Preview | Restore |
| --- | --- | --- |
| HTTP | `POST /v1/spaces/{id}/journal-recovery/preview` | `POST /v1/spaces/{id}/journal-recovery` |
| Python | `preview_journal_recovery(id, input)` | `restore_journal(id, input, idempotency_key=key)` |
| TypeScript | `previewJournalRecovery(id, input)` | `restoreJournal(id, input, key)` |
| Private agent catalog | `memory.journal.preview` | `memory.journal.restore` |

Preview accepts `identity_mode` (`original` by default, or `copy`), the complete
catalog as a string, `files` with relative `path` and complete UTF-8 `text`,
explicit `withdrawn_ids`, and optional `reject_personal_data`.
Restore adds the returned `preview_sha256`, literal `true` for
`reviewed_complete_inventory`, `reviewed_withdrawals` and
`acknowledge_source_only`, and an `Idempotency-Key` header.
Discover the exact schemas through [agent control](agent-control.md).
File contents use private transport and do not belong in a shared prompt.

## Resumable API, SDKs and agents

The base path is `/v1/spaces/{space_id}/journal-recovery/uploads`.

| Action | HTTP suffix | Python client | TypeScript client | Agent suffix |
| --- | --- | --- | --- | --- |
| Begin with an idempotency key | `POST /` | `begin_journal_upload` | `beginJournalUpload` | `begin` |
| List own retained uploads | `GET /` | `list_journal_uploads` | `listJournalUploads` | `list` |
| Inspect progress | `GET /{upload_id}` | `journal_upload` | `journalUpload` | `status` |
| File receipts, 128 per page | `GET /{upload_id}/files?cursor=0` | `journal_upload_files` | `journalUploadFiles` | `files` |
| One chunk | `PUT /{upload_id}/files/{file_index}` | `send_journal_chunk` | `sendJournalChunk` | `chunk` |
| Decisions, at most 128 per page | `GET /{upload_id}/decisions?cursor=0` | `journal_upload_decisions` | `journalUploadDecisions` | `decisions` |
| One durable step | `POST /{upload_id}/advance` | `advance_journal_upload` | `advanceJournalUpload` | `advance` |

Agent names begin with `memory.journal.upload.`. Begin and chunk inputs use the
private file/CLI transport, never a generic shared memory prompt. Discover their
exact request and response schemas in the operation catalog. SDK methods accept
the space, upload and request arguments in the same order as the HTTP path.

Begin supplies `catalog`, declared `files: [{path, bytes}]`, `withdrawn_ids`,
`identity_mode` and `reject_personal_data`. File indices are assigned in sorted
path order. Each chunk contains `offset`, `sha256` and base64 `data`; send 256 KiB
of decoded bytes except the final chunk of each file. UTF-8 characters and JSONL
records may cross chunk boundaries. The final file byte must complete a record.

The Python `upload_journal_file(space, upload, index, binary_stream)` helper checks
length and acknowledged prefix, then streams from a seekable file. Optional
`progress` and `cancelled` callbacks report status or pause between chunks. It
leaves the caller's stream open. TypeScript exports `verifyJournalPrefix`,
`journalChunk`, `journalTransportDigest` and `JOURNAL_CHUNK_BYTES` for browser
`File`/`Blob` slices. Neither helper approves restoration.

After every file is accepted, send `finish_upload`, then repeat `review` until
state is `reviewed`. All advance commands carry the last observed
`expected_version`. Approval uses action `authorize`, the returned
`preview_sha256`, and true for `reviewed_complete_inventory`,
`reviewed_withdrawals`, `acknowledge_source_only` and
`acknowledge_resumable_batches`. Repeat `restore` until `completed`.
`restart_review` rebuilds decisions against the immutable staged inventory;
`cancel` preserves any already-restored memories.

After a lost response, read status before continuing. A stale version cannot
repeat or skip a committed batch. Chunk retries are accepted only for identical
bytes. Missing/conflicting events, incomplete inventories and changed previews
are actionable errors, never silent truncation or successful partial completion.

Migration 028 adds six private staging/progress tables and a narrowly authorized
worker cleanup function. All durable state uses PostgreSQL; no process-local
buffer, writable staging folder, new cloud account or external object store is
required. Normal backup and migration safeguards still apply.

Migration 027 adds a private origin registry for version reconciliation and
content-free quarantine state. Full database backups include that registry.
Current recovery ledgers also retain subsequent source quarantines and manual
quarantines of recovered memories, including a hold created in a space absent
from an older backup. Restore keeps that negative identity without creating a
missing space, permission or memory text. A ledger never restores newer positive
content or releases a backed-up quarantine; review the complete newer journal
or restore a newer full snapshot for that content.

A ledger containing these holds uses format version 2 and requires Mnemion
4.26 or newer. Older readers reject it. Recovery of a populated origin registry
requires a current journal-aware ledger. Conflicting identities or source
versions stop restoration before the new database becomes available. Local
edits after the backup can be protected from source overwrite, but their lost
text still requires a newer full snapshot.

No cloud service, paid dependency or model call is added.
