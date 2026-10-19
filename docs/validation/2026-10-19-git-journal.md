# Git journal validation — 19 October 2026

The 4.15.0 source advances issue 39 with opt-in native-memory capture,
publication and source replay. [The guide](../service/git-journal.md) describes
consent, retained history, identity boundaries and remaining work.

Tests use disposable local bare Git repositories, isolated PostgreSQL databases
and generated fixture identities. No user memory repository or hosted workspace
was modified. This is not a live Git-provider or remote host-reset claim.

- **126 focused Python checks passed** across journal capture/publication,
  native transactions, recovery, source ingestion, SDKs and agent contracts.
  This includes **39 journal/write-back cases** and upgrades from all nine
  preceding schema prefixes, 013–021. Upgrade checks compare every original
  row hash and require the two new journal tables to be empty.
- Journal cases cover strict parsing, scans before commit, durable local
  acknowledgment, post-commit retry with the same key, real Git acknowledgment
  for important saves, remote conflicts, changed-history refusal, rollback,
  quarantine/deletion, grant revocation and explicit repair.
- Replay checks cover duplicates, reordered active/archive records, stable
  origin identities and refusal of partial inventories that omit denials.
  Physical duplicates still consume resource limits.
- Retrying a push after its daily file was moved to the archive preserves the
  existing catalog count. Late records append to the archive, keeping retries
  idempotent and preventing active/archive duplicate counts from blocking replay.
- A real Git → HTTP connector → PostgreSQL round trip retains the imported
  memory/revision IDs on repeated sync, refuses an omitted deletion and removes
  the imported copy when the complete journal becomes available again. Original
  native IDs remain provenance; this test does not claim writable-space restore.
- A blocked publisher does not prevent a new local receipt from being written.
  Operator enrollment refuses stale replacement and never reflects a proposed
  credential-bearing URL.
- **14 TypeScript client checks**, web and Electron frontend builds pass. The
  journal page reuses the existing Perseus components and disables unsupported
  server controls. This records compilation, not a separate visual acceptance.
- The **125-operation** agent contract, Python lint, both dependency locks and
  release metadata checks pass. One host-recovery check initially lacked `uv`
  on the test runner's PATH; it passed after exposing the already installed
  pinned binary. No product behavior was weakened to pass that check.
- The first 4.15.0 release preflight found one unformatted CLI registration.
  Its formatting was corrected without a behavioral change. Release startup
  now runs format/lint locally before reserving a release branch; the complete
  497-file format check and lint pass.
- Release attempt 2 passed **334 legacy tests** (one skipped), then its legacy
  coverage calculation included the new service journal modules at zero coverage.
  Those modules and journal projection are now measured by the service gate and
  excluded from the legacy denominator. Both thresholds remain unchanged
  (75% service, 45% legacy). Their **39 focused tests cover 88.79%** of the 758
  journal/projection statements. No tested module is excluded from both gates.
- The next release service run passed **1,279 tests** with **86.01% coverage**,
  but exposed a test assumption that a deletion would finish within eight global
  worker claims. The test database contains other tenants' queues. The corrected
  test deliberately puts nine indexing jobs ahead of its deletion and waits for
  that deletion's completion receipt under a deadline. Real worker purging and
  the assertion that journal revision references are cleared remain exercised.
- A Mac main-branch check hit an anonymous Hugging Face repository-listing
  HTTP 429; the release's equivalent Apple Silicon model check passed. The local
  model loader now uses cached pinned files first, then exact file resolution for
  missing files. **35 model/cache/idle checks passed**, including actual E5/BGE
  retrieval and idle reload with network access disabled. Cache checks prohibit
  network calls for complete caches, reject mixed snapshots/unsafe paths and
  ensure corrupt model bytes never reach inference.
- A fresh tokenizer-configuration download used the Hub's file-resolver quota
  and did not list the repository tree. Cold downloads still use the network.
  The corrected journal suite and new cache checks passed together (**20 tests**).

Native packages, independent uploaded-byte verification and public automatic
upgrade rehearsals remain separate pipeline evidence in
[release status](../RELEASE_STATUS.md).

Unfinished acceptance includes librarian folding/archival, complete app host
enrollment, automatic file sharding, representative live-provider capacity and
direct writable-space reconstruction. Source replay retains provenance IDs but
does not replace complete workspace recovery.
