# Mnemion: full study and rebuild recommendation

**Study date:** 9 October 2026. **Repository:** [Perseusxrltd/mnemion](https://github.com/Perseusxrltd/mnemion). **Published baseline:** [c670e3039d2f7b43dbb00a2157e420e665203979](https://github.com/Perseusxrltd/mnemion/commit/c670e3039d2f7b43dbb00a2157e420e665203979), version 3.6.0, 21 June 2026. The local work in progress was reviewed and tested separately.

The requested product direction is **memory infrastructure for apps and teams across AI assistants, systems, and programs**.

**Required compatibility:** retain Obsidian for visualization. Standard Markdown, stable wikilinks, native graph navigation, existing vault paths, and manual edits are part of the migration and release contract.

## Recommendation

Build a new service and data core for Mnemion v4, then migrate useful existing features onto it. Keep Python, FastAPI, and the React interface unless measurements identify a reason to replace them. Make PostgreSQL the authoritative store for the initial team service, with full-text search and pgvector, a durable ingestion queue, explicit permissions, and stable HTTP, SDK, and MCP interfaces.

The reason is architectural: Mnemion currently coordinates several local stores and ingestion paths without one authoritative transaction or a common authorization boundary. Improving the UI or adding another vector backend will not establish the guarantees needed when several applications and people share memory.

The source archive, evidence links, trust history, wiki projections, and existing integrations are useful assets. A wholesale rewrite would spend time recreating them. Carry their behavior and relevant tests forward while replacing the global state and persistence assumptions beneath them.

The proposed product promise is:

> Mnemion lets applications and assistants share the right memory, with evidence, permissions, and a reliable history of what changed.

This study produced findings, reproducible diagnostics, an architecture, and an implementation plan. It does not claim that the proposed v4 service has been implemented or validated.

## Read the study

| Document | Purpose |
| --- | --- |
| [Evidence and findings](EVIDENCE.md) | Reproduced failures, code references, test results, dependency reports, and limitations |
| [Current landscape](LANDSCAPE.md) | MemPalace and seven related product families, with pinned sources and adoption decisions |
| [v4 architecture](ARCHITECTURE.md) | Domain model, storage, permissions, ingestion, retrieval, APIs, and deployment |
| [Roadmap and migration](ROADMAP.md) | Prioritized work, acceptance gates, estimates, and a reversible migration sequence |
| [Validation data](evidence/validation.json) | Machine-readable results and measured scope |

## What exists today

Mnemion is a substantial local memory application. Its Python package stores verbatim “drawers” in Chroma, mirrors some content into SQLite FTS5, and stores trust, entities, relationships, working memory, source metadata, and wiki state in a SQLite sidecar. CLI commands, MCP tools, transcript hooks, miners, capture commands, and the Studio backend access overlapping parts of this data.

The checked repository contains 271 tracked files and 269 commits. The local branch already has 45 modified tracked files and additional Windows release work. Those changes improve configuration isolation, deterministic embedding tests, Studio authentication, desktop process management, packaging checks, and interface behavior. They deserve a reviewed release path; they are not evidence that the project must be discarded.

| Area | Current assessment | Consequence for the target product |
| --- | --- | --- |
| Local capture and recall | Several working paths, with inconsistent persistence and cold-start behavior | Consolidate every writer behind one ingestion contract |
| Source archive and wiki | Raw copies, content hashes, chunk citations, generated-section boundaries, and live provenance checks | Preserve and move onto versioned, scoped storage |
| Trust and corrections | Status/history model exists; enforcement differs between retrieval paths | Make policy and provenance checks mandatory for every read |
| Retrieval | Vector + lexical rank fusion, graph injection, cognitive reconstruction | Correct ranking and evaluation before adding more algorithms |
| Team identity | Global local profile, classification through wings/rooms, caller-supplied author names | Add authenticated organizations, principals, spaces, and grants |
| Integrations | Broad local MCP/CLI surface; 47 MCP tools in the inspected registry | Offer a small stable agent surface and typed application SDKs |
| Studio | Useful desktop shell, browse/search/detail/core-memory views | Evolve into an operator console for shared memory |
| Operations | Local storage, scripts, optional Git synchronization, Ubuntu CI | Add durable jobs, migrations, recovery drills, and service observability |

“Private,” “internal,” wings, rooms, and agent names are currently useful labels. They do not establish authenticated access control between different users. This is a gap relative to the newly stated infrastructure goal, not evidence that v3 already promised tenant isolation.

## Findings that drive the decision

Fifteen targeted diagnostic cases reproduced the suspected behavior. Several use real temporary Chroma and SQLite databases; ranking cases use controlled candidates to isolate the relevant logic. These are correctness probes, not a representative retrieval benchmark.

1. **Saving and finding a memory can disagree.** A searcher initialized before the first collection exists stays empty after a successful save. The same failure appeared in Studio: Browse showed the saved PostgreSQL decision while Search returned no results. A newly constructed searcher found it.
2. **Retries can acknowledge incomplete writes.** Injecting a failure between the Chroma write and the SQLite write left a vector record without lexical or trust records. Retrying returned success because the vector ID already existed. The sweeper also wrote a memory without populating lexical or trust data.
3. **Quarantine does not apply consistently.** A memory consolidated before quarantine reappeared through reconstruction. Graph injection returned a fact from a quarantined source outside the requested wing and exceeded the requested result count.
4. **Backup, restore, and deletion are not reliable lifecycle contracts.** The drawer export/import path lost trust and sidecar state; a restored quarantined memory became searchable as current. A truncated JSON array was accepted partially. Git export merging resurrected an ID deleted locally.
5. **The evaluation cannot support the headline performance claims.** One A/B scorer accepted any `NEEDLE_` record as the correct answer. The “moat” evaluation did not execute the named vector and hybrid baselines. LongMemEval NDCG normalized against only the retrieved relevant items.

The [evidence register](EVIDENCE.md) separates these observations from additional design concerns and identifies the affected code. The uncommitted Studio changes already fix one important published behavior: with a configured token, anonymous reads of `/api/config` changed from HTTP 200 to 403. The response still returns the provider key to an authenticated caller; the future service should use secret references and redacted settings responses.

## What the checks establish

| Check | Result |
| --- | --- |
| Published Python default suite | 276 passed, 1 skipped; 56.55% statement coverage |
| Local work-in-progress Python default suite | 280 passed, 1 skipped; 56.55% statement coverage |
| Local Ruff lint and format | Passed |
| Studio frontend production build | Passed |
| Electron TypeScript build | Passed |
| Frontend dependency audit | 13 affected packages: 9 high, 4 moderate |
| Electron dependency audit | 19 affected packages: 1 critical, 14 high, 4 moderate |
| Python installed-environment audit | 35 reported advisory entries across 9 packages; 23 distinct advisory IDs |
| Targeted diagnostic cases | All 15 reproduced the documented behavior |
| Studio browser flow | Save/detail worked; fresh-install search missed the saved memory |

The Python runs followed the repository's default exclusions for benchmark, slow, and stress tests. Passing tests demonstrate a useful regression base, but the missing invariants explain why serious failures coexist with green results. Coverage is not a reliability score.

Dependency counts include transitive and development dependencies; scanner entries can overlap. They are an update and exposure-triage backlog, not a count of independently exploitable production flaws. The current npm audit gates fail against today's advisory data even though the latest observed June CI run passed. A Windows installer was not packaged or launched in this WSL study.

## What to retain, replace, and defer

| Treatment | Components | Reason |
| --- | --- | --- |
| Retain and adapt | Source extraction/chunking, source hashes, evidence links, wiki rendering/diffs | These support portability and inspectable memory |
| Preserve as a required integration | Obsidian Markdown export, stable wikilinks, graph navigation, managed vault paths and manual sections | The user requires Obsidian for visualization; migration must preserve existing vaults |
| Retain as behavior, revise implementation | Trust transitions, core memory, correction workflows, compatibility aliases | Useful concepts need revisions, permissions, concurrency, and uniform enforcement |
| Retain as clients | React Studio, CLI, assistant adapters, selected desktop lifecycle work | Shared clients should use the same service contract |
| Replace | Global singleton service state; independent Chroma/FTS/trust writes; unversioned backup envelope; Git merge as live synchronization | They cannot provide the required shared-memory guarantees |
| Refactor behind domain services | Large MCP and CLI modules, miner/capture entry points, storage access | Prevent each transport from recreating business rules |
| Defer to an experimental package | LeWM grooming, JEPA-named prediction, automatic causal interpretation | Current evidence does not establish a production advantage; predictor inputs are missing on the normal search path |
| Add | Authenticated identity, scoped authorization, durable jobs, versioned API/SDKs, export manifests, deletion receipts, operational console | These are foundational for apps and teams |

The initial service should remain usable without LLM extraction. Accept and retrieve raw evidence first. Offer extraction, reflection, entity resolution, and compiled knowledge as separately observable and budgeted work. This preserves a practical advantage for local and private deployments without making an unsupported “zero cloud calls” promise for every connector and model configuration.

## Alternatives considered

| Option | Benefit | Main cost or limitation | Decision |
| --- | --- | --- | --- |
| Patch v3 in place | Fastest improvement for current local users | Permission, transaction, and lifecycle changes spread through most modules | Use for a stabilization bridge |
| Rebase onto current MemPalace | Access to storage contracts, adapters, daemon work, and MCP improvements | Reconcile substantial divergence; shared-palace features do not establish Mnemion's required user permissions | Review targeted ports; avoid treating a rebase as the whole rebuild |
| New service core, migrate useful features | One consistent contract while preserving domain knowledge | Requires deliberate migration and compatibility work | **Recommended** |
| Build Mnemion on Hindsight or Mem0 | Potentially reduce extraction and retrieval engineering | Must prove permissions, correction/deletion/export semantics, operational cost, and licensing fit | Run a bounded adoption comparison before owning every algorithm |
| Rewrite everything in another language | Maximum implementation freedom | Recreates working assets and does not itself solve the domain problems | No evidence justifies it |

The most valuable comparison prototype is a common workload exercised through Mnemion's proposed contract against PostgreSQL retrieval, Hindsight, and Mem0. It should answer which components to adopt. It should not become an open-ended contest to claim the highest public benchmark number.

## Initial product scope

Prioritize two end-to-end workflows. First, an application records an event, an authorized assistant recalls it with evidence, and another application sees a later correction. Second, a team shares project knowledge while personal and other-team memory remain inaccessible; revoking a credential or deleting evidence takes effect across search, profiles, graphs, and exports.

The first console should make spaces, credentials, ingestion status, evidence, corrections, and recovery visible. It should show whether a source was accepted, indexed, or failed. “Current — 100%” for a newly entered unverified memory and “average confidence 100%” for an empty store communicate certainty that the system has not earned.

Obsidian remains a supported visualization client in the first migration milestone, with Markdown, wikilinks, indexes, and provenance pages that work with its native graph. Additional custom graph features, rich automatic synthesis, dozens of connectors, and peer-to-peer replication can follow measured demand. Existing source/wiki backend features should become visible before adding more hidden subsystems. Clear integration instructions should distinguish configuring MCP access from enabling capture and supplying startup context; a tool's existence does not guarantee every assistant invokes it.

## What success means

Mnemion v4 is ready for a team pilot when successful writes survive worker failure, retrying cannot create inconsistent state, permissions apply to every projection, corrections and deletions propagate predictably, and a tested restore preserves those properties. Retrieval must be evaluated with query-specific ground truth, held-out questions, source citations, time-aware answers, and recorded cost and latency.

The next implementation unit is a stabilization release plus a small v4 vertical slice: authenticated ingest, durable storage, scoped recall with citations, correction, deletion, and a migration of a synthetic v3 fixture with its Obsidian visualization. The [roadmap](ROADMAP.md) makes those outcomes reviewable and orders the remaining work around them.
