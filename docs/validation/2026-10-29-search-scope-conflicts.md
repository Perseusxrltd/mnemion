# Search scope conflict diagnostics — 29 October 2026

Search now distinguishes a changed set of readable spaces from a changed
embedding model. If a source permission lease expires, a grant changes or a new
readable space appears during an all-space search, the request returns HTTP 409
with `scope_changed`. Its fixed message asks the caller to retry with current
permissions. Actual model-routing changes retain `generation_changed`.

Both checks still run before model inference and before returning results.
There is no cached permission, automatic retry, expanded grant or fallback to
content from an expired source. Neither error adds source names, space IDs or
memory content to the response.

## Reproduction and verification

The original source, based on `21a2f377d3bf28585a8ba4ea8f0483798a639252`,
failed three deterministic regression cases. Each returned `generation_changed`
although the test had changed only accessible spaces:

- A new readable space was created during embedding.
- A managed source's permission lease expired before embedding.
- The same lease expired while embedding was in progress.

The tests use real PostgreSQL and non-owner application roles with synthetic
data. The corrected [scope tests](../../service_tests/test_accessible_scopes.py)
verify the distinct conflict, refusal before inference when access has already
expired, no private source/content identifiers in errors, and an empty result
on a subsequent search after that source is no longer readable.

The focused scope, reindex and retrieval suite passed **41 tests**, with no
failures, errors or skips, in 112.878 seconds of pytest time. It includes the
existing real model-switch conflict and cross-space vector-dimension checks.
Lint passed. The three original failures remain retained as failures.

## Field acceptance remains open

This explains a reproducible misleading error. It does not prove which event
caused the reporter's four concurrent failures on 4.46.40, improve measured
latency or establish installed-host acceptance. The reported concurrency,
source freshness, database availability and truly changed-space identification
criteria remain in [multi-agent field readiness](../implementation/multi-agent-field-readiness.md)
and [issue 47](https://github.com/Perseusxrltd/mnemion/issues/47).

The normal source/native release checks and a published-host verification are
still required. All 66 requirements and V08's Building state remain unchanged;
production telemetry remains disabled.
