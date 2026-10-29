# MemPalace and Mnemion: product review, 29 October 2026

**Decision:** keep Mnemion's shared-service architecture and finish its reliable
daily workflows. Adapt MemPalace's guided maintenance, native agent capture,
compact working context and incremental processing. This review provides no
evidence that another full rebuild would improve the product.

Mnemion has a broader implemented organization, desktop and administration
surface. MemPalace offers deeper integration in some agent workflows and a
clearer initial promise: install it, retain conversations, recall them. Breadth
does not establish reliability or quality leadership. Mnemion's outstanding
search, source-freshness and field-acceptance work still limits the experience.

## What was actually reviewed

| Snapshot | Verified state |
| --- | --- |
| MemPalace published package | [3.11.0](https://github.com/MemPalace/mempalace/releases/tag/v3.11.0), released 14 October; PyPI also reports 3.11.0. Release commit `602d796c699cabba2971982cd9dccbbf46abfe79`. |
| MemPalace development | [`84582fb055a6429261f9c779da86c0561ec80adc`](https://github.com/MemPalace/mempalace/tree/84582fb055a6429261f9c779da86c0561ec80adc), committed 25 October. Its files say 3.12.0, but [release promotion #2860](https://github.com/MemPalace/mempalace/pull/2860) remains open. |
| Mnemion published product | [4.46.52](https://github.com/Perseusxrltd/mnemion/releases/tag/v4.46.52), published 29 October at 09:55:54 UTC; source `839a25055cb3cfe9388eed8ba1a2c0a78b447f2d`. The 4.46.53 fixes remain candidate work at this review. |

The review covers current releases, selected implementation and test files,
documentation, package metadata, committed benchmark results and a dated sample
of recently updated issues/PRs. It is not a new installation, performance
benchmark, exhaustive security audit or complete issue triage of MemPalace.
The [source manifest and arithmetic](2026-10-29-mempalace-evidence.json) pin the
evidence. The [9 October study](2026-10-09-mnemion-study/LANDSCAPE.md) remains a
historical comparison; 3.11.0 was not yet published at that earlier checkpoint.

## Product comparison

| User need | MemPalace at the reviewed snapshots | Mnemion's available behavior and remaining gap |
| --- | --- | --- |
| Start using memory | CLI/Python package, agent-guided setup, plugins/hooks and Docker; a local store needs no PostgreSQL server. Remote agents use a shared hub. | Studio for Windows/macOS/Linux, local hosting or connection to a team service, web UI and agent controls. Complete fresh-machine onboarding remains partial. Make the first connection, first saved memory and first successful recall one obvious journey. |
| Work across agents | HTTP/stdio MCP, hub-aware proxies, full and three-tool MCP variants, diaries and logstream. A real Hermes `MemoryProvider` implements per-turn filing and context hooks. | MCP, SDKs, compact discovery, native configuration and Perseus XR connection packages. A Hermes MCP configuration is not equivalent to a native automatic memory provider. Complete per-provider capture/reconnect journeys remain open. |
| Company control | Shared hub with bearer-token access and agent naming. Replica design explicitly trusts admitted devices with the whole personal palace. | Individual accounts, organization sign-in, scoped principals/spaces, revocation, reviewer/admin controls and a separate credentials vault. These are stronger foundations for compartmentalized team use; complete corporate/fleet acceptance remains partial. |
| Retain source evidence | Verbatim conversation drawers. 3.11 fixes discarded exchanges; development adds retained raw bytes, transformation provenance, prior text revisions and write-before-prune mining. | Source revisions, exact citations, controlled raw capture, revisioned corrections, Git journals and guarded recovery. Provider coverage and the complete layered librarian remain unfinished. Reuse the upstream failure cases to test our existing contracts. |
| Organize and navigate | Wings, rooms, drawers, tunnels, entity hallways, temporal KG and a five-part organization audit with guided repair. | Search, wiki/graph, 3D map, insights, librarian organization/review proposals, schedules, diffs and guarded undo. The missing product opportunity is one actionable organization-health workflow tying these together. |
| Begin a new agent session | Progressive identity/story/room/deep-search context; documented typical wake-up is roughly 600–900 tokens, with bounded selection. | Profile/context retrieval and token budgets exist. A consistent provider-native startup brief combining current work, relevant decisions and source links is incomplete. MemPalace's layer numbers describe context loading, not Mnemion's planned raw/consolidated memory layers. |
| Choose models | MiniLM, multilingual EmbeddingGemma, opt-in EmbeddingGemma 2, remote compatible embeddings, and optional local/cloud LLM steps. | Pinned CPU E5/BGE and operator-approved Ollama/compatible local or cloud profiles; per-space candidate generations, evaluation and activation without relabeling existing vectors. The best default remains an evaluation question. |
| Search media | 3.11 includes opt-in image/audio/video file-reference retrieval with EmbeddingGemma 2. It is experimental, with a small Mac acceptance corpus and explicit codec/missing-file limits. | No equivalent accepted native multimodal retrieval journey was found in the reviewed current service guides. This is a worthwhile optional research candidate, not a reason to bundle PyTorch or media weights in every installer. |
| Download and update | Python dependencies and model downloads are separate. Optional native executables are vector utilities, not a complete desktop app. Guided update checks are opt-in and do not install automatically. | Verified desktop distributions and automatic updates, bundled hosting runtimes and OS integration. Published 4.46.52 installers are about 220–271 MB; Windows x64 is 225,938,684 bytes. Continue footprint work and actual update acceptance. |
| Keep working during an outage | Logstream replication and memory read replicas are described as shipped steps. Full memory multi-writer convergence remains a draft; a hub outage still matters. | Durable local capture, saved connections, host administration and independent encrypted recovery provide continuity components. Transparent offline team replicas and complete fleet failover remain unfinished. Neither product justifies an "always reachable" claim. |
| Prove quality | Multiple benchmark scripts, committed per-question outputs and hardware/model experiments. Organization scores are navigation heuristics. | In-app evaluation sets, held-out splits, pinned manifests, per-case evidence, comparisons and exports. Representative common-corpus, cross-hardware and real-team baselines remain open. There is no defensible head-to-head winner yet. |

Mnemion's supporting guides: [onboarding](../implementation/app-onboarding.md),
[agent packages](../service/agent-packages.md),
[organizations](../service/organizations.md), [vault](../service/secrets-vault.md),
[capture](../service/live-conversations.md), [librarian](../service/librarian.md),
[embeddings](../service/embeddings.md), [evaluations](../service/insights.md),
[map](../service/memory-map.md) and [continuity](../implementation/workspace-continuity.md).

## What changed upstream since our first study

**Published in 3.11:** organization audit and guided repair; optional
EmbeddingGemma 2 and media references; recorded embedding identity with mismatch
refusal; more efficient metadata updates; fixes for conversation text loss,
large-palace status/mining work and HTTP/recovery correctness. The release notes
also warn that existing conversations are re-mined once where transcripts remain
available. Migration cost is part of the product experience.

**Only in the inspected development branch:** 3.12 source retention and
write-before-prune changes, reuse of vectors for unchanged text, UTC timestamps,
consistent graph/project routing, prior text revisions, Windows exclusive hub
port handling and SQLite-backed hallways. The hallway implementation indexes by
wing, updates changed derived records and migrates its old JSON transactionally.
Older writers do not follow the new store; the changelog requires upgrading every
installation sharing it. This is not a released automatic-upgrade guarantee.

**Still proposals/open work:** [background room suggestions #2904](https://github.com/MemPalace/mempalace/pull/2904),
additional hook providers and complete multi-writer memory replication. The
current [replication RFC](https://github.com/MemPalace/mempalace/blob/84582fb055a6429261f9c779da86c0561ec80adc/docs/rfcs/004-replicated-palace.md)
expressly separates already-shipped steps from unlanded operations and says
team/partial-access workflows require another capability layer.

## What the benchmark numbers establish

The committed April result files contain **483 hits out of 500** for raw mode
and **443 out of 450** for the held-out hybrid run: 96.6% and 98.44%.
This review recomputed those averages from the stored per-question metrics. It
did not regenerate embeddings, rerun retrieval or independently verify labels.

The scorer calls the metric `recall_any@5`: did at least one labeled supporting
session appear in the first five results? This is a session hit rate. It does
not require all evidence needed for a multi-session answer, validate a generated
answer or demonstrate performance on a large shared database. The default raw
harness builds a fresh corpus per question and joins user turns by session;
that differs from an always-running multi-tenant service over all source types.
The files are historical results, not a rerun of today's 3.11/3.12 product.

For a fair Mnemion comparison, freeze the same corpus, labels, split, retrieval
unit, K, embedding model and context-token budget. Report session hit rate,
all-support coverage, passage relevance, evidence integrity, unanswerable cases,
latency percentiles, CPU/RAM, indexing/update cost and failure recovery
separately. Add revoked permissions, deleted evidence, changed facts,
multilingual questions and concurrent capture. Keep held-out questions outside
tuning; publish per-case failures. Use our existing evaluation system.

MemPalace's audit score is also not answer accuracy. Its code combines generic
room share, naming drift, link artifacts/coverage and predicate reuse. A high
score means those organization heuristics look healthy. We should expose the
underlying measurements and findings instead of calling such a score memory IQ,
truth, safety or retrieval quality.

## Adoption backlog, mapped to existing requirements

These are reviewed candidates and delivery criteria, not newly shipped features.
They retain the existing ordering: urgent reliability repairs alongside the
active telemetry milestone, then complete user journeys. All 66 requirement
states remain unchanged. No item replaces current issues or earlier roadmap work.

| Priority | Adaptation | Existing scope and acceptance |
| --- | --- | --- |
| First | **One memory-health and repair journey.** Show stale/unindexed sources, naming drift, duplicate candidates, generic categories, disconnected evidence and noisy graph links; open the relevant reviewed action. | R06/R07, V01/V03, U01. Same bounded read-only report in app/API/MCP; exact scope and evidence, preview, permission recheck, resumable application and conflict-safe undo. No automatic deletion or authority change because a model or heuristic recommends it. |
| First | **Provider-native capture and recall.** Adopt the Hermes lifecycle pattern and extend supported hooks: startup context, allowed turn capture, pre-compaction handling and reconnect. | C04/C05, R07, U01. One durable, idempotent path per event; retained custody before acknowledgement, restart replay, visible overflow/offline state, per-provider consent and no cross-space leakage. Support only content the provider actually exposes and the user permits. |
| First | **A compact session brief.** Current task, unresolved handoffs, recent relevant decisions and cited facts; deeper retrieval on demand. | F08, R04/R07, A12; issue 48. User/agent token budget, fresh permissions, explicit stale state, exact evidence links and evaluation against ordinary context retrieval. Retrieved text must not become trusted system instructions. |
| First | **A reproducible product comparison.** Reuse upstream's transparent per-question record, with the common inputs above. | V02, R02/R04/R06; issue 47. One declared experiment, publish failures, compare cold/warm and read-while-capture behavior. No new leaderboard from incompatible scores. |
| Next | **A smaller client-only distribution with optional hosting components.** Separate connecting to a team host from installing local database/model runtimes. | F05/F06, U01/U02, R03; [footprint plan](../implementation/installer-footprint.md). Preserve the full/offline-host option, signed component hashes, resumable downloads, rollback, free use and all OS/CPU paths. Measure complete downloads and installed size separately. |
| Next | **Incremental graph and maintenance work.** Scope changes to the affected source/space, reuse unchanged embeddings and avoid global metadata/cache rebuilds. | R04, V03/V04; issue 47. Compare one-source changes and concurrent recall on representative inventories; preserve permission freshness, deletion and model identity. PostgreSQL already supplies indexed storage in Mnemion: port the principle, not a second authoritative SQLite database. |
| Next | **Durable task/handoff events.** Separate active work from memories of completed work, with claim, reply, acknowledgement and artifact hashes. | F02/F08/A03; issue 48. Resume by cursor, reject stale claims, preserve identities and current authorization, export/recover and migrate existing LEDGER/DISPATCH only after verified parity. Never execute a retrieved instruction just because an event exists. |
| Evaluate | **EmbeddingGemma 2 and optional multimodal search.** Compare an opt-in provider against E5/BGE and other configured models. | R01/R02/R03, C01. Recheck model/dependency licensing, immutable revision and dimensions; measure quality, RAM, download size and CPU latency. Test media lifecycle, missing/moved files and all supported hardware before claiming compatibility. No paid calls or automatic model downloads in this study. |
| Design | **Permission-aware offline replicas.** Learn from snapshot-plus-tail recovery and explicit peer presence. | A06/A09/A12, U02. Per-device least privilege, bounded offline grants, revocation/deletion reconciliation, conflict handling, encryption and independent recovery. Full-palace personal device trust is unsuitable for organization compartments. |

Our small MCP discovery/read/write interface, embedding fingerprints, versioned
evidence, user-selected models and source-preserving librarian already implement
important principles from upstream. Reuse them. A new query language, all six
storage backends or another complete rewrite would add migration and maintenance
work without a demonstrated benefit for the current failures.

## Failure cases worth carrying into qualification

Recent upstream reports include [cache eviction after any write #2907](https://github.com/MemPalace/mempalace/issues/2907),
[quarantine during an active index write #2905](https://github.com/MemPalace/mempalace/issues/2905),
[cross-palace graph sidecars #2710](https://github.com/MemPalace/mempalace/issues/2710),
[checkpoint lock duration #2886](https://github.com/MemPalace/mempalace/issues/2886)
and [readonly hook checkpoints #2884](https://github.com/MemPalace/mempalace/issues/2884).
Their reported timings/data loss are reporter observations, not results
reproduced here. The cache-clearing and sidecar-placement patterns are present
in the inspected source. Copying those implementations would import their risks.

The native Hermes provider also uses an in-memory background queue and logs a
dropped turn when full. Its lifecycle integration is valuable; that queue is not
an acceptable substitute for Mnemion's durable capture custody. No retry or
end-of-session safety net should silently duplicate already-filed turns.

Mnemion's own [issues 44/47/48/49](../implementation/multi-agent-field-readiness.md)
and the new [Mac keychain issue 50](https://github.com/Perseusxrltd/mnemion/issues/50)
remain open at the final review: provider-specific acceptance, search/freshness,
tasks/vault portability, affected-Mac launch and repeated keychain prompts. A larger feature list does not
cancel them. The public product must be judged by these daily user journeys.

## Licensing and implementation boundary

The inspected MemPalace [license](https://github.com/MemPalace/mempalace/blob/602d796c699cabba2971982cd9dccbbf46abfe79/LICENSE)
is MIT, copyright 2026 MemPalace Contributors. Code can be adapted while retaining
the required copyright and license notice in substantial copies. Model weights,
dependencies, branding and third-party data need their own review. Mnemion's
existing upstream attribution remains intact. This study copies no runtime code
and installs no model or third-party service.
