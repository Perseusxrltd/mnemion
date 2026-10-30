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
reader allowed replacement immediately; cleanup passed. The R3 observer
and writer used those operations. The original unclassified failure lacks enough
detail to identify that race as its definitive cause.

macOS ARM64 completed 128 cycles in its enabled case with `hosting_ready: true`
and root exit zero, but recorded zero telemetry attempts and zero reports. Its
driver failure remains unresolved.

## Reviewed source corrections

The shared workload now creates one 13-character query prefix per launch before
measurement. Payload sizes, recall limit five, 128 cycles and checkpoint order
are unchanged. The function remains self-contained when serialized into the
renderer: the first candidate's missing module binding was caught and corrected,
and seven canonical Node checks passed in the original worker execution.

Astra exercised that serialized function on `9456c51a` against the real loopback
API in eight fresh JavaScript contexts. All 48 save/fetch/search requests and
16 cycles passed in 8.245 seconds. Each launch used a distinct prefix; fetched
content and original payload lengths matched, and each final query returned
exactly its own note. Owned cleanup completed. This is a bounded retrieval
regression check, not a replay of the installed 128-cycle resource comparison.

The first Windows fix, allowing delete sharing on a held reader, still failed
Node's replacement operation. The accepted source instead publishes immutable
numbered progress files through one shared host-side writer. Each private run
allows at most 64 records of 1,024 bytes. Readers stream a bounded directory
scan, require the writer's ASCII filenames, and read at most 1,025 bytes to
detect oversize data. Incomplete, malformed or ambiguous records stay unknown;
legacy `monitor.json` is used only when the new directory is absent. There is
no replacement of an open destination, retry loop or additional service.

Six focused Windows checks passed in 0.63 seconds, including a real Node
producer publishing its next record while Python holds the previous one open.
The earlier test-process timeout and failed sharing proposal remain retained;
closing the test's input pipe fixed that timeout. Review also reproduced and
fixed acceptance of noncanonical numeric filenames. The final receipt now
preserves allowlisted failure metadata and keeps missing hosting readiness
unknown through Python/JavaScript conversion.

A real Linux desktop build on `5fe51030` passed in 19.22 seconds with the
project TypeScript compiler, native network build and normal runtime staging.
The staged canonical module matches the module used by the real API probe,
and the compiled application imports it. Build inputs were unchanged.

## Remaining acceptance

These corrections do not rescore the original failed native run or establish
that its Windows stop had the reproduced file-sharing cause.

All retained resource coverage remains partial and no budget comparison
completed. Windows/Linux group lifetime CPU is available; per-process residency
and macOS descendant CPU still have coverage gaps. The
[8 MiB and 0.5% allowances](../implementation/telemetry-resource-budget-2026-10-30.md)
remain unchanged. The [whole-product efficiency requirement](../implementation/runtime-efficiency.md)
extends beyond telemetry. Public hosting, collector operation and useful fleet
statistics require their separate acceptance.
