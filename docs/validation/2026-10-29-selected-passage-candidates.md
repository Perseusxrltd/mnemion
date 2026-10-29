# Bound passage chronology to selected candidates

The passage-ranking query now applies its candidate filter inside the
materialized eligibility query. Previously, PostgreSQL rebuilt eligibility for
the complete accessible corpus before the outer query selected at most 250
candidates. Both query variants share the same tenant, source, revision,
quarantine, claim and temporal filters. Row-level security and final permission
checks remain active.

## Regression and focused checks

The new [real PostgreSQL regression](../../service_tests/test_passage_candidate_work.py)
creates 32 unrelated memories and one matching memory, then examines the query
actually used by retrieval through `EXPLAIN (ANALYZE, FORMAT JSON)`. It runs as
the existing non-owner application role in an isolated test database.

| Observation | Original query | Candidate query |
| --- | ---: | ---: |
| Selected passage candidates | 1 | 1 |
| Materialized eligibility rows for passage ranking | 33 | 1 |
| Full index eligibility count | 33 | 33 |
| Matching memories returned | 1 | 1 |

The original test failed on the excess materialization and its receipt remains
retained. After the query correction, **61 tests passed in 27.88 seconds**, with
zero skips, across candidate work, passage chronology, retrieval, ranking and
accessible-scope suites. Ruff also passed. Coverage includes historical
corrections, source deletion, revoked or expired access and passage timestamps.

This proves bounded work for the chronology query in the fixture. It does not
measure an end-to-end production latency improvement or resolve every part of
[issues 47 and 48](../implementation/multi-agent-field-readiness.md). The earlier
[live field measurements](2026-10-29-mcp-field-sessions.md) used server 4.46.44
and do not include this correction.

The runtime change is in [retrieval.py](../../mnemion/service/retrieval.py), with
the original eligibility query retained for full-corpus candidate selection and
index counts. This batch requires the normal source and native release checks;
publication is tracked in [release status](../RELEASE_STATUS.md).

Private evidence is retained under the 29 October selected-passage-candidates
completion record: the original failing test, passing check logs and JUnit
results, pre-preparation source hashes and release-preparation receipts.
