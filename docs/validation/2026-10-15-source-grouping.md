# Source diversity and long-document evaluation

This report covers the **4.8.1 source batch**. Native publication, uploaded
artifacts and public automatic updates remain separate in
[release status](../RELEASE_STATUS.md).

**Publication update:** 4.8.1's [native release](https://github.com/Perseusxrltd/mnemion/actions/runs/38722648688),
[independent package publication](https://github.com/Perseusxrltd/mnemion/actions/runs/38726654937),
[live website update](https://github.com/Perseusxrltd/mnemion/actions/runs/38726877979)
and [all six public automatic updates](https://github.com/Perseusxrltd/mnemion/actions/runs/38726882226)
passed on 15 October. Retrieval-quality acceptance below remains open.

## Scoped retrieval

A real PostgreSQL exercise imports a 35-part document through the published
`Document.items()` format, followed by three other matching documents. With
individual-part ranking, all four newest-first results come from the large
document. With the new default, the four results cover all four documents,
including those that the old 30-row candidate window omitted.

Lexical, hybrid and semantic protocol checks cover limits of one, two and all
parts, ordinary text and exact-identifier queries, context packing, and documents
with identical titles. Separate spaces and original authors retain independent
groups. Ordinary memories without the adapter's part metadata are not merged by
title or source-name hints. Revoking a space grant removes it from a subsequent
all-accessible query. Similarity rejection does not consume a document's slot.

Related ranking, search-control and MCP checks passed. SDK checks verify omission
of the new field unless the caller explicitly supplies it. Actual HTTP/MCP checks
exercise default and explicit limits, context results and existing source access
denials. These use a deterministic embedding fixture and do not establish model
quality or production-scale throughput.

## Evaluation and citation regression

The new comparison exposed an existing evaluator error: it compared narrowed
source offsets with the complete saved citation and rejected valid long-document
excerpts. The correction verifies that the returned range lies within the
original citation and that its excerpt is exact. Direct memory/source copies
also require matching relative memory offsets. Complete source and memory hashes
remain checked; source verification caches only hashes and length.

The final focused source-grouping, evaluation and passage selection passed
**45 tests**. Real persisted runs with one versus all parts retain their settings
in the configuration and manifest and show the expected reference/context
coverage difference. Unicode examples cover both direct excerpts and derived
memories with different source text. Altered excerpts, hashes, ranges outside the
original citation and corrupt stored source hashes are rejected.

## App walkthrough

A browser connected to the bundled Studio and a disposable real PostgreSQL
workspace exercises five imported parts across three documents. The default
limit returns three search results, with two additional parts grouped; choosing
`0` returns all five. A context limit of two returns four citations. Empty search
limits block submission. Desktop and 390-pixel mobile layouts remain within the
viewport, and the controls and source summaries were visually inspected.

The evaluation form starts with a limit of one, rejects an empty limit on
submission, and persists an explicit zero in both the queued run configuration
and its reproducibility manifest. This browser exercise verifies queueing, not
completed evaluation execution; the real runner comparisons are covered by the
focused tests above. The TypeScript client and final bundled Studio build passed.

## Compatibility and remaining acceptance

Python SDKs omit the option unless requested; the app enables its search and
evaluation controls only with service 4.8.1 or later. Existing saved evaluation
configurations without the field retain individual-part retrieval. TypeScript
client compilation and the production frontend build passed during development.

A read-only Windows check authenticated the existing independent administrator
against the actual **4.7.1** shared server. Its three readable spaces include a
reader-only source scope; that membership does not grant model administration.
Before the bounded lexical comparison could finish, the public route returned
`ERR_NGROK_3200` (tunnel offline). No production memory writes, permission changes
or cloud model calls were made. Live before/after ranking and saturation remain
unverified.

This batch does not resolve the whole current-state/natural-language issue,
infer that newer text supersedes older claims, split dated sections, or prove
large-workspace capacity. Source metadata identifies groups; it is not proof of
authorship or source truth. The full roadmap remains open.
