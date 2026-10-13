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
rows, not database scan work. Large-corpus capacity, natural-language quality,
no-match thresholds and recency ranking remain separate evaluation work.

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
