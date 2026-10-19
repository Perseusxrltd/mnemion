# Recover an older agent buffer

From 4.25, Studio and the authenticated API can reconcile the external JSONL
prototype described in [issue 39](https://github.com/Perseusxrltd/mnemion/issues/39).
This copies available records into a **private native space**. Recovered memories
can be edited normally, have immediate keyword search and enter the ordinary
semantic-index queue. The original buffer ID remains discoverable as provenance;
the new native ID is deterministic for the destination space and import source.

This is source recovery. It does not reconstruct missing revisions, original
accounts, grants, application keys, attachments or secrets. Use a verified
[host package and current deletion/access ledger](host-recovery.md) for complete
workspace recovery. Missing current office data is not recovered by this feature.

## In the app

1. Preserve the original files and independently retrieved remote commits.
   Reconcile which records were withdrawn or superseded, and which bytes were
   actually delivered. The prototype has no trustworthy built-in withdrawal
   ledger, and its old file-hash receipt can include later, unpublished appends.
2. Create or choose a private native space with **only your administrator grant**,
   no connector binding and no Git publication policy. Organization administration
   and administrator access to that space are both required.
3. Open the space's **Git journal** page and **Recover an older buffer**. Choose
   an import source name, such as `office-buffer`. Keep that name and destination
   for every batch and retry from this buffer.
4. Select complete, decrypted UTF-8 `.jsonl` files and enter all known withdrawn
   original record IDs. A batch accepts at most 100 distinct positive records,
   1 MiB of UTF-8 input and 1,000 withdrawn IDs. Withdrawals can be supplied alone.
   The file picker accepts up to 32 files within the same total limit. Larger
   archives need batches of complete lines; do not split a line or silently drop
   the unfinished end of a live file.

   The service also retains its 2 MB limit on the complete encoded HTTP request.
   A heavily escaped payload may need a smaller batch even below the JSONL limit.
5. Review the counts and identities. Identical duplicate lines are combined;
   conflicting duplicates, malformed records or incomplete final lines stop
   review. Secret-like data is rejected. Recognizable personal-data checks are
   on by default; an administrator can explicitly permit that data in this
   private space. These pattern checks are not a complete PII classification.
6. Confirm that you reviewed withdrawals and understand the recovery scope, then
   **Import reviewed batch**. Rejected/conflicting records stop the whole batch.
   Changed input or destination state requires a fresh review. An uncertain
   response can be retried with the same review and idempotency key.

The app holds selected plaintext in page memory, sends it to the selected
workspace when you request review/import, and does not save it in browser
storage. The server parses it in memory without plaintext temporary files.
Use **Clear selected files** or **Prepare another batch** to release the page's
references. This is not a claim of secure erasure from operating-system memory.

## Identity, edits and withdrawals

The prototype schema is `{id, ts, desk, kind, text, subject?, important?, journal?}`.
`id` is a UUID, `ts` is an ISO timestamp with its time zone, and `kind` is `memory`
or `action`. Other fields are refused, rather than silently discarded. Both kinds
become native `note` memories; the original kind, writer label, timestamp and
journal reference are retained in `metadata.buffer_import`. The original timestamp
is source provenance; the database records the actual import time separately.
Windows CRLF, a leading UTF-8 BOM and Unicode text are supported.

The importing administrator creates these records. A `desk` label cannot become
a principal or grant access. After reconciliation, share the space explicitly
using its normal access controls. Original plaintext should not be committed to
a public repository or added to ordinary shared notes.

Stable aliases and source fingerprints prevent repeat imports from duplicating
memories, even after an ordinary idempotency receipt expires. Existing native
edits and quarantine remain unchanged. Reusing an old record ID for different
source content requires reconciliation; the importer never overwrites it.

Explicit withdrawals are applied before any future import can revive that ID.
They persist even if the positive record has never been imported. Deleting an
imported memory normally also prevents resurrection after its content is purged.
Withdrawals address only this destination/import source; they do not erase old
Git commits or other independent copies. A different import source name creates
a different namespace, so retaining that name matters.

All changes in one batch, its aliases, denial records, indexing operations and
receipt commit together. Current organization access and space state are checked
again at application time. Concurrent import approvals serialize with permission
and journal-policy changes. No new database-owner credential is needed.

## Encrypted originals and publication

Some versions of the external prototype publish only age-encrypted
`_enc/...jsonl.age` files. Preserve that boundary. This importer does not fetch,
decrypt or replace those files, infer their remote acknowledgments, or enroll a
plaintext Git destination. Obtain an authorized private decrypted copy using the
original key and verify it against the preserved encrypted source. Ciphertext
alone cannot reconstruct the record contents.

A destination with any Git publication policy is refused, including a paused
policy: ordinary capture can continue while publication is paused. Recover into
a private space first. Any later sharing, native journal setup or existing-memory
backfill is a separate explicit publication decision. An existing encrypted
publication design must not be replaced by plaintext Git without that review.

Native journals still need an unused prefix such as `memory/native-buffer`.
The older files do not become valid native catalogs merely by importing them.
`remote_delivery_verified: false` in every import receipt is intentional.

## SDK and agent controls

| Operation | HTTP | Purpose |
| --- | --- | --- |
| `memory.buffer.preview` | `POST /v1/spaces/{space_id}/buffer-import/preview` | Validate input, identity reconciliation and current destination state. |
| `memory.buffer.import` | `POST /v1/spaces/{space_id}/buffer-import` | Apply the exact reviewed batch with an `Idempotency-Key`. |

Both take `namespace`, `jsonl`, `withdrawn_ids` and optional
`reject_personal_data` (default `true`). Import additionally requires the returned
`preview_sha256`, `reviewed_withdrawals: true` and `acknowledge_source_only: true`.
Retain one idempotency key (at most 120 characters) across uncertain retries.
The preview contains counts, bounded identities and safe writer labels, without
echoing memory text or rejected secret-like labels. Review/import inputs are
private agent operations; use a private input file or stdin, not shell arguments.

Python provides `Client.preview_legacy_buffer` and `Client.import_legacy_buffer`
with the validated `BufferPreviewInput` / `BufferImportInput` models. TypeScript
provides `previewLegacyBuffer` and `importLegacyBuffer`. Studio checks the connected
server's version before offering the feature. An updated desktop attached to an
older host cannot add that host capability on its own.
