# Search and agent compatibility batch, 13 October 2026

Source version: 4.2.3. Publication and native release gates are tracked separately
in [release status](../RELEASE_STATUS.md).

Focused integration checks use real isolated PostgreSQL with non-owner service
roles and a deterministic protocol fixture embedder. They cover newest-first
selection beyond the ordinary candidate window, filtering by recorded time
before candidate selection, malformed/missing source-date fallback, explicit
semantic/rank rejection, literal-hit preservation and context filtering.
The fixture tests behavior and access policy; it is not a model-quality benchmark.

Real HTTP MCP checks exercise compact discovery below 4 KB with required
validation bounds, profile identity, paginated/filtered operation discovery,
describe/write/search/fetch, effect mismatch and private credential guards.
Native SDK initialization returns a session ID in the optional session mode;
another key for the same principal is rejected, grant revocation removes access,
and key revocation rejects the existing session. Default HTTP remains stateless
and keeps both old tool names and new aliases.

Git fixtures verify per-file source modification times, unrelated-commit
stability, literal filenames, merges and rollback. The connector format changes
once for date backfill; no migration SQL is added. The workflow check verifies
unfiltered pull-request coverage and the complete release native call after
removing the duplicate push trigger.

The initial focused run passed **17 tests**. After extending compact catalog
pagination and guarding unrepresentable source dates, **six targeted checks**
passed. The TypeScript client and production frontend build passed, including
the new controls and bundled offline guides. Existing retrieval/identifier
and default MCP behavior had already passed **18 tests** before these additions.
These are targeted checks of changed behavior, followed by the established
automated release pipeline, without repeating local whole-product suites.

The final release-automation/status guard suite passed **42 checks**, following a
dry run against the actual published 4.2.2 receipt and current GitHub inventory.
Publication and downstream dispatch were disabled in that dry run. The final run
includes source-freezing and duplicate-dispatch guards. Scripted preparation
regenerated both contracts and passed version validation; source lint and format
checks passed. This does not claim that the first live automatic publication has finished;
its workflow and retained receipts provide that evidence after release.

The first complete release attempt (`38429792683`, source `7c5375e`) exposed
missing descriptions on new full-profile MCP fields and a Git-date test oracle
that expanded a literal bracketed filename as a wildcard. That attempt was
cancelled and did not publish. Full-schema descriptions are restored; the test
now uses literal paths and distinct deterministic commit times. The three checks
covering the original failures and compact discovery passed after correction.
The corrected attempt guards and deterministic Git fixture passed 20 focused
checks; version preparation, source lint and patch whitespace checks also passed.
Corrected unpublished attempts use a new frozen branch; the successful release
receipt, rather than the cancelled run, determines publication readiness.

Remaining limits: no universal calibrated confidence threshold, no guarantee that
recency resolves conflicting evidence, no dated-section chunking, no distributed
MCP session store and no claim of live acceptance in every named agent product.
