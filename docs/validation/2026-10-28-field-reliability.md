# Field reliability: bounded inventory, activity and search authorization

**28 October 2026 source qualification.** The repairs address portions of
[issues 47 and 48](../implementation/multi-agent-field-readiness.md); both reports
retain their full remaining acceptance. Publication and installed versions are
reported separately in [release status](../RELEASE_STATUS.md).

## Search diagnosis and permission-preserving change

One bounded, read-only probe on the existing 4.46.40 service used the current
application role, checked its source identity and made no inference calls or
settings changes. That administrator could access **four spaces and 722
eligible/indexed records**, with zero pending records or source warnings. A
no-hit lexical request took **12,310.518 ms**. Eligibility/lexical SQL took
**6,408.574 ms**, and eligibility/index-count SQL took **5,473.320 ms**.
This is a smaller scope than the reporter's eleven spaces.

The selected lexical statement had SHA-256
`f937c0867908d2d1143a818ce3d7096e1e900272b027c60cffa98565aee400f6`.
Read-only EXPLAIN execution took **9,620.128 ms** with the original setting and
**4,793.853 ms** with JIT disabled only in that diagnostic transaction. Both
reported 46,765 shared buffer hits, zero reads and no JIT section. These samples
do not establish JIT as the cause. No persistent JIT change was made.

[Migration 035](../../mnemion/service/migrations/035_statement_authorization.sql)
keeps the existing `authorized(space, level)` function as the authority. A
security-definer function resolves only the caller's grants, and uncorrelated
RLS subqueries reuse that result within each statement. The existing tenant,
principal-disable, provider lease, source ownership and capture-custody checks
remain. SELECT and ALL/write policies both retain their original levels;
audit/private-note reads retain reviewer access and erased-memory protection.
There is no permission cache across requests, statements or transactions.

A disposable PostgreSQL benchmark seeded **800 synthetic memories across four
spaces** and used a login that neither owned nor bypassed RLS. The original
per-row policy query reached the unchanged **15,000 ms** statement timeout.
Its failed result and stopped owned server are retained. A separate fresh
candidate fixture applied the normal migration and measured the same lexical
SQL at **279.944 ms execution / 287.912 ms elapsed**, with zero result rows and
zero buffer reads. JIT was off in both measured transactions. The failed baseline
was not repeated; this is not a paired live-host speedup measurement.
Both disposable servers were stopped. Live latency and all-eleven-space activity
acceptance remain pending deployment.

## Functional checks

The first focused run passed **34 cases**, with one failure in the new inventory
MCP journey. Direct HTTP inventory, grant revocation within the same database
connection, contributor/reader separation, source lease and custody revocation,
activity pagination, journal behavior and existing retrieval checks passed.

The failing case identified the compact MCP tool's fixed **16 KiB** allowance.
It now exposes the same bounded response-size choice as the full read/write
tools, with the original 16 KiB default and **128 KiB maximum**. A targeted
follow-up passed all **six cases**, including the original inventory failure,
compact discovery and the generated agent contract. The first failure is retained;
unchanged database-policy checks were not rerun locally.

The inventory fixture contains 101 large-content records with 500-character
Unicode subjects and arbitrary private metadata. A 100-record summary page
and its cursor remainder return every ID once, stay under 128 KiB even with
Unicode escaping, and exclude content, evidence and arbitrary metadata.
Subject previews are bounded to 160 UTF-8 bytes with an explicit truncation
flag; a full fetch retains the complete subject and content. The actual MCP
path reproduces full-page rejection and accepts the explicit 128 KiB summary
request. Quarantine, missing source visibility and revoked grants remain enforced.

The activity fixture walks 143 matching events from 215 events with tied
timestamps across three pages, without duplicates or gaps. Changed filters and
malformed cursors are rejected, and revocation blocks a later page. Real Git
filing checks confirm that a no-op updates status/scheduling without another
activity receipt. Existing audit rows are not erased.

Studio adds action filtering and older/latest page controls, clears inactive
activity pages from its query cache and hides cached rows on a read error.
Older servers retain their recent-activity view with an upgrade hint. The typed
SDK exposes inventories and activity filters/cursors/cancellation. The SDK and
Studio TypeScript/Vite production builds passed with the prepared 4.46.43
versions, matching staged assets and verified brand assets. All 22 existing SDK
tests passed, alongside Ruff and formatting checks. Required platform release
checks remain separate from this local qualification.

No production data, source policy, deployed service or paused publisher was
changed by these source tests. Product telemetry collection remains unavailable,
and the original RAM failure and complete V08 acceptance remain open.
