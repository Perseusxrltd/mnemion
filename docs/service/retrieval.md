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

The query still examines the eligible corpus; the candidate cap bounds returned
rows, not database scan work. Large-corpus capacity and natural-language quality
remain separate evaluation work. Version 4.2.3 adds the controls below.

## Natural-language question support

From service 4.3.3, hybrid search defaults to `keyword_fallback: true`.
When a plain question has no complete lexical match and no identifier channel,
individual key terms can add candidates alongside semantic search. For example,
“Where will we keep the Atlas backup copy?” can give an Atlas document useful
text support even though the document does not repeat the complete question.

The fallback accepts 3–32 query words and 2–24 distinct non-stopword lexemes.
PostgreSQL's bundled English and French dictionaries remove common words; the
remaining terms retain their original lexical form. This is not automatic
translation or a general language-understanding model. Quotes, exclusions,
explicit `OR`, identifier queries, short queries, explicit lexical/semantic
modes and inference-busy exact-text fallback keep their existing behavior.

Each matching term counts once per eligible memory. Rarer terms and subject
matches receive more weight, with a small length adjustment. Document-frequency
statistics use only the authorized, filtered inventory. The returned candidate
window remains `min(250, max(30, limit * 5))`; database work still scales with
the eligible inventory. No model download, extra embedding call or re-index is
required. Representative large-workspace capacity remains evaluation work.

Key-term candidates use rank-fusion weight 0.5 in place of the absent full
lexical channel. `ranking.keywords` exposes the matched terms, matched/requested
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

## Order and match controls

From service 4.2.3, recall and context requests, SDKs and the full MCP
`memory_search`/`memory_context` tools accept:

| Input | Behavior |
| --- | --- |
| `sort: "relevance"` | Rank fusion with the source-age and archive preferences below from 4.3.1; the default. Earlier servers use pure rank fusion. |
| `sort: "recent"` | Order matching candidates by `metadata.source_modified_at` when parseable, otherwise the selected revision's `recorded_at`; rank score breaks ties. |
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

Git connectors now record the last file-changing commit's strict ISO timestamp
as `source_modified_at`. Their source revision format changes once to backfill
this metadata on the next scan, which can temporarily queue re-indexing. Unchanged
files remain stable across subsequent commits, merges and rollback scans. Date
sorting does not itself resolve contradictions or split appended logs by section.

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
| `half_life_days` | `3` | At this age, half of the maximum reduction applies. Range: 1 hour–36,500 days. |
| `archive_weight` | `0.35` | Multiplier for archived candidates, 0–1. One disables the reduction; zero puts them last without excluding them. |
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
{"query":"TASK-7312","all_accessible":true,"ranking_policy":{"recency_weight":0,"archive_weight":1}}
```

The ordering score is `relevance_score × age_factor × archive_factor`, where
`age_factor = 1 - recency_weight × (1 - 2^(-age_days / half_life_days))`.
Defaults therefore reduce a match by at most 25% due to age. Age can reorder
comparably relevant hits within that bounded share of the existing score.
The source date is parsed from `source_modified_at`, with invalid, missing or
unsupported dates falling back to the selected revision's `recorded_at`.
Future source dates receive the same maximum age weight as today's dates.
The reference is `known_at`, otherwise `valid_at`, otherwise the request's start
time, so historical queries do not acquire an age penalty based on today's date.

Each relevance hit exposes `ranking.adjustment`: ordering score, ranking date,
age, both factors and the matched archive directory. The response echoes the
policy and `ranking_reference_time`; the app displays the factors under
**Why this result?**. `relevance_score`, `score_method: normalized_rrf_k60` and
`min_score` remain unadjusted, keeping existing quality thresholds comparable.
Result relevance scores can consequently be out of descending order.
`sort: "recent"` continues to order by date and bypasses these preferences.

Access, source leases, quarantine, validity and query filters still run before
ranking. These preferences add no model call, re-index or candidate-window
expansion. Old servers receive no new field unless a caller requests it; the app
enables the controls only for a compatible workspace server. Source dates and
archive paths remain source-supplied hints, not proof of supersession or truth.
Read cited evidence for current-state decisions. Dated-section chunking,
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
