# Agent and ingestion stabilization — 2026-10-13

Version 4.1.6 addresses the reported Git revision/scan-label issue 30, MCP search
defaults in issue 24, small version diagnostics in issue 29 and standalone-port
migration guidance in issue 23. It is in release preparation; native and public
delivery checks remain required before publication.

The focused suite passed **80 tests in 36.12 seconds** under a 512 MiB process
scope and one CPU quota. It used disposable PostgreSQL with restricted roles,
real local HTTP/MCP transports, local Git repositories and scanner processes.
The embedding fixture checks transactions and authorization; it is not a
retrieval-quality benchmark. No production workspace or cloud model was used.

The regenerated OpenAPI and agent contracts passed three additional catalog
and version-consistency checks. Repository lint, formatting for all 387 Python
files, release-version validation and changed-document relative links passed.

The first invocation encountered a previously generated, ignored 4.1.4 Studio
bundle in the newer source checkout. The bundle was preserved outside the
checkout, restoring the normal source-test environment. The complete focused
run then passed. The production bundle/version guard was not weakened.

## Git evidence and managed scans

Real Git history checks cover unchanged documents across unrelated and empty
commits, literal bracketed filenames, changed/added/renamed paths, merged branches
and a prior snapshot. Each cited commit is checked against the actual file
content. Complete document/chunk values for unchanged paths remain identical,
not just their revision labels.

The real service connector test withdraws one source after a requested scan and
checks that the remaining document stays at memory version 1, with zero changed
and one unchanged result. Existing failed-inventory, competing-run, permission,
request acknowledgement and busy-inference tests also passed.

Separate scanner processes receive `startup`, `poll` and `requested` reasons while
following current and restored runtime fixtures. A managed watcher preserves a
pending requested reason through an update wait, and launcher handoff retains
it with filtered credentials. The production runner reports those values; an
unknown environment value cannot enter diagnostics, and plain watch mode starts
fresh. Older scanners retain their existing command line and rollback support.

The fix still inventories files and sends their current evidence through the
normal connector protocol. It does not claim delta-only transfer, new provider
coverage or a measured large-repository throughput result.

## Agent scope and monitoring

Query-only MCP search/context and no-argument map calls use the current accessible
scope across two source spaces. Tests exclude a separate owner's private memory,
verify explicit narrowing, reject empty/false/conflicting/inaccessible selections,
and repeat calls after one source's access is suspended. Current permission and
lease checks remain authoritative. Both current and older HTTP MCP flows,
stdio, per-request credentials and revocation tests passed.

Health responses report the actual service version without source identities,
credentials or update inventory. Client contracts still accept older hosts that
omit this optional field. Existing combined and standalone MCP transport tests
cover the two documented listener options; no automatic extra listener or
cross-origin redirect was added.

The full roadmap remains open, including company sign-in, hosted OAuth,
independent host recovery, broader provider capture, retrieval-quality work and
the separately encrypted secrets vault. This release does not close those
requirements.
