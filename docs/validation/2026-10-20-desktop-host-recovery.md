# Desktop recovery from server packages

Validated on 20 October 2026 for source 4.30.0. Publication and installed-platform
acceptance remain separate gates in the [automatic release status](../RELEASE_STATUS.md).

The unpublished 4.30.0 candidate exposed two fixture assumptions in the complete
service suite: its shared database contains many organizations, and its access
ledger exceeds the small local-settings record limit. Source **4.30.1** compares
the host wrapper against the full ordinary-snapshot inventory and writes the
modified private ledger fixture separately. The six focused host-import cases,
including both real native database restores, passed again in 29.85 seconds.
This correction changes tests, not the runtime's validation or recovery policy.

The first 4.30.1 native run then caught an elevated-Windows test setup error:
Node's temporary profile belonged to the Administrators group, so the private
fixture writer correctly refused its parent. The corrected attempt creates the
new disposable root with the existing explicit-owner directory helper before
installation. It does not take ownership of an existing directory or relax the
production check. The first frozen attempt is retained; the corrected source
uses a separate release attempt and must pass the normal native gates.
The corrected directory/private-fixture round trip passed with native Windows
Python on the local PC; the disposable folder was removed afterward. JavaScript
syntax and diff checks also passed.

That longer private test root then exposed a real Windows PostgreSQL path
boundary: the database dump filename reached exactly 260 characters. Both
4.30.1 attempts remain unpublished. Source **4.30.2** carries the recovery
feature with [extended-length native file arguments and bounded diagnostic
retention](2026-10-20-windows-backup-paths.md); installed-platform acceptance
still runs against that exact source.

## Implemented behavior

The existing desktop recovery flow now recognizes authenticated server packages.
It verifies the outer package and inner database inventory, displays a restricted
host summary, and supports an explicitly selected included ledger or a newer
encrypted ledger. Database recovery requires both trusted-input confirmation and
confirmation that host/provider settings require separate configuration.

The app and private local-agent controls use the same native implementation.
Fresh destination directories, original organization/memory IDs, current denial
reconciliation, rotated access and explicit connection selection keep their
existing semantics. A separate ledger older than the included host ledger is
rejected before a destination is created. Saved host settings are never activated.

## Focused checks

- **30 distinct Python checks passed** across native backup, native recovery,
  server-package desktop import and supervised-host recovery. The new import
  checks include actual separate PostgreSQL databases with both included and
  external ledgers, exact content, deleted revisions, rotated keys, unchanged
  source files, explicit confirmation, stale hashes, older ledgers, cancellation
  and private temporary-file cleanup.
- A package produced by the actual supervised-host snapshot implementation,
  including a registered source and private provider assets, passed native
  inspection without exposing its credentials or adopting its settings.
- **78 desktop control checks passed**, including the new restricted host
  projections and ledger receipt validation, existing backup controls, native
  lifecycle serialization and private operator behavior.
- Both production web and desktop frontends compiled, along with the Electron
  controller/preload. Formatting and relevant lint checks passed.

## Actual source-app walkthrough

A fresh disposable Electron profile used the real current renderer, sandboxed
preload, native IPC/controller, Python source and PostgreSQL 18 runtime. Its
synthetic source server was stopped before recovery. The OS file picker alone
was supplied with the chosen fixture files; no backup, decryption or restoration
response was mocked.

The walkthrough opened a server package, reviewed its included ledger, chose and
inspected a newer encrypted ledger, and verified that restoration stayed disabled
until both confirmations were selected. It then created one separate verified
copy. The renderer reported no console errors and the 480-pixel layout had no
horizontal document overflow. Completed recovery cleared its update guard.

A subsequent database read verified the original organization, exact Unicode
memory content, the later deletion with no retained revisions, one fresh active
recovery key and unchanged input ciphertext. Source host configuration was absent
from the recovered runtime. The disposable database was stopped after inspection.
This does not claim a new named-provider login, independent cloud delivery or an
OS secure-store enrollment; this manual-key recovery flow did not require one.

The installed six-platform gate now prepares a server-format package from each
target's real encrypted snapshot and uses it for the existing app recovery,
vault, deletion and reopen checks. The private agent restore in that gate still
exercises ordinary desktop snapshots. Those native results must pass before
the release is published; source tests do not substitute for them.

## Limits

This recovers a database into the desktop's separate local host. It does not
provision a provider/OS, restore server credentials, enable source runners or
replicate the original workspace automatically. The original encrypted package
is retained for full supervised-host reconstruction. The normal archive/disk
bounds apply; no 50 GiB capacity, broad hardware or complete disaster-recovery
claim follows from these small synthetic cases. Incomplete native destinations
remain separate and unselectable; retry uses a new destination.

No live user memory was changed and no paid service or hosted model was used.
The [app/agent guide](../service/desktop-host-recovery.md) states the complete
workflow and scope. Strict full-scope completion remains **17/64 (26.6%)**.
