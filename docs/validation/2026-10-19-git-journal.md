# Git journal validation — 19 October 2026

The 4.15.0 source advances issue 39 with opt-in native-memory capture,
publication and source replay. [The guide](../service/git-journal.md) describes
consent, retained history, identity boundaries and remaining work.

Tests use disposable local bare Git repositories, isolated PostgreSQL databases
and generated fixture identities. No user memory repository or hosted workspace
was modified. This is not a live Git-provider or remote host-reset claim.

- **125 focused Python checks passed** across journal capture/publication,
  native transactions, recovery, source ingestion, SDKs and agent contracts.
  This includes **38 journal/write-back cases** and upgrades from all nine
  preceding schema prefixes, 013–021. Upgrade checks compare every original
  row hash and require the two new journal tables to be empty.
- Journal cases cover strict parsing, scans before commit, durable local
  acknowledgment, post-commit retry with the same key, real Git acknowledgment
  for important saves, remote conflicts, changed-history refusal, rollback,
  quarantine/deletion, grant revocation and explicit repair.
- Replay checks cover duplicates, reordered active/archive records, stable
  origin identities and refusal of partial inventories that omit denials.
  Physical duplicates still consume resource limits.
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

Native packages, independent uploaded-byte verification and public automatic
upgrade rehearsals remain separate pipeline evidence in
[release status](../RELEASE_STATUS.md).

Unfinished acceptance includes librarian folding/archival, complete app host
enrollment, automatic file sharding, representative live-provider capacity and
direct writable-space reconstruction. Source replay retains provenance IDs but
does not replace complete workspace recovery.
