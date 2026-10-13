# Matched evidence validation — 13 October 2026

Unreleased correction for [issue 35](https://github.com/Perseusxrltd/mnemion/issues/35),
prepared separately from the personal sign-in candidate.

The focused group passed **13 checks** using real isolated PostgreSQL
and deterministic fixture embeddings. It includes existing retrieval and source
tombstone checks, plus:

- A matching answer near the end of a long document in lexical, hybrid and
  semantic modes; both displayed passages include it and remain at most 4,000
  Unicode code points.
- Exact reconstruction from source/memory offsets, with the complete fetch
  preserved.
- A derived memory citing only an allowed source range; its source offsets
  differ from the summary and exclude text outside that range.
- Unicode case folding, emoji and nonzero source origins without displaced
  citations; context packs retain the selected citation.
- Joint query coverage instead of the first common word, and the selected
  embedding passage when there is no literal query match.
- Preserved smaller embedding-chunk display budgets when a better matching
  passage occurs elsewhere in the same memory.

A separate synthetic selector measurement scanned a one-million-character
cited source with 32 densely repeated query terms. Three runs had a median
of **140.54 ms** under a one-CPU limit; a traced run added **72,495 bytes** of
Python allocations and returned 4,000 characters. This measures the selector
only, excluding the input allocation, database, models and process baseline.
It is not a whole-service RAM or throughput claim.

These are transaction, policy and passage-selection regressions, not a
retrieval-quality benchmark. The change does not close the identifier-ranking,
recency, relevance-threshold or natural-language evaluation issues. Release
validation and a published package are still required.
