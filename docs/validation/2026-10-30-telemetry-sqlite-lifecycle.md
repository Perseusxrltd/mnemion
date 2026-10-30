# SQLite handle lifecycle — 30 October 2026

**The idle retained SQLite connection is rejected for this release.** An owner
note had proposed one idle connection. These probes do not implement that
proposal, do not adopt it on Linux only, and do not move the 2 MiB or 0.5%
ceilings.

No eligible existing owner was identified. The backend is unavailable for
remote-only, onboarding-only, and tray-only lifecycles. No new resource run is
justified.

## What ran

Finite disposable Node SQLite lifecycle probes. Each mode ran an external
child-process `UPDATE`, then an atomic replacement. The modes were a
per-operation baseline, a retained read-only connection, and a retained
read-write connection.

| Host | Runtime | Arch | Exit |
| --- | --- | --- | --- |
| Linux | Node 22.22.0 | x64 | 0 |
| Windows | Node 25.2.1 | x64 | 0 |

Both runs are standalone Node probes. They are not Electron builds and they
are not resource measurements. `resource_acceptance` remains false. Nothing in
production changed. Cleanup was true on both hosts.

## Results

Every mode on both hosts saw the other process's commit.

Baseline, both hosts: replacement completed, path identity changed, and both
the held read and a later reopen saw the replacement generation.

Windows, both retained handles: replacement failed with `EPERM`. Path identity
did not change. The held read and a reopen both still saw the original
generation.

Linux, both retained handles: replacement completed and path identity changed.
Each held connection kept reading the original generation until it was closed
and reopened. The reopen saw the replacement.

## Decision

Reject the idle-handle proposal for this release because the retained Windows
handles block replacement. V08 stays Building. Collection, destination and
route stay false/null/null. All 66 requirement texts and states stay unchanged.
