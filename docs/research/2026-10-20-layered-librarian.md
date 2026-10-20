# A layered, continuously maintained memory system

Research and implementation contract, **20 October 2026**. This records the
expanded librarian requirement; it does not describe a released autonomous
brain. The current [librarian](../service/librarian.md) supports bounded,
evidence-linked proposals, review, schedules and undo. Continuous consolidation,
cross-layer maintenance and the decision router below remain implementation work.

The goal is to preserve the useful structure of human memory—rapid experience
capture, slower consolidation, association and retrieval practice—while adding
inspectable sources, explicit permissions, reproducible decisions and recovery.
No biological analogy establishes unlimited capacity or perfect recall.

## Capture first, without making capture depend on a model

Each approved source feeds a durable raw inbox before optional interpretation.
Capture should continue while the librarian is stopped, offline, out of model
quota or catching up. The acknowledgment boundary is durable storage; semantic
indexing and librarian completion have separate checkpoints.

Capture settings belong to each source and organization, with a simple user
preset and equivalent agent controls:

- **Selected:** chosen notes, messages or sessions.
- **Conversation:** available user/assistant messages and their provenance.
- **Detailed:** conversation plus approved tool calls/results and the reasoning
  summaries or traces that the provider actually exposes.
- **Paused:** preserve the checkpoint and show the last successful capture.

There is no promise to obtain a provider's hidden internal reasoning. Optional
reasoning traces are unverified process records, not factual evidence. The app
must show unavailable content types instead of inventing complete coverage.
Sensitive fields, attachments, maximum sizes, exclusions and retention are
reviewable before enrollment. Existing security pauses remain effective.

Events need stable source/session/turn IDs, actor, source and observed times,
content hash, media type, source revision, permission snapshot and an idempotency
key. Checkpoint gaps, truncated streams and source deletions stay visible.
Duplicate delivery may be coalesced while retaining its provenance. A full
queue applies bounded backpressure and records the gap; it never silently
discards accepted events or grows RAM without a limit.

## Layers and ownership

| Layer | Contents | Maintenance and retrieval |
| --- | --- | --- |
| Raw inbox | Original permitted events, attachments and provenance | Append and checkpoint quickly; repair gaps; enforce retention and deletion. |
| Episodes | Sessions, tasks, decisions and chronological event groups | Segment and summarize with links to exact raw revisions; distinguish observations, proposals and outcomes. |
| Knowledge | Versioned claims, entities, concepts and relationships | Consolidate compatible evidence, preserve contradictions and time ranges, link related subjects. |
| Procedures | Reusable workflows, constraints and lessons | Require observed outcomes, task scope and regression evidence; record what failed as well as what worked. |
| Working memory | Bounded, task-specific context and frequently useful items | Assemble for the requesting identity, budget and current task; expire or refresh derived views. |

These are logical views over portable records, not five mandatory databases.
PostgreSQL, the existing revision/claim model, source adapters, graph and
Obsidian-readable exports remain the foundation. Embeddings and summaries are
rebuildable derivatives. A summary never becomes the only copy merely because a
model calls it sufficient. Authorized deletion still removes raw data and its
derivatives according to policy; audit receipts retain no deleted content.

“Rooms and drawers” map to projects, topics, entities and collections. A room's
display organization must not silently change a space's access boundary. The
encrypted credentials vault remains separate: detected secrets are quarantined
or redacted from search, and a librarian may propose an approved vault action.
It cannot grant access, export secrets or declassify information by itself.

## Two maintenance loops

The **arrival loop** performs cheap validation, redaction, exact deduplication,
event grouping and candidate routing. It can use deterministic rules, a small
local classifier or an explicitly approved decision provider. Uncertain material
remains in the inbox for later review rather than being discarded.

The **consolidation loop** revisits both new and old records. It selects bounded
neighborhoods, compares claims against newer evidence, proposes links and
corrections, refreshes derived summaries and checks whether procedures still
work. Periodic coverage sweeps ensure that rarely retrieved rooms are eventually
reviewed. Multiple librarians can specialize by space or task, but leases,
version checks and fair scheduling prevent conflicting writes and starvation.

Every proposed change carries source revision IDs, exact evidence, action type,
model/deployment and prompt-policy fingerprints, usage, decision reason and
expected revision. Applying it rechecks current permissions and source versions.
An interrupted job resumes from acknowledged work; it does not replay an
uncertain mutation. A changed source invalidates affected derivations.

Autonomy is configurable by action and space: observe, suggest, automatically
apply reversible organization, and apply retention rules explicitly authorized
by an administrator. Policy controls the maximum authority. Model confidence
never authorizes permanent deletion, permission changes or external disclosure.
Soft archival, rollback and protected retention periods precede destructive
cleanup wherever the policy permits them.

## Statistical resurfacing without reinforcing mistakes

Track qualified retrievals, explicit usefulness feedback, task reuse, source
freshness, unresolved contradictions, dependencies and review age. A retrieval
is an exposure, not proof of usefulness. Repeated model-generated copies do not
count as independent corroboration; repeated errors do not become truths.

Start with an interpretable priority policy, versioned per workspace. Combine
task relevance, measured reuse, independent source support, deadline proximity
and change impact; subtract staleness, redundancy and uncertainty. Keep the
arithmetic in code and expose each contribution. Reserve part of the maintenance
budget for coverage and exploration so unpopular information is not forgotten
solely because it was never surfaced.

An optional learned router must beat this baseline on held-out data. Selection
bias, feedback loops and confidence calibration are evaluation subjects, not
problems solved by collecting more counters. Avoid expensive all-pairs scans:
use permission-filtered lexical/vector candidates, entity neighborhoods,
temporal windows and checkpointed sweeps.

## Scientific evidence and its limits

| Source | What it supports investigating | What it does not establish |
| --- | --- | --- |
| [MemGPT](https://arxiv.org/abs/2310.08560), 2023 | Explicit movement between working context and external memory; separate storage from a model's context window. | Unlimited reliable memory or automatic team authorization. |
| [Generative Agents](https://arxiv.org/abs/2304.03442), 2023 | An observation stream, higher-level reflections and retrieval using relevance, importance and recency. | Factual correctness or enterprise reliability; its main setting is a social simulation. |
| [MemoryBank](https://arxiv.org/abs/2305.10250), 2023/2024 | Selective reinforcement and time-sensitive memory updates. | A reason to erase infrequently used legal, security or project evidence. |
| [A-MEM](https://arxiv.org/abs/2502.12110), 2025 | Linked notes and contextual memory evolution as new material arrives; compare with the existing knowledge graph. | Correct links under every domain, permission-safe cross-space consolidation, or calibrated verification. |
| [Sleep-time Compute](https://arxiv.org/abs/2504.13171), 2025 | Precompute useful context during idle time, particularly when future questions are predictable. | Free computation or the same gains for unpredictable queries; the paper explicitly discusses this limitation. |
| [LongMemEval](https://arxiv.org/abs/2410.10813), 2024/2025 | Evaluate extraction, multi-session reasoning, time, updated knowledge and abstention separately. | Sufficient coverage of organizations, permissions, ingestion outages or malicious memories. |
| [LoCoMo](https://arxiv.org/abs/2402.17753), 2024 | Long multi-session conversation, event summarization and temporal/causal questions. | Complete real-provider capture or a substitute for private, consented deployment acceptance. |
| [Titans](https://arxiv.org/abs/2501.00663), 2025 | Distinguish neural long-term memory architectures from external record stores. | A drop-in database or a model-independent plugin that can transparently modify closed models. |
| [Memory in the Age of AI Agents](https://arxiv.org/abs/2512.13564), 2025/2026 | Organize the field by memory forms, functions and dynamics; inspect multi-agent and trustworthiness research. | An independently validated universal architecture; it is a broad research survey. |
| [MemRL](https://arxiv.org/abs/2601.03192), 2026 | Candidate work on learning utility from episodic outcomes; evaluate only after stable feedback baselines. | Permission to learn directly from production mistakes or bypass review and rollback. |
| [Unveiling Privacy Risks in LLM Agent Memory](https://arxiv.org/abs/2502.13172), 2025 | Include memory disclosure and privacy attacks in evaluation. | That a successful accuracy benchmark demonstrates safe storage or retrieval. |

Full-text sections of A-MEM, Sleep-time Compute, LongMemEval and the survey
were retrieved for this review; the remaining entries were checked against their
official abstracts and metadata. Paper results are their authors' results, not
Mnemion measurements. The bibliography is selective, not an exhaustive claim
about the newest or best systems.

## TypeSafe AI Jev: a candidate decision stage

**Jev is relevant to routing and bounded judgments. It cannot replace the
entire librarian.** Its [official API](https://docs.typesafe.ai/introduction)
evaluates typed questions against supplied state. Choice, Score and Noul can
classify an event, prioritize a bounded candidate set or indicate whether
further verification is needed. A separate generative model is still needed
for synthesis, explanations and tasks requiring deeper reasoning.

TypeSafe's [memory cookbook](https://docs.typesafe.ai/cookbooks/basic_memory)
demonstrates a simple per-customer dictionary and an importance gate. That is
a useful integration example, not a durable, permission-aware memory system.
Mnemion would retain storage, evidence, policy, queues, actions and recovery.

The [model documentation](https://docs.typesafe.ai/models), checked on 20 October,
lists `jev-1.14.0` and `jev-1.13.0`; `jev-preview` points to 1.14 while
`jev-latest` still points to 1.13. Pin the tested version. The listed standard
limits are 64k tokens per request and 32k per question. Experimental image and
long-context flags are inappropriate defaults for this pipeline.

Potential trials, after authorization for a provider, are:

1. Classify incoming material into an **already authorized** project/topic set.
2. Score novelty, evidence completeness and the need for deep review.
3. Rerank a bounded set of permitted passages and candidate entity matches.
4. Route difficult, contradictory or uncertain cases to the deeper model.

The service returns typed values; correct types do not guarantee true claims.
Its [confidence documentation](https://docs.typesafe.ai/confidence) distinguishes
probability from distribution-based confidence. Validate both on Mnemion's
labels; do not interpret confidence as a universal error probability. The
[published 1.13 limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13)
include numeric precision, dates, indirection and long state. Exact arithmetic,
time comparisons, authorization and deletion eligibility stay deterministic.

**Cost and privacy decision:** TypeSafe currently lists **$0.042 per million
input tokens**, with output tokens free. It is a hosted paid API; the reviewed
documentation does not establish free self-hostable weights. No account,
subscription, trial or API call was created for this study. Under the project's
no-spending requirement, Jev remains an optional, disabled research candidate.
A future user-supplied provider cannot become necessary for the free product.
The local rules/small-model route must work without it. TypeSafe says customer
requests are not used for training; zero data retention is separately described
for enterprise customers. That is not blanket approval to send company raw
memory. Existing per-space cloud-processing approval and data policies apply.

## Measurements required before autonomous rollout

Use the same event corpus, permission graph, model revision and resource budget
for rules-only, current librarian, layered librarian and optional Jev routing.
Record real latency, peak RSS, CPU, bytes, tokens, retries and actual provider
cost separately. Publish results with corpus provenance and known gaps.

- **Capture:** accepted/durable/indexed/consolidated watermarks; gap and duplicate
  rates; queue age and backlog; recovery after offline operation.
- **Memory quality:** retrieval precision/recall, grounded answers, temporal
  corrections, contradiction handling, abstention and summary citation coverage.
- **Maintenance:** useful promotion rate, reviewer rejection, rollback rate,
  harmful archival/deletion, sweep coverage and changed-source invalidation.
- **Decisions:** confusion matrices, Brier score/calibration curves, uncertainty
  routing and accuracy/latency/cost tradeoffs, broken out by language and domain.
- **Isolation:** revocation during a run, cross-tenant/space leakage, poisoning,
  untrusted transcript instructions, secret handling and deletion propagation.

The app and online graph should show each layer, backlog, review coverage,
provenance, why a memory resurfaced, unresolved findings and model expenditure.
Offer an understandable overview plus advanced graphs and exportable run data.
Every configuration and inspection operation must also be available to agents.

## Delivery sequence and research watch

| Slice | Deliverable | Completion evidence |
| --- | --- | --- |
| L1 | Raw inbox, source-level capture presets and durable checkpoints | Restart/offline/gap tests with real adapters; visible coverage and no silent loss. |
| L2 | Episodic/claim derivatives with evidence and invalidation | Incremental updates, corrections and deletion retain source linkage and isolation. |
| L3 | Fair background consolidation and coverage sweeps | Bounded CPU/RAM/queue behavior while retrieval and capture remain available. |
| L4 | Statistical resurfacing and deep review | Held-out quality, calibration, temporal and conflict measurements beat the baseline. |
| L5 | Policy-bounded autonomy, archival and recovery | Revocation, concurrent edits, undo and retention/deletion tests pass. |
| L6 | Layer-aware map, advanced insights and complete agent controls | Matching app/API/CLI acceptance across supported platforms. |
| L7 | Optional typed router, including Jev if justified | Independently measured benefit, pinned version, explicit processing/cost approval and working free fallback. |

Source **4.39** adds a [scheduled, free metadata watch](RESEARCH_WATCH.md) for
relevant scientific papers and official model/tool changes. It runs weekly on
main and can be requested manually; the [maintenance guide](../MAINTENANCE.md#scientific-paper-and-tool-watch)
documents its commands, source limits and failure behavior. Bundled app help
includes the catalog from that app release. New entries are **candidates for review**, never
automatic dependency upgrades or authority to run external instructions.
Deduplicate IDs, preserve source/date, record fetch failures, and compare
promising candidates against the existing evaluation corpus. Review licensing,
data handling, real hardware needs, migration and rollback before adoption.
The initial run retrieved seven of eight sources; arXiv returned HTTP 429 while
the direct paper sources above were available. A failed feed preserves the
previous successful catalog and its date. This automation supplies review
candidates; it does not complete the layered librarian stages or adopt a model.

This work is tracked as R07 in the [complete requirements](../PRODUCT_REQUIREMENTS.md).
Operational GitHub bugs and the current connector release continue in parallel
with this longer implementation sequence.
