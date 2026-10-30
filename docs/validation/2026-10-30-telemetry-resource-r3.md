# Third installed telemetry resource run

30 October 2026. Original run
[41070603786](https://github.com/Perseusxrltd/mnemion/actions/runs/41070603786)
used source `dc7f6c417bf78c9cbded7c6a485b30763bc63dde`. All 11 preparation jobs
passed; all six resource jobs failed. Resource acceptance and production
collection remain open.

The observer was interrupted by a WSL restart. Observation resumed against the
same completed GitHub run, preserving the first evidence directory. Six original
artifact ZIP digests and all 103 extracted files were verified once. No runtime
was replayed or missing source reconstructed.

| Target | Successful memory API calls | Cases reaching 128 cycles | Driver-complete cases | First failed case |
| --- | ---: | ---: | ---: | --- |
| Linux x64 | 1,935 | 5 | 5 | r2 unavailable |
| Linux ARM64 | 1,929 | 5 | 5 | r2 unavailable |
| macOS x64 | 1,956 | 5 | 5 | r2 unavailable |
| macOS ARM64 | 1,155 | 3 | 2 | r1 enabled |
| Windows x64 | 434 | 1 | 1 | r1 opted out |
| Windows ARM64 | 1,941 | 5 | 5 | r2 unavailable |

All 9,350 API requests succeeded. Eight valid 25-byte fixture reports were
accepted, totaling 200 bytes; no forbidden metadata or malformed body was
observed. All 29 launched cases reported successful owned cleanup. Seven absent
cases retain unknown launch/cleanup state. The earlier Windows uninstall
refusal and Linux directory-cleanup failure did not recur in this run.

## Original diagnostics and reproduced defects

The final Python receipt projection omitted `hosting_ready`, `root_exit_code`,
`failure_stage` and `failure_category`. The artifact's separate
`build-notes/*-owned-launch.json` files preserved them. Earlier private checkpoint
statements that no original failure category survived were incorrect; the build
notes supply the following evidence without another native run.

Linux x64, Linux ARM64, Windows ARM64 and macOS x64 recorded
`startup-error` / `memory_recall` in their final unavailable case, after 2, 0,
4 and 9 cycles respectively. The shared workload resets its query counter on
every launch, uses the same workspace, and asks for five hits. The sixth launch
creates a sixth matching note for each reused query.

A bounded local real-API probe on `9c0ddfd0` reproduced the omission: all 24
save/fetch/search requests succeeded and fetched content was exact, but the
eighth repeated query's five hits omitted its newly saved note. The fixture
completed cleanup in 9.467 seconds. This establishes a collision in the
diagnostic workload's retrieval assertion. Correcting query identity must
preserve 128 cycles, payload sizes, checkpoints and exact content/recall checks.

Windows x64 recorded `startup-error` / `unclassified` after 16 cycles. A separate
native Windows fixture established that an ordinary Python read handle blocks
Node's atomic replacement of the same progress file with `EPERM`. Closing that
reader allowed replacement immediately; cleanup passed. The current observer
and writer use those operations. The original unclassified failure lacks enough
detail to identify that race as its definitive cause.

macOS ARM64 completed 128 cycles in its enabled case with `hosting_ready: true`
and root exit zero, but recorded zero telemetry attempts and zero reports. Its
driver failure remains unresolved.

## Remaining acceptance

The initial final-projection correction passed ten focused Python checks in
the original Windows Grok execution. Astra requested a follow-up because missing
hosting readiness must stay unknown through Python/JavaScript conversion.
Query isolation and Windows read-sharing corrections are under review.

All retained resource coverage remains partial and no budget comparison
completed. Windows/Linux group lifetime CPU is available; per-process residency
and macOS descendant CPU still have coverage gaps. The
[8 MiB and 0.5% allowances](../implementation/telemetry-resource-budget-2026-10-30.md)
remain unchanged. The [whole-product efficiency requirement](../implementation/runtime-efficiency.md)
extends beyond telemetry. Public hosting, collector operation and useful fleet
statistics require their separate acceptance.
