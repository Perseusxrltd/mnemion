# Installed process-role RSS evidence

31 October 2026. Reviewed source `85476a0f` passed the focused checks below.
The installed Mac ARM workload passed at integrated source `0ff248b8`.
Whole-resource acceptance remains open. Production telemetry stays off.

The existing installed 128-cycle workload adds one Electron metrics
observation at each of its nine checkpoints: before workspace connection,
after connection, after the first memory cycle and delivery settlement, then
after 8, 16, 32, 64, 96 and 128 cycles. These observations add no production
polling, persistent worker, workload padding or replacement memory operation.
The existing workload, delivery, admission, native CPU and cleanup evidence
keep their scope.

`app_main` and `app_renderer` come from the actual main process,
BrowserWindow renderer PID and Electron metric types. RSS is retained in
bytes. PID plus Electron `creationTime` tracks identity within each launch;
that timestamp is not the OS birth counter. These samples remain separate
from the native owned-launch ledger and do not cover exited or unseen helpers.

For each repeat, `enabled` and `opted_out` are compared with that repeat's
`unavailable` launch at the same role and named checkpoint. The report keeps
both absolute RSS observations, the signed difference (current minus
unavailable), and the maximum matched-phase signed difference. It retains
the first observed difference without subtracting either launch's initial
RSS. That initial observation does not establish full startup coverage.
Matching does not use PIDs across launches, RSS rank or helper ordering.

Qualification requires aligned phases, unambiguous roles, stable within-run
identities and available counters. Extra windows, devtools and rejected or
truncated observations must block qualification. Missing data stays explicit;
ambiguous helpers stay uncompared. A numeric difference alone is insufficient.

The canonical new artifact is `build-notes/telemetry-installed-resources.json`:
case `process_roles` contains the checkpoint observations, and top-level
`process_role_rss` contains the comparisons. The outer Python receipt keeps
its existing summary. The public projection allowlists bounded roles,
identities, RSS and diagnostic flags, excluding credentials, endpoints,
contents, names, paths and renderer URLs. The 25-byte product telemetry
payload is unchanged.

The original eight-test run recorded 7 passed and 1 failed because phase
rejection was lost during resanitization. After that correction, the affected
phase-mismatch and hostile-input checks passed; TypeScript `--noEmit` also
passed. The original failure is retained.

Further pure-source review found four cases that incorrectly published
`ownership_valid=true`:

- Original rejected-row evidence was erased by another public projection.
- An original truncation flag was lost after excess rows had been removed.
- Zero `creationTime` was accepted as a birth identity.
- Main and renderer rows could share one PID and identity.

Those original cases remain preserved. The corrections retain failure flags,
require exact positive birth identities and reject duplicate identities; all
11 focused checks passed. A further review found that an overlong checkpoint
list could lose its run-level overflow flag when its nine retained rows were
republished. That flag now survives both republication forms and comparison.
A failed devtools URL read also remains an observation failure.

The final affected test file passed all 12 checks in 162.1089 ms. TypeScript
`--noEmit` passed after restoring the existing Electron type dependencies;
the original missing-dependency attempt is retained. Passing checks were
not repeated merely to produce a log. Those source checks are separate from
the installed measurements below.

## Original installed result

[Run 41165832667](https://github.com/Perseusxrltd/mnemion/actions/runs/41165832667)
completed successfully on `macos-26` ARM64 at source
`0ff248b82317111ca4b54ec96caf603039805fd0`. Its original
`telemetry-installed-resources-macos-arm64` archive has SHA-256
`b3ad8256a37f81101e80c0ef834d68ed55b88e03e517e4fb85934711d0d216fc`.
The retained archive and all 18 extracted files passed digest verification.

All six counterbalanced cases completed their 128 memory cycles: all 2,310
memory API requests succeeded, each host became ready and exited with code
zero, and no cleanup failures were reported. Each enabled case delivered one
25-byte report to the test collector. Opted-out and unavailable cases delivered
none. This was test delivery; production collection remains unavailable.

Each case retained all nine phases and one stable identity per observed
`app_main`, `app_renderer`, `utility` and `gpu` role. Phase and ownership checks
passed with no checkpoint overflow. The original report marks the scoped
role comparison available. Its maximum signed RSS differences, in bytes,
are shown below; each uses the same repeat's unavailable case as baseline.

| Repeat / condition | App main | App renderer | Utility | GPU |
| --- | ---: | ---: | ---: | ---: |
| 1 / opted out | -5,455,872 | 1,097,728 | 114,688 | -3,145,728 |
| 1 / enabled | 475,136 | -2,064,384 | 114,688 | -2,670,592 |
| 2 / opted out | -1,392,640 | -376,832 | 131,072 | -2,523,136 |
| 2 / enabled | 1,720,320 | -262,144 | 81,920 | 442,368 |

The original artifact retains both absolute observations and the signed
difference at every phase, including the first. Differences between launches
do not establish a causal improvement. These checkpoints do not cover all
startup activity, exited helpers or every process's full lifetime. Native
process coverage remains partial, and the budget comparison remains false.
The original workflow was dispatched once. A dropped GitHub read was recovered
by reconnecting the observer to that run; the workload was not rerun.

A scoped role comparison does not qualify whole-process lifetime accounting
or whole-product CPU/RAM savings. The allowances remain 8,388,608 additional
RSS bytes per participating process and 0.005 of one CPU core, both
**UNACCEPTED**. Resource acceptance remains false, and all 66 requirement
states remain unchanged. Old runs without these samples are not rescored.
