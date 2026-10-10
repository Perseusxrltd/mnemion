# Mnemion v4 implementation status

For current delivery priorities and the platform-v1 freeze, use the
[product roadmap](../ROADMAP.md) and [4.0.0 release notes](../releases/4.0.0.md).
This chronological ledger also retains earlier checkpoints and the broader
program acceptance criteria; historical counts are not final-version results.

Objective: deliver a professional shared memory product for applications, teams,
assistants, and programs, retaining Obsidian visualization. The objective remains
active until the implementation and release gates are verified.

The user additionally requires full macOS, Windows, and Linux compatibility.
Native packaging, window behavior, local Obsidian refresh, installation/update
instructions, and platform validation are release requirements for all three.

Requirements and acceptance criteria are defined by the
[study](../research/2026-10-09-mnemion-study/README.md),
[architecture](../research/2026-10-09-mnemion-study/ARCHITECTURE.md), and
[roadmap](../research/2026-10-09-mnemion-study/ROADMAP.md).

## Worktree and reproducibility

- Current implementation: `main`. The rebuild and free Mac updater were merged at `da74785f67f96d0fd375e7925d23284c435b6f99`. The original implementation branch was `codex/mnemion-v4`, based on `c670e3039d2f7b43dbb00a2157e420e665203979`.
- Pre-existing tracked and untracked work was preserved before implementation. A WSL restart on 10 October cleared the temporary backup and fixture directory; the working tree remained intact. A fresh private snapshot now preserves the complete current tree in persistent local validation storage.
- Local test runs use isolated temporary profiles and an environment installed from the refreshed `uv.lock`. No production memory or personal Obsidian vault has been migrated.
- A real local PostgreSQL 16.2 instance with pgvector was verified through a temporary `pgserver` development installation. This binary is test tooling, not the production database distribution.

## Implemented work, 9 October 2026

- Search reacquires a collection created after startup.
- Hybrid ranking sorts after confidence weighting, applies a normalized rank threshold, and enforces the final result limit.
- Graph search checks the actual source, current trust, and requested scope; unbacked, removed, or quarantined source facts cannot enter ordinary search.
- Cognitive retrieval resolves current trust; reconsolidation replaces evidence when source text changes; reconstruction bounds topic expansion.
- Added a durable legacy ingestion journal and shared writer. MCP saves/diaries, miner, conversation miner, sweeper, capture, and autosave hooks now use it. Retries replay interrupted vector/sidecar writes; successful completion persists lexical and trust state together. Completed jobs discard their content payload.
- Idempotent trust creation preserves the existing status and avoids spurious creation history. Edited source text invalidates its older cognitive and graph projections.
- Legacy deletion now records a durable denial before deleting projections; retries cannot recreate a deleted ID. Query-specific recall and NDCG calculations were corrected, unexecuted comparison modes report no score, and Studio provider keys are redacted from configuration responses.
- Added the PostgreSQL service: authenticated principals, explicit spaces/grants, row-level isolation, immutable source and memory revisions, optimistic corrections/review, transactionally accepted writes, idempotency receipts, indexing leases/heartbeats/retries, and deletion/purge receipts. API and worker logins are separate and cannot own the schema or bypass row-level policy.
- Added local multilingual E5 retrieval with pinned model/tokenizer hashes, chunk offsets, index-generation identity, lexical and semantic readiness, temporal/filter-aware recall, cited sources, and bounded context packs. Transaction fixtures use a separate test-only embedder; the real-model integration test checks multilingual retrieval and long-input chunking.
- Added the `/v1` HTTP surface, typed Python and TypeScript clients, and an MCP 2.x gateway over that HTTP contract with stdio and Streamable HTTP transports. HTTP MCP calls use each caller's credential.
- Added scoped Obsidian ZIP export and a shared local refresh engine. Standard YAML/Markdown, source block citations, stable paths, wikilinks, and graph navigation are retained. Refresh preserves personal sections and unmanaged files, records edited-generation conflicts, handles interrupted publication, and prunes only known managed content. The service never accepts a server-side vault path.
- Split the default service installation from the optional Chroma-based `legacy` extra. Setup, API/worker commands, SDK examples, MCP configuration, and Obsidian refresh are documented in [the service guide](../service/README.md).

Additional implementation completed:

- Versioned full PostgreSQL backup/restore with manifest and per-table verification, isolated restore publication, current deletion/access-ledger reconciliation, and API-key rotation. Recovery preserves newer negative identities even when their positive record did not exist in the backup.
- Complete offline v3 profile archives include Chroma, sidecars, raw sources, core memory, wiki, and the Obsidian vault. Restores reconcile current deletions and pending writes, relocate paths, and stay paused. Updated legacy entry points honor a persistent writer pause.
- Flat JSON imports validate the entire input before opening a live backend and use the durable journal; missing lifecycle data is quarantined. Destructive replace behavior and the old Git-union sync are retired, with their historical sources retained under `docs/legacy`.
- V3 migration now creates an explicitly owned private space, retains original IDs/source bytes/trust history/correction references, reports exceptions, imports the final delta, and records a cutover boundary. Application writes use a shared transaction lock; a pause waits for acknowledged in-flight writers.
- Scoped rollback exports preserve all current v4 records, revisions, source attachments, core history, and deletion denials. Replay into a new paused v3 profile uses the legacy embedding pipeline and verifies canonical content hashes. The complete v4 tail remains available in the recovered profile.
- Studio now supports authenticated shared workspaces, save/revise/review, lexical/semantic retrieval, context packs, source evidence, original-file downloads, operations/retries, core context, credentials/grants, and Obsidian export. The default Windows package connects to the shared service through a narrow sandboxed bridge and includes a local vault refresh client.
- Native Obsidian 1.14.4 was exercised with readable note paths, wikilinks, source anchors, and a repeated refresh. The connected fixture had 17 Markdown files, 35 resolved links, zero unresolved links, and four valid source block anchors. Settings and personal annotation bytes survived refresh.

Verification completed so far:

- The latest complete regression run passed **358 tests**, skipped one, and deselected 106 benchmark/slow/stress cases. Service coverage was **83.56%**, above the required 75%. It included real PostgreSQL, real local multilingual embeddings, SDK/MCP transports, service and legacy recovery, and Obsidian refresh.
- The migration/rollback group and HTTP attachment/alias authorization checks passed in that full run, including a real Chroma rollback after new v4 writes, corrections, quarantine, deletion, and a core-block change.
- The TypeScript SDK builds and its four retry/authentication/browser-fetch tests pass. Its real HTTP integration is part of the service suite. The Studio frontend and Electron TypeScript builds pass after the desktop changes; original-file download UI also compiles.
- The supported Python 3.12/3.13/3.14 service matrix passed at the earlier core milestone; it must be rerun after the recovery/migration additions. Default service dependencies exclude Chroma; native legacy replay requires the Python 3.12 legacy environment.
- The native Windows build produced a **116 MB NSIS installer**. Payload validation and real-window rendering, sandboxed preload, local-client capability, and tray-icon checks passed. The packaged client authenticated against the real service. Native vault refresh and tray/second-instance interaction checks are being completed. The installer is **NotSigned** and has not been published.
- Advisory scans found no known advisories in the default Python production environment (57 third-party distributions), frontend, or TypeScript SDK. The Electron build dependency tree retains eight moderate affected packages from the transitive `sprintf-js` advisory; exposure/disposition and the legacy-extra audit remain to be finalized.
- OpenAPI is generated offline from the actual typed routes. Ruff checks passed on the modified service and integration files at the current milestone. Final repository formatting, CI, and runtime checks remain.

The original temporary test fixtures and raw logs were cleared by the WSL restart;
new checks use private persistent validation storage. Historical counts above
describe those earlier runs, not retained final-release evidence. Reviewable
screenshots remain under `output/playwright/mnemion-v4`. No production
profile, personal Obsidian vault, scheduled task, or GitHub release was changed.
The overall product goal remains active.

## Original program checklist (historical)

This checklist records the early rebuild checkpoint. Later entries and the
[current roadmap](../ROADMAP.md) supersede its implementation status. Broader
capacity, live-provider and answering evaluation commitments remain visible there.

- [ ] Complete memory/resource limits and observable bandwidth, selectable current embedding models with safe reindex/activation, and the configurable local/cloud librarian.
- [x] Implement and validate the detailed visual [observability and evaluations workspace](observability-and-evaluations.md), including reproducible test sets/runs, bounded execution, comparisons, exports and permission/deletion handling.
- [x] Implement complete service and legacy recovery, durable legacy writes, strict JSON imports, and replacement of unsafe Git sync.
- [ ] Finish migration/rollback edge-case and operational review, including derived legacy views and uncommon source layouts.
- [ ] Complete the bounded component/adoption decision with comparable contract and cost evidence.
- [ ] Complete the service-core release audit of the implemented PostgreSQL/auth/revision/job/readiness paths and setup commands.
- [ ] Verify tenant/space isolation, concurrent writes, retries, leases, revocations, corrections, quarantine, and deletion across every API/projection.
- [ ] Validate the implemented real embedding retrieval, fingerprinted generations, scoped fusion, citations, temporal behavior, and context budgets against the held-out and load gates.
- [ ] Complete typed OpenAPI responses, SDK integration/compatibility checks, maintained MCP transport verification, and required legacy aliases.
- [ ] Preserve Obsidian Markdown, paths, wikilinks, native graph, manifests, manual sections, and refresh/ZIP/open workflows through a copied-vault migration.
- [x] Implement and rehearse versioned recovery, v3 ownership/ID import, final delta/cutover, exception reconciliation, and replay of post-cutover writes into a new paused legacy profile.
- [ ] Adapt Studio into a coherent team/operator product with credentials, sources, ingestion, query explanation, conflicts, exports, deletion, and recovery status.
- [ ] Remediate or explicitly assess dependency advisories, update lockfiles, and pass the complete supported-runtime test/build matrix.
- [ ] Execute held-out retrieval/answering evaluation and declared load/cost/recovery benchmarks; publish the actual results and limitations.
- [ ] Verify self-hosted startup and deployment configuration, native macOS/Windows/Linux packaging and launch, supported clients, and native Obsidian visualization.
- [ ] Complete release documentation, compatibility policy, operational runbooks, support path, and requirement-by-requirement final audit.
- [ ] After product validation, audit tracked files and Git history for exposed secrets, remove temporary artifacts, organize public documentation, and leave a clean, reviewable Git state (explicit user requirement).

Completion requires evidence for the full requirements above and the detailed
gates in the linked roadmap. Passing a smaller regression suite is intermediate
progress only.


## Expanded source and feature-preservation validation — 2026-10-09

The source/identity connector contract now has Git, filesystem, rclone, Slack
and Drive adapters, scope leases, checkpoints, source conflict proposals,
operator pauses and restore-time deletion/access reconciliation. A public
adapter API supports additional company providers. Live customer-provider
authorization has not been exercised; included provider tests use explicit
fixtures plus real local Git/filesystem operations.

The [v3 feature audit](v3-feature-parity.md) now links shared conversation capture,
configuration preview/apply, source/wiki workflows, graph and curation.
[Feature decisions](feature-review.md) distinguish implemented capabilities from
optional enterprise work. Obsidian entity pages now retain evidence excerpts,
review status and revision dependencies.

The full Python 3.12 regression with real local E5, real PostgreSQL and Chroma,
and Node SDK integration passed **403 tests, 1 skipped, 106 deselected**, with
**84.96% service coverage**, in 215.35 seconds. The TypeScript SDK and Studio
production build passed. This does not certify native installers, deployment,
load performance or held-out answer quality.

Subsequent security work reproduced and fixed a check/open symlink race in the
selected-folder connector. Linux/macOS now use anchored directory descriptors;
Windows verifies the opened file handle's final path. The provider command runner
also bounds output while the process runs. Their targeted provider suite passed
11 checks before the final read-error hardening; final native verification and
a fresh publication audit remain required. Local proof logs are intentionally
kept outside the public source tree.

## Persistent release validation — 2026-10-10

The current tree is privately archived before further work. The locked Python
3.12 environment and pinned real embedding cache have been rebuilt. The public
LongMemEval source is pinned by repository revision and file SHA-256; its frozen
12-development/48-held-out question plan is versioned under `benchmarks/plans/`.
Abstention cases are identified by the dataset's `_abs` suffix, excluded from
retrieval recall, and kept for separate answering checks. The harness validates
scope, content hashes and citation offsets, compares hybrid/semantic/lexical
retrieval, and records actual bounded context coverage and uncertainty. Results
are not yet final release evidence.

Compose initialization and an explicit restore activation workflow are now
implemented and documented in the [deployment runbook](../service/deployment.md).
Activation validates the restored administrator key, completed recovery record,
migration hashes and both restricted database roles before an atomic cutover
record is written. Runtime credentials are derived and recover after interruption.
The old database and prior private operator state are retained.

The focused recovery/setup/evaluation group passed **10 tests, 1 platform-specific
skip**, including a real backup/restore, stale-key rejection, interruption after
activation publication, idempotent resumption, and preservation of the original
database. The three evaluation-metric tests passed again after adding baseline
modes and bounded-context reporting. Fresh full-suite, container, native,
performance and publication checks remain required.

The [10 October validation report](../validation/2026-10-10.md) now records the
retained full regression (421 passed), supported Python matrix, native Windows
client checks, container recovery activation, Obsidian correction/deletion refresh,
Linux payload/window checks, and the completed frozen held-out retrieval results.
It also records the indexing timeout and continuation, limited context coverage,
and the remaining answering, load, native, licensing and publication gates.

## Configurable librarian and product website — 2026-10-10

The shared librarian now supports operator-approved Ollama and OpenAI-compatible
endpoints, per-space outbound approval, optional schedules, durable call budgets,
leased low-concurrency jobs and explicit source revision dependencies. Organization
proposes titles, additional tags and summaries independently for each memory;
review proposes possible links, duplication, contradictions and stale claims in
a bounded batch. Generated output never grants access or verifies a claim.

Studio includes model/schedule controls, before/after proposals, all input
revisions and quotations, per-memory outcomes, run usage, accept/reject and guarded
undo. Applying organization preserves the canonical text, original evidence,
attachments and unrelated metadata. Deleted or quarantined inputs invalidate and
erase affected generated text, including findings influenced by uncited inputs.
Restoring a backup cancels pending jobs and requires renewed model approval.

Browser validation found and corrected premature completion of a multi-memory
run and a cramped mobile status layout. Regression tests cover complete and
mixed-size batches. Cancellation retains the database-wide slot while a request
is still in flight. The HTTP transport now enforces a total deadline across
connection, headers and body and closes interrupted requests; real loopback HTTP
tests exercise deliberately trickling responses. No live model or paid call was
used for these checks. See [the operator guide](../service/librarian.md).

The matching Perseus XR product page is prepared in a verified deployment
preview. Its existing Mnemion project card now describes shared memory and links
to the new page. The page includes platform downloads, documentation, roadmap
and optional support; download eligibility requires a complete published release.
Production promotion remains tied to the desktop publication gates. Current
validation, public scan results and remaining limits belong in the
[validation report](../validation/2026-10-10.md), not an unconditional v1 claim.


## Main integration and staged platform release — 2026-10-10

The rebuild, selectable embeddings, librarian, documentation and free Mac updater
are on `main`. Both packaged Mac architectures passed signed upgrade/relaunch
and inactivity, transfer, draft and focus guards at `873da44`; native interrupted
download, oversize, downgrade and disconnection recovery passed at `c088757`.
The [implementation report](free-macos-updates.md) links the exact workflows.

The Perseus XR product page, homepage feature and existing Lab Notes entry are
live. Ready Mac/Linux platforms are published independently while Windows release
validation continues. The release-target registry and platform-specific website
gates require complete installer/update assets for each offered platform.
Historical build counts above remain historical; the versioned release notes and
current roadmap define current availability and outstanding work.


## Platform v1 published

Version **4.0.0** is public for macOS and Linux on Intel/x64 and ARM64, from
`d66345a53329adf64c0745e599250ccddd6c8215`. Release workflow
[38077770316](https://github.com/Perseusxrltd/mnemion/actions/runs/38077770316)
passed all checks. The 26 immutable assets and their digests were verified after
upload, and the four public installer URLs returned HTTP 200. Downloads, setup,
release notes and the roadmap are available at
https://www.perseusxr.com/mnemion. Windows remains the next platform delivery;
see the current roadmap and dated validation report for the exact scope.

## Windows x64 delivery and remote-agent follow-up

The 4.0.1 release target includes Windows x64 plus both Mac/Linux architectures.
Native Windows x64 installation, authenticated upgrade and relaunch pass, with
72 installed binary hashes preserved and paths containing spaces. Windows ARM64
first installation now passes after the archive-filter correction; its automatic
relaunch remains a release blocker for that architecture. Publication proceeds
independently for the verified variants. See the
[dated evidence](../validation/2026-10-10.md#windows-x64-installer-and-updater-verification)
and [4.0.1 notes](../releases/4.0.1.md).

The next patch work includes full discoverable agent administration and reported
remote setup issues 3–10: one API/MCP endpoint, handshake authentication, explicit
scope diagnostics, remote/OAuth setup, Studio availability and non-systemd hosts.
