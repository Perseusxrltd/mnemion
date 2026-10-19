# Insights and evaluations

Open **Insights and evaluations** in Studio with reviewer access to the current
space. Every query is scoped to that identity and space. Process-level resource
details additionally require administrator access.

The six views cover activity, memory health, retrieval, source pipelines, model
resources and evaluations. Select a time window from one hour to thirty days,
filter operation origin, pause polling or refresh explicitly. Charts support
keyboard inspection, legends, tooltips and paged numeric tables. Missing samples
remain gaps; counters do not invent provider prices, hardware bandwidth or scores.
Runtime histories are bounded samples in the current browser session.

From 4.2.5, **Models & resources** also identifies supervised worker ownership
and displays its measured RSS, loaded model count, inference pressure and idle
cleanup. API gauges remain separate. These worker observations require the same
organization administrator access as API runtime diagnostics; they can include
other organizations using that host. Busy or unavailable worker samples remain
unavailable, and monitoring does not load a model or reset its idle timer.

Telemetry stores numerical aggregates, count/error/latency histograms and queue
status. It does not store memory text or query strings. Collection is bounded,
expires old buckets, and drops diagnostics under overload instead of making
memory writes depend on telemetry. Offline and unavailable states remain visible.

## Build an evaluation

1. Create a test set in the evaluation lab or import a JSON file of questions.
   Select reference memories using the picker or newline-separated memory IDs.
2. Mark each question as development or held out. Use intentionally unanswerable
   questions for inspecting unsupported results. JSON also supports relevance
   grades 1–3, explicit revision IDs and temporal filters.
3. Save a version. Its references, content hash and source revisions are pinned;
   labels and questions never enter the searchable memory corpus.
4. Start a run with lexical, semantic or hybrid retrieval, up to five K cutoffs,
   an optional context-token budget, a duration limit and an inter-query delay.
5. Inspect per-case evidence and aggregate scores, add a human assessment, compare
   compatible runs, and export JSON or CSV for independent analysis.

There is one leased evaluation runner across the deployment. A run uses the
service's configured model and does not launch a new local model or cloud judge.
Cancellation, credential revocation, source deletion and time limits stop or
invalidate affected work. Human assessments use optimistic concurrency so two
reviewers do not silently overwrite one another.

From server 4.14.0, **Ranking preferences** also records `sort` and the recent
match threshold (`ranking_policy.recent_relevance_ratio`). Compare relevance,
recent relevant passages and strict dates on the same test-set version. A
threshold of 0 restores strict chronological ordering; 70% is the normal
comparison threshold. The run keeps its settings, retrieval implementation
and actual execution version. Older queued runs keep relevance order. Source
date labels and matching terms do not establish that a claim is true.
From 4.24, recent comparison retains available question support and applies
archive preferences among comparable matches. A queued run that starts after an
upgrade records the implementation actually executed and preserves its queued
identifier. Already running evaluations still refuse to mix service versions.

From server 4.3.3, **Ranking preferences** records `keyword_fallback` and the
complete `ranking_policy` with each run. Compare question-term support on/off,
or use 0% recency influence and 100% archive weight to measure relevance without
age/archive adjustments. The same options are available to agents through the
evaluation API and SDKs. Dataset, split, corpus, index coverage, modes, cutoffs
and context budget must still satisfy the comparison checks; ranking preferences
and model generations may deliberately differ.

From service 4.8.1, **Results per imported document** also records
`max_per_source` with the run. One groups imported document parts, a higher
number permits several, and zero retains individual-part results. The per-case
export includes the applied setting and skipped-candidate count. A test set
that labels several parts of one document can legitimately have lower reference
coverage when grouping is enabled; compare the settings deliberately.
Saved configurations without this field retain individual-part retrieval.

The same version corrects citation verification for bounded excerpts of long
sources. A valid excerpt need not cover the full saved citation. It must stay
inside that citation, reproduce the source text exactly and pass the original
memory/source hash checks. These checks establish evidence integrity, not the
truth of an answer.

New manifests record the queuing service version and the worker version that
starts execution. Per-case results record the service version and ranking
reference time. If a new run resumes on another version after a hotfix, it stops
with `evaluation_error`; start a new run rather than mixing implementations.
Older saved runs have no guaranteed runtime pin. Runs queued before the
question-term option existed retain disabled term support when resumed.
Current-state queries still use their actual request time; use explicit temporal
filters, or disable recency, for comparisons requiring a fixed age reference.

Older servers retain their existing run form and behavior. Updated SDKs omit the
new options unless the caller supplies them, preserving older-server contracts.

## Interpret results

Recall measures coverage of labeled references; precision uses the configured
cutoff; nDCG uses relevance grades and rank; MRR measures the first relevant hit.
Context coverage and citation validity assess the returned evidence. Unanswerable
questions are excluded from reference-recall denominators. Confidence intervals
and sample counts are shown; a perfect small fixture is not proof of production
accuracy. The manifest records the model generation, configuration, scorer,
dataset hash and corpus/index changes.

Human assessments are separate from retrieval scores. The lab does not claim
answer-generation accuracy or automatically charge a cloud model. Comparable runs
must share the required frozen inputs; incompatible comparisons explain the
differences. Keep held-out questions separate from tuning.

History uses cursor pages of 50 in Studio; API datasets allow 200 and runs 100 per
page. Active polling uses compact manifests, and per-case results are fetched in
pages. JSON/CSV exports deliberately include full evidence for the authorized
reviewer and should be treated as private. Removing a reference invalidates and
redacts dependent evaluation material according to current deletion policy.
