# Resumable native journal recovery — 20 October 2026

The 4.29 source extends complete-journal recovery beyond the earlier 1 MiB and
1,000-identity limits. This report separates source acceptance from the native
installer and public-update gates tracked by [release status](../RELEASE_STATUS.md).

## Implemented and verified

The app, Python/TypeScript SDKs and private agent catalog use the same PostgreSQL
staging and review service. Uploads use fixed 256 KiB binary chunks, byte hashes,
durable parser tails and locally verified prefix receipts. A complete inventory
is required before review and approval. Reviews and writes are bounded to 64
identities and 2 MiB of staged record data per batch. All current negative
source decisions precede positive content. A changed destination stops the
relevant batch and requires review; previous accepted batches remain explicit.

- **40 existing recovery tests passed** after extracting the shared transactional
  apply routine. Original IDs, explicit copies, local edits, later quarantines,
  current ledgers, provenance and complete-backup restoration remain covered.
- **11 new PostgreSQL/HTTP tests passed**. A 1,030-positive-identity inventory
  exceeds both old limits, resumes in a new service instance, rejects changed
  retries and applies negatives first. Tests also exercise partial restoration,
  current edits and fresh review, private authorization/RLS, quotas, expiry,
  bounded cascade cleanup, incomplete/conflicting files, archive holds/releases,
  large byte-limited reviews and Python/private-agent parity.
- **22 agent-contract and migration tests passed**, including upgrade from schema
  027 to 028 with previous keys, grants and memory inventory retained. Generated
  OpenAPI and private operation schemas match the new routes.
- **19 TypeScript client checks passed**, including byte-exact transport receipts,
  changed-prefix rejection, bounded Blob reads, paging and versioned controls.
  Studio's production build and both packaged frontend bundles passed.

## Actual app workflow

A disposable real PostgreSQL workspace and the built 4.29 Studio used a normal
browser login and native folder picker. The selected folder contained active
files, an archive and a numbered continuation: **2,166,409 bytes, 85 distinct
records and 83 memory identities**.

The transfer paused after an accepted 536-byte first file. Reloading cleared the
browser-only key; signing in again exposed the saved upload. Selecting the same
original folder resumed it. Complete review showed **81 creates, one retained
withdrawal and one quarantine hold**, with zero identities applied before
approval. Three acknowledged batches completed recovery. The original current
memory content and UUID were read back through HTTP. There were no browser
console errors and no horizontal overflow at a 390-pixel viewport.

The test used synthetic content and the deterministic transaction-test embedder;
it does not claim retrieval quality, semantic-index throughput, a maximum-size
2 GiB run or a new native installer acceptance result. It made no paid model calls
and did not modify the real shared workspace or user memories.

## Operational boundaries

Migration 028 adds six private tables and a narrow worker cleanup function.
Staging is ordinary private database content and can be present in full backups.
Current permissions are checked for every step. Idle/completed staging expires
following the documented 24-hour policy, with bounded asynchronous deletion.
Cancelling never undoes restored memories. Full accounts, vault secrets, grants,
attachments and revision history still require complete workspace backups.

The [guide](../service/journal-recovery.md) documents exact limits, quotas,
retries, review semantics and API/SDK/agent use. Broader host provisioning,
provider sign-in acceptance and the unavailable original office remain separate.
Strict full-roadmap coverage stays **17/64 (26.6%)**.
