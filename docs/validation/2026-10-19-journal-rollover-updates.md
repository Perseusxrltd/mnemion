# Git rollover and local app update controls — 19 October 2026

The 4.19.0 source combines journal capacity work for issue 39 with private local
agent control of desktop updates. All writable test repositories, memories and
databases are synthetic and isolated. No live-office migration or user workspace
change is part of this validation.

Focused validation covers **68 Python cases** (52 journal/replay/filing cases and
16 service cases) and **64 desktop cases** (17 update-controller, 9 private
operator protocol and 38 workspace identity/connection cases). Desktop process and web-renderer builds, locked
dependency metadata, pinned formatting/lint and release metadata checks pass.

The installed Git-setup flow in the 4.18 release failed on all six targets before
publication: native identity sanitization discarded `service_version`, so the
renderer hid capabilities supported by the server. Two focused regression checks
failed against the old compiled code; all 38 identity/connection checks passed
after retaining the bounded, optional version field. Unrelated server fields
remain excluded. Missing or invalid optional versions do not break valid logins,
and reconnect reads the current server rather than trusting cached capabilities.
The installed hosting probe now checks version metadata immediately and retains
the actual registration, restart and memory-preservation flow. Its successful
native acceptance remains a release-pipeline requirement. 4.18 was not published;
4.19 supersedes it rather than changing its frozen source.

The focused journal tests use actual Git repositories and include a daily writer
whose records exceed the real 20,000,000-byte file limit. Publication produces
multiple bounded files and leaves the sealed original unchanged. Exact retries
retain the same commit and catalog count; a warmed retry reads zero journal body
bytes during append planning. A separate instrumented check observes Git object
reads and verifies that an append does not reread the sealed original.

Checks also cover a fresh publisher with no cache, loss/damage and rebuilding of
the private metadata index, a concurrent publisher winning the first push,
conflicting event/version identities, numbered-path gaps, catalog downgrade,
whole-file archival, late writes, and a deletion followed by a later upsert.
Complete replay keeps the deletion effective; omitting its file refuses replay.
The index is inspected to confirm that it contains metadata rather than the
synthetic memory text. Existing publication/privacy and filing cases are retained.
The actual catalog parser from the frozen 4.18 source
(`7b5dea97291cc34eb5f93cc61fcb472f2308cb00`) was also loaded separately: it accepts
schema 1 and refuses schema 2 with `invalid_journal_catalog`. This is why upgrading
every publisher and journal runner is an explicit prerequisite for continuations.

The focused service checks use actual PostgreSQL for publication consent,
transactional receipts, queue behavior, permission changes and scheduled filing.
The local update-controller checks exercise the real controller and dispatcher
with synthetic platform adapters: immediate checking, snapshot isolation,
stale preferences, administrator policy, version-bound restart, drafts and
cancellation. These controller tests make no update download. The existing
private operator protocol checks retain authentication, framing and retry coverage.

The installed operator acceptance flow now reads the actual app update policy
through its bundled native engine and private pipe. That new native flow still
requires the release pipeline; source tests do not prove installed acceptance.
Builds, publication, website refresh and all six public automatic-upgrade targets
are tracked separately in [release status](../RELEASE_STATUS.md).

The private publication report's `append_planning` byte counts describe JSONL
objects processed while planning all push attempts. They exclude network fetch,
Git compression, history-protection comparisons, catalog and generated-note work.
They are neither physical disk traffic nor complete network-bandwidth measures.
The bounded synthetic capacity case is not a live-provider or company-scale
throughput benchmark. Complete backfill, provider onboarding, independent recovery
and current production-office availability remain separate acceptance.
