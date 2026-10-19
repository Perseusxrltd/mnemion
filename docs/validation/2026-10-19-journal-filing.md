# Journal filing validation — 19 October 2026

The 4.16.0 source adds separately enabled journal filing and archival. Tests use
disposable bare Git repositories, isolated PostgreSQL and generated identities.
No personal memory repository, account or production workspace was modified.

**67 focused Python checks passed** across journal capture/publication, new
filing, service permissions and historical schema upgrades. They cover:

- Latest-revision notes, whole-day minimum age, byte-for-byte archive retention,
  unchanged catalog counts, idempotent repeated runs and late archive writes.
- Concurrent publishers with a full refetch/reprojection before retrying,
  partial note batches that leave journal files in place, and reappearing files
  whose distinct serialization is retained while logical operations deduplicate.
- Deletion/quarantine view invalidation and refusal to ingest old generated
  notes, including copied marked notes and damaged headers in the reserved folder.
- Preservation of unrelated files, visible conflicts for edited views, and
  source withdrawals that clear an edited body while retaining Git history.
- Explicit filing opt-in, scoped reviewer access, paused/revoked publishers,
  stale policy versions, pending local publication, observed counts/errors and
  a policy change while a prepared archive waits to push.
- Real HTTP and Python-client filing, plus older-client configuration that
  omits filing fields and preserves the current schedule.
- The additional concurrent-append case requested in issue 39: a second native
  save arrives after Git uploads the first batch but before acknowledgment.
  Only the uploaded event becomes pushed; the second event remains durably
  queued and is acknowledged by its own later publication.
- Migration from every preceding schema prefix 013–022, retained accounts,
  keys, grants and memories, and company-session continuity. A separate 022→023
  case compares every existing publisher field and checks all new defaults;
  filing stays disabled and cannot be scheduled after the upgrade alone.

**15 TypeScript client checks passed**, including request versions and server
compatibility. Web and Electron frontends compile and use existing Perseus components;
this records compilation, not a separate desktop UI acceptance session.

The same source batch addresses issue 40's Grok Build format gap. **17 parser and
companion checks passed** across the existing formats and new ACP sessions,
including streamed Unicode/text spacing, literal Unicode separators in JSONL,
Windows line endings, separate sessions/message identities,
first/last chunk timestamps, explicit event deduplication/conflict handling,
non-message exclusion, stable raw provenance and repeat/append companion IDs.
Unknown updates remain raw; incomplete JSONL still fails the normal inventory.
These are synthetic format/connector checks, not a live Grok deployment claim.

**12 agent-catalog and connector-runner checks passed** alongside the new
concurrent-append case. The generated contract has 126 reviewed operations.
Issue 41's bounded live-conversation adapter remains separate work; normalizer
support does not make a growing, incomplete or oversized file a complete source.

Repository formatting/lint, both offline dependency-lock checks, release metadata
and the staged-change secret scan pass. The offline documentation, release notes
and generated HTTP/agent schemas are updated with this source.

The implementation reads bounded Git object batches and uses a private SQLite
projection with a 2 MiB cache. Count/byte/file limits are described in the guide.
These source checks do not establish large-company throughput, live Git-provider
acceptance or native delivery. Native installers, uploaded-byte verification,
publication and public automatic upgrades remain independent gates recorded in
[release status](../RELEASE_STATUS.md).

Remaining issue 39 work includes app-only host enrollment, file sharding,
old-memory backfill and direct writable-space recovery. Git history and copies
retain published text; generated-view invalidation is not external-history erasure.
