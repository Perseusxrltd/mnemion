# Private state publication — 20 October 2026

Source candidate: 4.37.0. This combines the unchanged fair-indexing migration
and queue view from unpublished 4.35/4.36 with a local state correction.

The [4.35 Windows ARM installed-app job](https://github.com/Perseusxrltd/mnemion/actions/runs/39392435604/job/118532066284)
failed during `create`: a normal `local:status` request reported
“Use an ordinary local folder without links.” Publication was withheld. The
queued 4.36 build was cancelled so the corrected source can ship together.

A separate native Windows x64 reproduction used the unmodified state code and
paused exclusive publication after the real filesystem link operation. The
fully written destination had two links: its published name and private staging
name. A concurrent status read produced the same `unsafe_location` error; after
publication removed the staging name, the exact record read successfully with
one link. This establishes a concrete race without claiming access to the
discarded runner's private diagnostics.

Readers now retry only a two-link ordinary file, with five metadata delays
totalling at most 310 ms. They must observe one link before opening and recheck
the opened file's type, link count, identity and size before reading bytes.
Persistent links, reparse points, unsafe ownership and oversized state remain
refused. Publication, private permissions and exclusive creation are unchanged.

**Linux: 12 passed, 5 Windows-only checks skipped.**
**Native Windows x64: 14 passed, 3 checks skipped** (two POSIX-only cases and an
elevated foreign-owner fixture unavailable to the current user).

The state suite covers a concurrent first publication, a publication that never
finishes, a link added after the initial path check, interrupted replacement,
persistent links, size limits, cross-process locks, staging cleanup and existing
Windows sharing/permission/junction checks. No installed user workspace, model,
memory or application file was modified by the isolated tests.

The preceding 18 PostgreSQL dispatch/reindex cases, 28 historical migration
cases and six database/one browser queue checks remain evidence for their
unchanged code. Full six-target installed acceptance and the actual guarded
shared-host upgrade are separate gates; neither is inferred from these results.
