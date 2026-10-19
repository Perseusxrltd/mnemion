# Search ranking, passages and source evidence

## Exact identifiers and filenames

Service 4.2.2 adds a literal candidate channel for task IDs, quote numbers and
filenames in lexical and hybrid searches. An exact filename can enter the
results even when the memory body does not contain every word of the query,
or the semantic candidate window would omit it. Explicit semantic-only
searches retain their existing behavior. This is a source-version description;
check [release status](../RELEASE_STATUS.md) for publication.

Matches are case insensitive and literal, with identifier boundaries:
`TASK-7312` can match `reports/TASK-7312_result.md`, but not `TASK-73120`.
Filename matching accepts Windows or Unix path separators and NFC or NFD
Unicode. Repetition within a memory does not add identifier coverage.
The query parser recognizes at most eight distinct identifiers or filenames,
each at most 256 characters. Excess identifiers produce the explicit
`identifier_query_truncated` warning. Plain prose, standalone numbers and
queries containing explicit exclusions such as `-billing` continue through
the existing lexical and semantic channels. The new positive-ID channel cannot
reintroduce a result excluded by lexical query syntax.

Candidates are selected from the currently authorized spaces and eligible
revisions before ranking. Source removal, quarantine, withdrawal, time and
metadata filters apply to the literal channel. A single additional SQL query
selects two bounded windows: identifier coverage and subject/path matches.
Each window has the existing candidate cap of `min(250, max(30, limit * 5))`.
There is no additional embedding or language-model call.

Reciprocal-rank fusion retains `k = 60`. A subject or path match has weight 3;
literal coverage, lexical rank and semantic rank each have weight 1.
The relevance score divides the sum by the maximum available channel weight
at rank 1. It is a ranking score, not an answer probability. Existing
`ranking.ranks.lexical`, `ranking.ranks.semantic` and `score_method` remain
compatible. Optional `ranking.identifier` reports the literal rank, label
rank, matched and requested counts, label matches and weights. The app shows
the matched counts under **Why this result?**

In 4.14.0, a plain hybrid question containing an ID also uses its surrounding
key terms. Among equally complete identifier matches, those terms break ties;
`ranking.identifier.context_matches` reports the count when present. Pure
identifier requests, explicit search syntax and a disabled keyword fallback
retain their original identifier ordering.

The query still examines the eligible corpus; the candidate cap bounds returned
rows, not database scan work. Large-corpus capacity and natural-language quality
remain separate evaluation work. Version 4.2.3 adds the controls below.

## Natural-language question support

From service 4.3.3, hybrid search defaults to `keyword_fallback: true`.
When a plain question has no complete lexical match,
individual key terms can add candidates alongside semantic search. For example,
“Where will we keep the Atlas backup copy?” can give an Atlas document useful
text support even though the document does not repeat the complete question.
From 4.14.0 this also applies to questions containing identifiers; earlier
versions skipped this support when an identifier was recognized.

The fallback accepts 3–32 query words and 2–24 distinct non-stopword lexemes.
PostgreSQL's bundled English and French dictionaries remove common words; the
remaining terms retain their original lexical form. This is not automatic
translation or a general language-understanding model. Quotes, exclusions,
explicit `OR`, short queries, explicit lexical/semantic
modes and inference-busy exact-text fallback keep their existing behavior.

Each matching term counts once per eligible memory. Rarer terms and subject
matches receive more weight, with a small length adjustment. Document-frequency
statistics use only the authorized, filtered inventory. The returned candidate
window remains `min(250, max(30, limit * 5))`; database work still scales with
the eligible inventory. No model download, extra embedding call or re-index is
required. Representative large-workspace capacity remains evaluation work.

From 4.14.0, key-term candidates use rank-fusion weight
`0.5 × matched_terms / requested_terms`, replacing the absent full lexical
channel or supplementing exact identifiers. Merely sharing an ID no longer
gets nearly the same question support as matching its specific decision.
`ranking.keywords` exposes the matched terms, matched/requested
counts, rank and weight. `partial_keyword_support` explicitly marks the fallback;
the app explains it under **Why this result?**. It does not establish a full
query match. The existing `semantic_only` match status and evidence-review
warning remain when no full lexical or identifier hit exists. Similarity floors
still apply to partial-term candidates, including those with no semantic rank.

Disable it with `keyword_fallback: false` in recall/context, Python or TypeScript
clients, full MCP search/context tools, or **Search order and match filters**.
Older workspace servers receive no new field from the app; the Python SDK sends
the option only when explicitly supplied. [Evaluations](insights.md) can compare
the option and age/archive preferences on the same private test set.
The [60-question regression](../validation/2026-10-14-question-retrieval.md)
records the measured improvement and its limits; broader question quality and
live shared-workspace acceptance remain open.

For relevance ordering, available question support also supplies a bounded
`ranking.adjustment.keyword_factor`: `0.5 + 0.5 × matched_terms / best_matched_terms`
within the keyword candidate window. The strongest coverage keeps its original
ordering score; weaker coverage can reduce it by at most half. This adjustment
does not alter `relevance_score` or `min_score`. Turning keyword fallback off
also turns off this adjustment. It is not applied to full lexical matches or
explicit lexical/semantic modes.

## Order and match controls

From service 4.2.3, recall and context requests, SDKs and the full MCP
`memory_search`/`memory_context` tools accept:

| Input | Behavior |
| --- | --- |
| `sort: "relevance"` | Rank fusion with bounded source-age, archive and available question-coverage preferences; the default. |
| `sort: "recent"` | Prioritize comparable passage query support, then order by passage chronology. From 4.24, apply archive preferences within that group and retain available question support when rank fusion supplies the comparison. Weaker candidates follow. Earlier than 4.14, servers use whole-record dates. |
| `recorded_after` | Inclusive timezone-aware timestamp filter on when the revision was recorded in Mnemion. Applied before candidate selection; distinct from the source date. |
| `min_score` | Minimum normalized rank-fusion score, 0–1; default 0. It is a rank score, not answer confidence. |
| `min_similarity` | Optional cosine floor, −1–1, for candidates without a full lexical or identifier match, including partial key-term candidates. Exact text or identifier matches remain eligible; `min_score` still applies to them. |

The app exposes these in **Search order and match filters**, including for context
packs. On an older server the new controls are disabled and their fields are not
sent. Simple `search` aliases stay small; agents can discover `retrieval.search`
through the administration catalog for the full HTTP contract.

Recall returns `match_status`: `empty` means no eligible hit passed the requested
filters; `semantic_only` means the returned hits have no literal-channel match;
`matched` means at least one returned hit has a lexical or identifier match.
Semantic-only responses retain the evidence-review warning. None of these states
asserts that an answer is true or that every returned hit answers the question.
`filtered_candidates` counts threshold rejections examined before filling the
requested result limit, not the number of rejected memories in the whole corpus.

Recency remains bounded by the candidate windows. With `sort: "recent"`, the lexical
window prioritizes date before its limit; semantic and identifier windows retain
their own candidate selection before the final recency sort. A recent unrelated document is not added
solely because it is recent. Source dates are provider-supplied metadata, not an
independent authenticity guarantee. Use workspace evaluations to choose score
floors; different embedding models do not share a universally calibrated cutoff.

The app's **Match threshold for recent results** defaults to 70%. It is
`ranking_policy.recent_relevance_ratio` in the API. A candidate with at least
70% of the best passage word coverage joins the priority group; when word
coverage is unavailable, the same comparison uses rank fusion with any available
question-coverage factor. Explicit semantic mode uses rank fusion without keyword
support. Set it to 0 for strict date ordering within the candidate windows.
Weaker results remain available and produce `recent_weak_matches_demoted`.
This is separate from exclusion filters and from the keyword-fallback option.

From **4.24**, comparable recent matches also honor `archive_weight`. An archived
match whose weighted support falls below the comparison threshold follows the
other comparable matches. Each group retains its actual passage dates; no date
is rewritten. This produces `recent_archived_matches_demoted` and per-hit
`ranking.archive` with the factor, matched folder and `demoted` flag. Strong
archived evidence still precedes weak unrelated matches. If all comparable
matches are archived, their common factor cancels and dates determine the order.
Use `archive_weight: 1`, an empty archive-folder list or a recent ratio of zero
to disable this preference. `ranking.recency.comparison_basis` and
`comparison_support` explain whether the comparison used passage coverage,
plain fusion or fusion with question support.

## Passage chronology

Version 4.14.0 adds an internal chronology field to memory revisions. On a new
revision, unchanged lines and numbered decisions retain their earlier date,
including whitespace-only edits. Editing another line in a file therefore
does not refresh an unchanged status. A changed statement beneath an existing
date heading receives its observed update time. Repeated identical text keeps
its earliest retained date; this is text-change evidence, not proof that its
context or claim remains valid.

The first observation can use a leading ISO date in a Markdown heading or
table row. A timestamp with an explicit UTC offset retains its precise time.
A date or time without an offset is ordered at calendar-day precision and
displayed as **date only**; no timezone is invented. Inline deadlines, invalid
dates, future labels and date-like text in fenced code are not interpreted as
new date headings. When no applicable date is available, chronology uses
the source's valid reported modification time or the revision's recorded time.

Recall reports `ranking.recency`: the date, its basis (`source_timestamp`,
`source_date`, `source_modified_at` or `recorded_at`), exact Unicode span,
literal query-term coverage, whether chronology was retained, and whether the
result joined the recent priority group. **Why this result?** explains those
values. Normal memory and source citations remain verbatim. A recent date
does not verify a claim, infer that “closed” supersedes “open”, or override
permissions and claim status.

Existing revisions receive an empty field in migration **021**. Search can
read their explicit dated sections immediately, without re-ingestion or
re-embedding. Their next actual revision can retain unchanged passage dates.
This does not reconstruct historical Git blame or missing pre-upgrade edit
history. Ambiguous dates, undated historical corrections, copied/reordered
content across separate imported parts and authoritative contradiction
resolution remain limitations to evaluate with the team's real evidence.

Processing is bounded to 2,048 units per revision and 250 strongest candidates
per search, using one additional authorized content query and no model call.
An excessive number of units falls back to whole-record chronology with
`passage_chronology_limited`; a larger candidate union reports
`passage_ranking_window_limited`. Other candidates remain available. Candidate
selection still uses record dates before this final passage comparison, so
this is not a complete chronological scan of arbitrarily large workspaces.
The field follows revision RLS, encrypted backup and deletion rules; it is
neither a searchable credential store nor a second plaintext source copy.

[Evaluations](insights.md) can now record `sort: "recent"` and the comparison
threshold, then compare them with relevance or strict-date runs on the same
private test set. Old queued runs retain relevance order. The run manifest
records the updated retrieval implementation and actual execution version.

Git connectors now record the last file-changing commit's strict ISO timestamp
as `source_modified_at`. Their source revision format changes once to backfill
this metadata on the next scan, which can temporarily queue re-indexing. Unchanged
files remain stable across subsequent commits, merges and rollback scans. Date
sorting does not itself resolve contradictions or split appended logs by section.

## Results from distinct documents

Service 4.8.1 defaults to `max_per_source: 1` for search and context. Large Git,
Drive and other imported documents can span several stored memories; the
default keeps repeated parts of one file from occupying the result list.
Choose **Results per imported document** in the app, or pass `max_per_source`
through HTTP, either SDK, the full MCP search/context tools or the agent catalog.
Values are integers from 0 to 50: `0` restores individual-part ranking and lets
all matching parts compete for the requested result limit.

Grouping recognizes the standard `Document.items()` metadata (`extractor:
"mnemion-text-v1"`, a nonempty source identity and an integer part number). Its
identity includes the current space and the memory's original author. Different
spaces, original authors or source identities remain separate; a matching title,
URL, path or body alone never merges memories. Custom adapters without this
format retain individual results. Grouping changes returned results only; it
does not delete, combine or rewrite stored memories or source evidence.

Within each lexical, semantic, identifier and key-term channel, the best part of
each document gets a place before second parts fill the existing candidate
window. Fusion and date ordering then select up to the requested per-document
limit. Match thresholds apply before a returned part consumes its document's
slot. Disabling grouping restores the individual-part candidate order as well.
Rank-fusion scores can change with the candidate order; compare settings on the
same [evaluation test set](insights.md), especially when it labels several parts
of one document.

Recall and context echo `source_grouping.max_per_source` and
`grouped_candidates`. The latter counts extra parts skipped in the examined
candidate window, not all matching parts in the entire workspace. Source dates,
validity, quarantine, current permissions and citation checks retain their
existing behavior. There is no added model call or re-index. The extra candidate
ordering still operates over the eligible corpus; a bounded response does not
promise constant database cost as the corpus grows.

For example, current-state review can explicitly combine matching-source date
order and distinct documents:

```json
{"query":"TASK-7312 current status","all_accessible":true,"sort":"recent","max_per_source":1,"limit":5}
```

An updated SDK omits the new field unless requested, and the app withholds it
from older servers. A newer server uses its default when the option is absent.
Grouping does not establish which document is authoritative or which conflicting
claim is true.

## Current-state ranking preferences

Service 4.3.1 adds a bounded source-age preference to the default relevance order
and lowers the priority of matches in directories named `archive` or `archives`.
This addresses current answers being buried under similarly relevant older
reports or archived task files with a strong filename match. Archive matches
remain available; `done` is not treated as an archive directory.

The API, Python/TypeScript clients, `memory_search`, `memory_context` and the app's
**Search order and match filters** accept a `ranking_policy` object:

| Field | Default | Meaning |
| --- | --- | --- |
| `recency_weight` | `0.25` | Maximum fractional age reduction, 0–1. Zero disables it. |
| `recent_relevance_ratio` | `0.7` | Comparable support threshold for recent ordering, 0–1; zero restores strict dates. Requires 4.14.0. |
| `half_life_days` | `3` | At this age, half of the maximum reduction applies. Range: 1 hour–36,500 days. |
| `archive_weight` | `0.35` | Multiplier for archived candidates, 0–1. One disables the reduction. In relevance order, zero explicitly puts them last; a nonzero value preserves sole literal historical evidence. In recent order, it applies within comparable matches. |
| `archive_path_segments` | `["archive", "archives"]` | Up to 16 literal directory names of 1–128 characters each. An empty list disables matching. |

Directory matching uses `metadata.path`, accepts Windows/Unix separators and
normalizes case and Unicode. It matches complete directory names, never a
substring, file name or memory body. No user regex or filesystem access is involved.

For example, a current-state query can use the defaults:

```json
{"query":"TASK-7312 current status","all_accessible":true,"limit":5}
```

For historical research or an exact baseline, request pure relevance explicitly:

```json
{"query":"TASK-7312","all_accessible":true,"keyword_fallback":false,"ranking_policy":{"recency_weight":0,"archive_weight":1}}
```

The ordering score is `relevance_score × age_factor × archive_factor × keyword_factor`, where
`age_factor = 1 - recency_weight × (1 - 2^(-age_days / half_life_days))`.
Defaults therefore reduce a match by at most 25% due to age. Age can reorder
comparably relevant hits within that bounded share of the existing score.
The ranking date uses passage chronology described above. Unsupported or future
source dates fall back to the selected revision's recorded time. The optional
question factor is 1 when no partial-term channel applies.
The reference is `known_at`, otherwise `valid_at`, otherwise the request's start
time, so historical queries do not acquire an age penalty based on today's date.

Each relevance hit exposes `ranking.adjustment`: ordering score, ranking date,
age, both factors and the matched archive directory. The response echoes the
policy and `ranking_reference_time`; the app displays the factors under
**Why this result?**. `relevance_score`, `score_method: normalized_rrf_k60` and
`min_score` remain unadjusted. Compare thresholds using the recorded model,
retrieval version and settings; a new keyword implementation can change scores.
Result relevance scores can consequently be out of descending order.
From 4.24, a nonzero archive preference does not penalize the only literal
historical evidence when no non-archived candidate has a full text or identifier
match. The hit reports `archive_uncontested: true`, the configured factor and an
effective archive factor of 1. This prevents generic semantic neighbors from
displacing the only exact record. An explicit zero still suppresses it in
relevance ordering. A literal match remains evidence to review, not proof of truth.

`sort: "recent"` bypasses age decay. Its comparable-support threshold retains
question support, and its separate archive comparison behaves as described above.

Access, source leases, quarantine, validity and query filters still run before
ranking. These preferences add no model call, re-index or candidate-window
expansion. Old servers receive no new field unless a caller requests it; the app
enables the controls only for a compatible workspace server. Source dates and
archive paths remain source-supplied hints, not proof of supersession or truth.
The [repeatable local-model regression probe](../validation/2026-10-19-retrieval-archives.md)
records synthetic multilingual, mixed-row and archive cases before and after
indexing, with explicit target labels. Read cited evidence for current-state decisions. Historical Git span dating,
contradiction resolution and broader held-out quality evaluations remain in the
[roadmap](../PRODUCT_REQUIREMENTS.md).

## Passages and citations

Search returns bounded passages so people and agents can inspect a result
without downloading every full memory. The matched-passage correction for
[issue 35](https://github.com/Perseusxrltd/mnemion/issues/35) requires service 4.2.0.
Check [release status](../RELEASE_STATUS.md) for the published server version.

`POST /v1/recall` and MCP `memory_search` use the same retrieval service. Each
hit has two independently meaningful spans:

- `text` and `memory_span` identify a passage in the memory revision.
- `evidence.excerpt`, `evidence.start` and `evidence.end` identify a passage in
  the cited source revision. A summary and its original source can differ.

Offsets count Unicode code points from zero; the start is inclusive and the
end exclusive. A source slice between those offsets reproduces the excerpt
exactly. The source revision identifier and hash continue to identify the
complete original source. Do not interpret a source offset as a byte offset or
JavaScript UTF-16 index.

The correction selects up to 4,000 characters around the strongest local
coverage of query words. Repeated words have bounded weight. When no query word
matches, an available embedding span supplies the memory passage. When an
embedding chunk is shorter than 4,000 characters, its size also bounds the
memory passage so context consumption does not expand. A derived memory's
source is searched separately, within its original cited range; memory
offsets are never copied into a different source. The selector scans text without
loading another model and retains only one display window of matches.

`text_truncated` and `evidence.excerpt_truncated` indicate that a result shows
only part of its memory or cited source. Fetching the memory still returns the
complete revision and original evidence. Context packs preserve the selected
memory passage and source citation after checking access and revision freshness
again. Obsidian export continues to use complete recorded evidence.

A well-positioned excerpt does not establish that the result answers a question
or is current. This correction does not change document ranking, introduce a
relevance threshold, resolve contradictions or supply a recency signal. Those
retrieval requirements remain in the [roadmap](../PRODUCT_REQUIREMENTS.md).

For scope, supply nonempty `space_ids`, or use `all_accessible: true` with an
empty list. Both resolve current permissions. Source removal, quarantine,
withdrawal and authorization checks also apply to passages.
