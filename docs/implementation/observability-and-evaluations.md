# Observability and evaluation requirements

This is an implementation and acceptance specification, not a claim that the
entire workspace has passed release validation. It incorporates the user's
10 October requirement for a detailed, visual monitoring and evaluation system,
alongside configurable embeddings, a local/cloud librarian and bounded resource
use. All earlier release requirements remain in force.

## Product surface

Studio needs one navigable **Insights & evaluations** workspace. The overview
answers whether memory is current, accessible, searchable and keeping up with
incoming work. Detailed views explain a change and link to actionable records,
operations, sources and evaluations. Support keyboard interaction, responsive
layouts, accessible labels, reduced motion, explicit units, timestamps and an
equivalent data table for every chart. Empty or missing telemetry is not zero.

Required views:

1. **Overview:** freshness, indexing coverage, queue age, failures, query latency,
   incoming/outgoing volume, current model, latest evaluation and actionable
   conditions. Time ranges and scope must apply consistently.
2. **Memory health:** kind, claim/review state, source provenance, age and validity,
   revisions, duplicate candidates, vector/chunk amplification and storage.
   A verified label is a human/source workflow state, not measured truth.
3. **Retrieval:** volume, latency distributions, empty/fallback results, incomplete
   indexing, context budgets, citation checks, lexical/semantic/hybrid comparisons
   and reproducible individual query diagnostics.
4. **Sources and pipeline:** provider status, access expiry, observations,
   checkpoints, ingest throughput, durable backlog, retries, failures and time to
   become searchable. No connector secrets or private query text in metrics.
5. **Models and resources:** generation/dimensions, configured budgets, admitted
   and rejected inference, memory/CPU where measured, model throughput, token and
   byte traffic, and separately identified provider cost estimates or actual
   usage. Do not infer memory bandwidth in GB/s from request throughput.
6. **Evaluations:** immutable versioned test sets, explicit development/held-out
   splits, reproducible runs, progress/cancel/retry, per-case inspection, category
   breakdowns, comparable-run deltas, uncertainty and JSON/CSV exports. Users can
   run a small diagnostic without launching or downloading a large model.
7. **Librarian:** policy, schedule, backlog, runs, supported/unsupported proposals,
   reviews, stale evidence, model/token/cost usage and accepted/rejected outcomes.
   This view depends on the shared librarian implementation.

## Measurement contract

Collect bounded, numeric aggregates with fixed operation/mode labels. Never put
queries, memory text, credentials, full URLs, source paths or arbitrary metadata
in telemetry labels. Use explicit retention and a bounded in-process buffer;
telemetry saturation must not block a canonical write. Distinguish durable
operational state from best-effort telemetry. Expose observation time, retention,
sample counts, dropped samples, aggregation resolution and process restart
boundaries. Histograms produce bucket bounds, not falsely precise percentiles.

Space diagnostics require current reviewer access. Cross-space and process-wide
information must not bypass provider access boundaries or leak another tenant's
content. Recheck access before serving cached statistics. Limit chart points,
table pages, polling, database execution time and concurrent evaluation work.
Pause automatic refresh while hidden and offer manual refresh.

Storage and network figures need a precise unit and basis: logical UTF-8 bytes,
stored vector bytes, process RSS, encoded request bytes and provider tokens are
different measurements. Cost estimates name the supplied price, currency and
date; an unconfigured rate is unavailable rather than free. Resource sampling
must work on macOS, Windows and Linux or report a specific unavailable sensor.

## Evaluation contract

Store test queries and reference IDs in a separate permission-scoped evaluation
schema. Never index test labels or generated answers as source evidence. Pin the
test-set digest, reference revisions, split, model generation, retrieval settings,
context budget, scorer version and corpus state before execution. Mark runs
whose source state changes. Keep original results when changing a model.

Report recall/precision at K, reciprocal rank, NDCG, evidence completeness,
context coverage, citation validity, latency and failures with denominators.
Exclude genuinely unanswerable cases from recall denominators. An empty answer
or zero hits is not evidence of a correct abstention. Answer generation and any
LLM judge are separate, explicitly configured stages with their own model,
budget, prompt and limitations. Human labels remain available. Explain small
samples and uncertainty; do not claim release quality from a deterministic
transaction fixture.

Durable evaluation runs need leases, cancellation, bounded retries, deadlines,
low concurrency and an inter-query rate limit. A revoked key or grant, deleted
reference, changed generation or exhausted budget must not silently continue.
Do not launch substantial local models automatically. Heavy release evaluations
run on a separate adequately sized runner, sequentially by stage.

Required validation includes metric correctness on partial/duplicate evidence,
cross-tenant and revoked-access denial, deletion/purge/restore behavior, lease
loss and cancellation, corpus drift, malformed imports, zero-sample displays,
bounded queue saturation, real retrieval integration, accessible charts and
exports, and a native client/build pass on all supported platforms.
