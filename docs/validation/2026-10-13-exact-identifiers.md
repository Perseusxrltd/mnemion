# Exact identifier and filename retrieval, 13 October 2026

This is validation of the 4.2.2 development source for
[issue 27](https://github.com/Perseusxrltd/mnemion/issues/27).
It is not a publication receipt or a general embedding-quality benchmark.
Check [live release status](../RELEASE_STATUS.md) before choosing a download.

## Failure and correction

The previous lexical channel required every query term in the memory body.
An exact task ID in `metadata.path` could therefore be absent from both the
lexical pool and the first semantic candidates. Reranking that existing pool
could not retrieve the missing file.

A new scoped query admits literal identifiers from the body, subject or path.
It selects independent bounded coverage and subject/path windows. This also
keeps a file available when many broad ledgers mention more of the query IDs.
Subject/path matches receive weight 3; literal coverage, lexical and semantic
ranks each retain weight 1, with RRF `k=60`. The API and app expose the matched
counts and weights. Existing rank-map keys and score-method identifiers remain
compatible. There is no new migration or additional model call.

## Evidence

The real-PostgreSQL identifier tests cover:

- A file outside the old semantic pool reaching first place among broad ledgers.
- Independent label candidates when the file is below the coverage window.
- Literal boundaries, near IDs, filename extensions, Unicode normalization and
  Windows/Unix paths; caps and explicit truncation warnings.
- Current space grants before ranking, grant revocation during inference,
  quarantine, metadata filters, source tombstones and historical revisions.
- A correction between SQL candidate queries discarding old lexical/identifier
  ranks instead of combining evidence from different revisions.
- Ordinary query scores and explicit semantic-only behavior remaining unchanged.
- Explicit lexical exclusions staying on the existing channels, so a positive
  identifier cannot resurrect an excluded result.

The final dedicated identifier run passed **10 checks**, including exclusion
semantics. The earlier identifier, accessible-scope and agent-contract run
passed **27 checks**.
The earlier identifier/concurrency and busy-fallback run passed **24 checks**;
these runs overlap. Existing retrieval and citation-passage checks passed as
well. A separate HTTP, model-routing and evaluation run passed **58 checks**.
The TypeScript client passed all **14 checks**, and the production web build
passed with its offline documentation and canonical brand assets. Further
product, native and public-release validation remains required.

An isolated comparison loaded the actual published 4.2.0 retrieval source
(`af7f9b795bc94b36c432810148e80a82fd1ce340`) against the same disposable
PostgreSQL database and deterministic four-dimensional fixture as the candidate.
The synthetic corpus has 49 memories: one target file, six broad ledgers and
42 semantic distractors. Across 12 alternating warm calls per version, the
target was absent from the old top six and ranked first in every candidate
call. Each call used exactly one query embedding. A plain query returned the
same IDs, scores and ranking details in both implementations.

[Machine-readable observations](2026-10-13-exact-identifiers.json) include
source-file hashes and all latency samples. On this single-CPU, 512 MiB local
test, median recall time was **230.201 ms before and 277.247 ms after**.
The additional identifier query costs database work; the correction does not
claim faster search. These fixture timings are not a hardware minimum,
production latency promise or an evaluation of an embedding model.

## Remaining limits

The candidate windows bound returned rows, not work scanning eligible records.
Larger corpora still need representative capacity measurements. Natural-language
quality, calibrated no-match thresholds, recency and contradiction handling
remain separate open work (issues 17, 28 and 31). The literal label preference
can elevate an exact file whose contents are less useful; matching an identifier
does not establish that a result answers the whole question or is current.
