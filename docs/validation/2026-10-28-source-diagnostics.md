# Source diagnosis and release preparation — 28 October 2026

This source batch continues [issues 47 and 48](../implementation/multi-agent-field-readiness.md).
Their full acceptance remains open. Public distribution and installed versions
are tracked separately in [release status](../RELEASE_STATUS.md).

## Source controls and privacy

An explicit `health.sources` request with `details=true` adds a paginated
diagnostic view. It reads the existing connector, scope, principal and inventory
tables through the application role and their existing row-level policies.
There is no new security-definer function, migration, grant or control bypass.
The default personal source counts retain their original grant-based meaning.

Tenant administrators can diagnose affected sources without receiving a content
grant. Active connector operators see their own controlled sources. Other
callers, including administrators of ordinary spaces, receive the explicit
unavailable-control scope without connector, source or operator identities.
Diagnostics contain fixed reason/recovery codes and current capability hints;
they omit labels, external memberships, source paths, checkpoints and raw error
text. Every later command still checks its own current authority.

The default diagnostic page is 20 entries, with a 100-entry maximum and a UUID
continuation cursor. The app, Python SDK, TypeScript SDK and MCP use the same
endpoint. Connections adds source availability and links to existing controls;
queries are scoped to the current service, tenant, principal and administrator
state, and inactive query pages are discarded. Failed diagnostic reads hide
cached rows. Opening this view performs no recovery write or source scan.

## Qualification

All **57 focused Python cases passed**, with no failures or skips, in **49.247
seconds**. They include real PostgreSQL under non-owner application logins,
real HTTP/Python-SDK and compact MCP requests, plus the existing source-health,
release-automation and generated-contract checks. The cases verify:

- tenant and connector-owner separation, with no control grant to a space
  administrator, reader or reviewer;
- paged affected-source inventories without healthy or foreign-source rows;
- sticky operator pauses and denied operator self-resumption;
- continued unavailability after resumption until fresh provider permissions;
- disabled or unsuitable source identities requiring tenant repair;
- private source/error/file sentinel values absent from diagnostics;
- a real incomplete file scan clearing only after repair and a successful scan.

Studio and SDK production builds passed, along with **22 existing SDK tests**,
Ruff and formatting checks. These builds do not establish installed app or
all-platform field acceptance. Source tests used disposable data and fixture
embeddings, without production mutations, live model calls or source cleanup.

## Release automation correction

The original preparation invocation stopped before version changes because the
required concrete release notes were absent. After those notes were written,
preparation updated versions and contracts, then its validator found stale
telemetry coverage: coverage had been generated before the changed agent
contract whose bytes it hashes.

The [preparation order](../../deploy/release_automation.py) now exports OpenAPI
and the agent contract before generating coverage. A regression executes this
orchestration against a changed fixture contract and the real coverage-hash
validator. It passes within the 57-case run. For this already prepared batch,
only the remaining coverage generation and release validator were run; both
passed. Version and contract preparation were not replayed.

The original preparation failures and a separate test-selection typo are
retained. The typo executed no tests; the corrected selection ran the passing
suite above. None is reclassified as an earlier successful full preparation.

Canonical telemetry documents now link to generated Git inventories for current
counts, while retaining historical coverage and failure evidence. V08 remains
Building, with collection disabled, destination/route null and no release
authorities. Resource, wire, provider/privacy and full platform qualification
remain required before collection or a completion notification.
