# Native backup and independent recovery workflow

Status: source implementation after published 4.4.0; installed release acceptance
is pending. The [user guide](../service/native-backups.md) and
[implementation contract](../implementation/native-backup-recovery.md) retain the
unfinished scope explicitly.

The desktop now owns a protected backup policy, serializes background/manual
jobs, coalesces missed intervals, persists failures and retry deadlines, and
checks the availability of its last recorded encrypted files. It supports
manual keys when the OS store cannot unlock. Rotated keys remain separate from
older encrypted files. Retention currently keeps all copies.

Inspection and restore use bounded private stdin, typed projected results and
the owning OS account. Snapshot and ledger authentication binds the reviewed
SHA-256 values to the actual restored bytes. Restore creates a fresh native
PostgreSQL cluster in a new private directory, reconciles current access and
deletions, rotates keys, pauses external connections, and records a verified
copy before the app offers to switch. Original data is retained. Archive
packing, verification and hashing support cooperative cancellation, and staging
and destination checks admit estimated disk capacity before large writes.

## Focused checks

- The initial combined capture, archive and recovery run passed 34 checks.
  It used real PostgreSQL and a bundled PostgreSQL 18 recovery destination.
  Source PG16 exports used the corresponding PG16 tools; newer dump-tool
  output is not assumed compatible with an older restore target.
- Six recovery/setup checks subsequently passed, including inspection before
  first-time setup and preservation of incomplete private recovery work.
- The combined follow-up passed **37 checks**, including disk admission. It
  exposed and corrected a cross-host timezone issue: a session-expiry constraint
  using calendar days can differ across daylight-saving boundaries. New snapshots
  retain the source timezone; restore configures the database and its client
  connection accordingly, while inventory hashes remain canonical UTC.
  The final 19 service/native recovery checks also passed with a conflicting
  `PGTZ` environment setting; the PostgreSQL tool and reconciliation connection
  both use the recorded timezone. No fixture database processes remain.
- The latest complete desktop regression run passed **146 checks**. It includes
  protected policy reopen, unavailable-store refusal, manual keys, scheduler
  coalescing, stale configuration, cancellation during key unlock, persistent
  failure/backoff, missing/resized files, output limits and update drain.
- The desktop walkthrough exposed a real status-refresh overlap: opening the
  recovery view could start a status query just before **Inspect snapshot**.
  Recovery now drains that read-only query and rechecks mutation/shutdown guards.
  A regression check covers the ordering.
- Switching copies now reports a transition status instead of calling a closing
  host, rejects overlapping local mutations and blocks update/quit until the
  handoff completes. The actual desktop recovery/reopen walkthrough covers it.

## Desktop walkthrough and release boundary

A disposable Linux Electron profile uses the current sandboxed renderer and
preload, actual native IPC/controllers, the source engine, bundled PostgreSQL 18
with TLS/pgvector, and the real BGE Small CPU model. All three workflow phases
passed: snapshot and newer deletion ledger, independent restoration with fresh
administrator access, and reopening the recovered copy after process restart.
The retained memory remained readable, the post-snapshot deletion stayed deleted,
and the original workspace was subsequently reopened through the app. Desktop
and 480-pixel layouts were inspected; small backup sizes now use bytes/KiB rather
than rounding down to zero MiB. A separate real Electron shutdown check recorded
the native `stopped` event, exit code zero and removal of its PostgreSQL PID file.
The remaining disposable database from an interrupted handoff was also stopped
using its verified TLS/process identity.

The local walkthrough uses an authenticated cryptographic test cipher because
this environment has no unlocked OS credential store. It is **not** evidence
of Linux Secret Service, Windows DPAPI or macOS Keychain acceptance. The local
Chromium process also uses the development sandbox override required by this
environment; production installer sandboxing retains its separate gate.

The installed-app pipeline now exercises three additional phases on each of
its six targets: encrypted capture, later deletion/current ledger, and restore
followed by app restart and reopening both the recovered and original hosts.
Those phases require the real OS store and retain the original credential hash.
Only the platform file picker is replaced with deterministic selections inside
the disposable fixture. Forms, IPC, encryption, database, model and persistence
remain real. A failed phase blocks that platform's acceptance.

Real cloud delivery, configurable pruning, complete agent schedule/root-selection
controls, broad hardware/storage workloads, recovery-custodian onboarding and
company failover remain open. No live user memories or production hosts are
modified by these fixtures, and these source results do not close the broader
requirements or represent a published release.
