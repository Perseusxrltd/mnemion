# Native backup retention and inventory

The 4.7.0 source extends the guided backup/recovery workflow with an opt-in
retention policy, private ownership inventory, reviewed cleanup and equivalent
local-agent operations. The [user guide](../service/native-backups.md) describes
the controls and limits. Public and installed acceptance is tracked in
[release status](../RELEASE_STATUS.md); this report records source validation.

## Behavior exercised

Only authenticated native captures register files in the private inventory.
The ownership scope includes the workspace, destination path and filesystem
identity. Cleanup keeps files from other keys and files with no private receipt.
Limited mode protects recent full snapshots, their paired access ledgers and
the latest recorded recovery files. Before deleting older copies, it verifies
the saved hashes of two retained pairs and the newest ledger. Those hashes
describe the exact encrypted bytes authenticated at capture.

Fourteen focused cases cover the default keep-all policy, paired-ledger and
latest-access protection, other keys, damaged/missing retained points, changed
candidates, stale plans, replaced folders, cancellation after partial removal,
bounded-batch fairness, invalid catalog paths, the two-point minimum, offline
CLI review/confirmation and unavailable storage. They also cover a storage
provider that accepts deletion but cannot flush a directory: the successful
removal is counted accurately. The final directory-flush case passed after
correcting its fixture to affect only the selected storage directory. The
preceding thirteen cases had passed together.

A separate real PostgreSQL 18/TLS recovery test captured three complete points,
enabled limited retention, retained the required pairs, authenticated the kept
files and restored a retained snapshot with the newest ledger. The restored
memory content matched the source. The first run exposed an incorrect test
query against the revision schema; after correcting that assertion, the real
capture/cleanup/restore case passed. Existing capture/recovery cases passed in
the same focused run before that assertion correction.

## Native Windows files

An isolated Windows Python 3.13 environment passed **11 retention cases**, with
the two CLI/environment cases excluded from that native subset. This exercised
actual NTFS private catalog permissions, file handles, retained-file sharing
locks, authenticated-byte comparisons and deletion by the opened handle.
Dependencies were installed only in a disposable test environment. The user's
installed Windows app and its workspace were not changed.

This is Windows filesystem evidence, not installed Windows x64/ARM acceptance.
The new POSIX-only directory-flush case was added afterward and was checked on
Linux. No live cloud provider was involved.

## Desktop, agent and recovery walkthrough

The full desktop suite passed **159 tests** after the related shutdown fix;
the Electron TypeScript and desktop frontend builds also passed. Added checks
cover policy compatibility, preserved settings, inventory/result validation,
busy guards, reviewed cleanup and failed-shutdown update protection.

A disposable source Electron app exercised the actual renderer, preload,
controllers, private OS socket, CLI and bundled PostgreSQL 18/TLS runtime:

1. A local agent reset keep-all mode and created three new full captures.
2. The app changed retention to two snapshots and two recent ledgers. Unsaved
   settings blocked update readiness; saving cleared that guard.
3. The app displayed the recorded inventory, required explicit cleanup
   confirmation and removed the eligible older copies.
4. The agent observed two retained snapshots with paired ledgers and no remaining
   eligible copies. Every retained encrypted file passed authentication and
   archive inspection using the private fixture key.
5. Repeating an empty cleanup removed nothing. Clean shutdown left no database
   PID files in either the original or recovered fixture directories.

The 1280×940 and 480×940 views were inspected. Counts, policy controls and
confirmation remained readable; narrow screens keep the file table within its
scrollable panel. The new installed-app probe requires matching retention,
retained-pair and app/agent results on each native target.

The Linux source fixture used an authenticated test credential cipher and the
development Chromium sandbox override. It does not certify Linux Secret
Service, macOS Keychain, Windows DPAPI or packaged installation. No production
memory, shared host or external provider was modified.

## Remaining acceptance

Installed six-platform checks, live cloud delivery/deletion contracts, broader
large-workspace measurements and independent host recovery remain required.
The inventory shows at most 100 recent records; cleanup handles at most 200
candidates per operation. These bounds do not impose a total disk-space ceiling.
The latest cleanup result records counts and cancellation state, not a permanent
per-file audit history. This batch advances F08 and A09 without marking either
broad requirement fully shipped.
