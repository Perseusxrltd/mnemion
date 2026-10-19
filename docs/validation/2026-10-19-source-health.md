# Text-source isolation and scoped health, 19 October 2026

Scope: 4.21.0 source, addressing
[issue 43](https://github.com/Perseusxrltd/mnemion/issues/43).

The regression fixture used the actual filesystem provider from commit
`125f5e8` against a disposable HTTP service and real PostgreSQL. One Markdown
file with a truncated multibyte sequence reproduced
`source_is_not_utf8_text`, `access_suspended: true` and zero unrelated updates.
The new provider passes that scenario, including binary bytes and oversize text.

Six initial HTTP/PostgreSQL acceptance cases passed. They verify that healthy
files update while a corrupt file retains its last good data; incomplete scans
cannot infer deletions or advance complete checkpoints; repair updates the same
memory identity; clean reconciliation removes genuinely missing files; private
health counts do not expose another user's sources; narrowed recall omits
unrelated warnings; actual source suspension hides evidence while reporting the
loss; and 60 failures produce only 50 detailed paths without acknowledging a
pending sync request. An unreadable structured journal file still suspends its
scope. These tests use the normal restricted database roles.

The completed focused checks cover 94 cases across source isolation, connector
leases/replay, source permissions, live JSONL, journal projection, HTTP health,
agent contracts and clients. The existing 92 checks passed on the first combined
run; the new Git fixture passed after correcting its test configuration, and an
additional 101-document deletion sweep verifies that finalization cannot be
relabelled as a partial scan after deletion has begun. This targeted follow-up
avoided repeating the already passing suite.

All 16 TypeScript client checks and the production web build passed. A real
Chromium session used the ordinary workspace-key login against a disposable
service and PostgreSQL. **Connections → Source status** showed one healthy
update, zero removals, the incomplete-scan message, the expandable relative path
`résumé.md` and its UTF-8 error. The screenshot was visually checked at
1600 × 1100. This used actual scan receipts, without a synthetic desktop bridge;
it does not test native installation.

Package locks, release metadata, formatting and lint checks passed. Native
installation, publication, website refresh and public upgrades remain separate
automated gates; this source record is not evidence that 4.21 is already
downloadable. See [release status](../RELEASE_STATUS.md) for those results.

Limits: skipped files retain earlier indexed data, which can be stale until
repair. Missing-file reconciliation waits for a complete scan. JSON/JSONL and
complete journal imports deliberately remain fail-closed. These changes do not
add text repair, arbitrary binary extraction, provider sign-in, automatic host
wake, external alert delivery, or improve the semantic ranking model.
