# Question-term retrieval and ranking evaluations

Source batch: 4.3.3. This record separates source validation from publication;
the [release status](../RELEASE_STATUS.md) records platform and delivery gates.

## Focused service checks

The real-PostgreSQL question, evaluation, MCP-default and current-ranking suites
passed **58 tests** in 29.51 seconds. They cover question ordering and cited
context, explicit syntax/modes/IDs, complete lexical matches, threshold behavior,
source expiry and mapping changes, paused sources, quarantine, and inference-busy
fallback. Evaluation comparisons retain the chosen settings; a service-version
change stops a new run before recording mixed results. SDK and MCP checks cover
optional controls and older-server compatibility. Client and Studio production
builds passed. The built interface also completed enabled/disabled search with
the expected result ordering, displayed the matched term, and submitted a real
evaluation retaining the selected term/age/archive settings. The 390-pixel
viewport check found and corrected a nowrap label; the rebuilt label wrapped
visibly and measured 318 pixels for both its client and scroll widths. A
simulated 4.3.2 service identity hid the new evaluation controls and sent neither
new field when starting a run. This is client compatibility evidence, not a test
of an installed older binary. The isolated database and browser were closed
after the walkthrough; no actual workspace or cloud model was used.

These deterministic fixtures establish behavior and authorization boundaries,
not general language quality.

The first release candidate's complete service checks caught a missing MCP
input description for `keyword_fallback`. The Python 3.13 run had 947 passing
tests, 10 skipped and this one failure. Both search and context now describe
the option in their tool schemas; the existing combined HTTP/MCP contract and
query-default checks passed **2 tests** in 8.26 seconds after the correction.
This changes tool metadata, not retrieval scoring. Publication still requires
the corrected source to pass the complete release gates. The first candidate
also failed during the Intel Mac installed app's initial model download; this
platform gate must pass on the corrected candidate before publication.

## Previously evaluated public-corpus regression

The [machine-readable aggregate](2026-10-14-question-regression.json) records
60 queries from the existing LongMemEval plan: 56 answerable and 4 unanswerable.
The corpus had already been used for development and held-out measurements;
**this is a regression comparison, not a new independent held-out result**.
No algorithm tuning was performed against these paired results.

The run copied the stopped benchmark database into an isolated directory and
used its existing 2,877 indexed public records. It streamed the public dataset,
checked scope, content hashes and index completeness, and compared explicit
`keyword_fallback: false` and `true` at the same per-question reference time.
Pair order alternated to reduce cache-order effects. The pinned
`intfloat/multilingual-e5-small` model ran offline with two CPU threads and a
1.5 GiB process-group memory cap. There were no production writes or cloud
calls; the source database remained unchanged and the copied server stopped.

| Metric | Disabled | Enabled |
| --- | ---: | ---: |
| Recall@5 | 90.33% | 95.24% |
| nDCG@5 | 87.71% | 90.18% |
| MRR@5 | 88.99% | 89.58% |
| Recall@10 | 96.58% | 96.58% |
| Median search latency | 191.93 ms | 213.27 ms |

The fallback activated on 43 of 60 questions. Four answerable questions improved
Recall@5, none lost Recall@5, and 52 were unchanged. This does not mean every
ranking position improved. Unanswerable cases are excluded from recall means;
no generated-answer accuracy or calibrated confidence is claimed.

The aggregate preserves the exact measured code hashes. Subsequent changes add
the controls/default, evaluation recording and explicit guards that retain the
old behavior when query inference is unavailable or busy; they do not change
the measured available-model scoring algorithm. The focused checks cover these
guards. Larger corpora, more languages, a new declared held-out split, current
shared-office queries and comparative model/hardware baselines remain open.
