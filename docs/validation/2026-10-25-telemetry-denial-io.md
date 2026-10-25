# Bounded reuse of telemetry denial observations

**Unreleased source checkpoint, 25 October 2026; V08 remains Building.** Native
and Python producers now reuse a known negative file observation for at most
**250 ms** during existing work. This reduces repeated filesystem work when
optional measurement is already denied. Corrected native checks and the actual
first burst diagnostic completed; resource acceptance remains open. A later
synchronous-refusal source change also passed its own checks and second diagnostic.
All 66 requirement texts and states are unchanged; production
collection/destination/route remain false/null/null.

## Bounded tradeoff

The [native store](../../studio/electron/telemetry-store.ts) and
[Python aggregate store](../../mnemion/product_telemetry/aggregate.py) may decline
an already disabled or exhausted scope without another file-stat or SQLite read
inside this interval. A file change is not necessarily observed immediately:
newly re-enabled work may lose optional telemetry samples for up to 250 ms.
Settings/status reads and every admitted observation, reservation and final
handoff retain fresh policy and private-storage checks. No cached observation
can enable collection or supply permission.

Day changes and the original **60-second** hint expiry still invalidate a hint
when work checks it. A file observation is refreshed on subsequent work after
its 250 ms interval; an unreadable or changed file discards the hint. There is no
idle timer or open database connection. Python now also merges exhausted scopes
only under the same file version/day, preserving the original expiry rather
than extending it. Contribution limits and spent delivery allowance are unchanged.

The later native source returns literal `null` synchronously from `snapshot`
for unavailable collection or a known refusal. Eligible work still enters the
private asynchronous `readStamp` path for fresh SQLite/policy checks. The
[workflow boundary](../../studio/electron/telemetry-workflow.ts) skips awaiting
that null result, and the diagnostic forwards the exact snapshot return without
an additional async wrapper. This avoids those snapshot Promise/await costs;
`TelemetryWorkflow.begin` itself remains asynchronous. The earlier checks and
first burst below predate this change; its separate final evidence follows.

## Source evidence

The Python policy/aggregate/workflow selection passed **58 tests in 26.45 seconds**;
the separate delivery selection passed **20 tests in 9.54 seconds**. The native
build passed. These results do not qualify installed platforms or full resources.

The first native selection retained **29 passes, one failure and two
Windows-only skips**. Its concurrent-reservation test required exactly one
winner, although zero lock waiting permits both callers to defer. The
[corrected test](../../studio/electron/scripts/test-telemetry-delivery.mjs) requires
at most one winner, checks ledger bytes and pending data, and verifies that an
explicit later attempt can use the intact queue when both defer. A separate
held-reader case exercises rollback and recovery without changing delivery code.
The original failure remains preserved. The corrected native selection passed
**31 tests with two Windows-only skips**, 33 total,
in **14.357 seconds**.

After the synchronous-refusal change, the final native selection passed
**37 tests with two Windows-only skips** (39 total, **26.668 seconds**), and
**91 frontend checks** passed in **10.247 seconds**. Native and frontend builds
passed; the frontend TypeScript/Vite build took **5.09 seconds**. The Python
sources were unchanged from their 58- and 20-pass selections above.

The [store regressions](../../studio/electron/scripts/test-telemetry-store.mjs)
and [Python regressions](../../tests/test_product_telemetry_aggregate.py) check
the bounded no-stat interval, fresh checks afterward, re-enable sample loss,
scope merging and original expiry. Within the controlled interval, 512 denied
calls make no repeated file-stat/SQLite calls; continued work refreshes at the
boundary. These source checks do not qualify all installed platforms.

## First actual burst diagnostic

The [existing pipeline probe](../../deploy/probe_telemetry_pipeline.py) completed
at **20:17:52 UTC** under Electron 44.9.3 / Node 24.22.0 on Linux x64. Each variant
made **544 synthetic instrumentation calls** after real headless app bootstrap:
32 initial calls and 512 further calls, with the enabled scope exhausted before
the latter. This is not a
representative memory workload; process CPU includes runtime work, and the
baseline excludes startup/static-module cost. There was no forced GC. Actual
gauges used an explicit fixture unmetered declaration for unknown network cost.

| Variant | Process CPU (ms) | Added RSS (bytes) |
| --- | --- | --- |
| Collection unavailable | 3.943 | 360,448 |
| Collection-capable fixture, saved opt-out | 7.900 | 2,523,136 (2.41 MiB) |
| Collection-capable fixture, enabled | 116.751 | 5,066,752 (4.83 MiB) |

Both opted-out and enabled RSS remain above **2 MiB**. These individual
observations do not establish a general speedup, stable memory reduction or
representative-workload CPU pass.

Enabled collection accepted **32 paired records and one four-byte TLS report**,
retained one spent **65,536-byte reservation**, cleared its lease and used a
24 KiB database. Unavailable/opted-out variants made no writes or reports.
All journeys and cleanup checks passed: isolated profiles and temporary
certificate trust were removed, the Collector stopped, zero aggregates were
published and no production memory/model calls occurred. All **185 source/build
inputs** still matched when reviewed. Reserved bytes are not full wire cost.

## Synchronous-refusal burst follow-up

The new source and direct-return diagnostic completed the same 544-call workload
at **20:28:53 UTC** on the same Electron/Node/Linux runtime:

| Variant | Process CPU (ms) | Added RSS (bytes) |
| --- | --- | --- |
| Collection unavailable | 5.333 | 0 |
| Collection-capable fixture, saved opt-out | 8.525 | 1,982,464 (1.89 MiB) |
| Collection-capable fixture, enabled | 120.742 | 4,644,864 (4.43 MiB) |

The single opted-out observation is below 2 MiB; it does not establish whole-app
or platform acceptance. Enabled RSS still exceeds the target. Zero net RSS in
the unavailable variant is not zero-allocation or zero-overhead proof. Source,
diagnostic return forwarding and runtime variation prevent treating these two
runs as an isolated product-only saving or a general CPU improvement.

The enabled variant again accepted 32 paired records and one four-byte report,
kept one 65,536-byte reservation spent, cleared its lease and used a 24 KiB
database. Both other variants made no writes or reports. All journeys and
profile/Collector/certificate cleanup checks passed, with zero published
aggregates or production memory/model calls. Its **185 source/build inputs**
matched the reviewed current source. The first receipt and failure remain intact.

## SHA-256 provenance

| Original evidence | SHA-256 |
| --- | --- |
| First burst receipt | `56221b2d512782b8bd6333a3d13537b123433fbd842a40b98a614e7d5fc97238` |
| First 185-input inventory | `38f5a73c3d86ca27872bb975a68e5b11a6f796f3d99f3803ea45fb191b29a6c9` |
| Synchronous-refusal burst receipt | `aa6bbba55be8ceb2b5786c9ac891e806ffb2add5bb8a6001943ca2dc649fe1f0` |
| Final 185-input inventory | `2225c7d8c591a287e1c16798254f8d886988ed7c44889cc23576d42c667c8c72` |
| Cleanup receipts, identical contents for both runs | `c52b943d5363ce402d72c37f33f89cbeaa3c7b9444744746e3d867040c4584dc` |
| Python policy/aggregate/workflow checks | `506f32b8cb64f07d2d9d4a3a8f2823e623fd829c2e881e024f875911608a35b2` |
| Python delivery checks | `5ba21c13b1364e4bb2443af3256bcce29b1102da72f179f6a8ea4a9bc86f8fd2` |
| Earlier corrected native checks | `b90b24d133e4411b50fbf970252f9a5fe9cae799ce134a117e7821adda6a0736` |
| Final native checks | `310e01e351cd59cf6d4f9a9ee24309c6923b442de64a7dd8165460dfb827c2ba` |
| Final frontend checks | `07fabbd8dc0e67548ab9ba4a7c48a24cfdbeafe7e03b2f9af08311736ee33a6b` |
| Original concurrent-reservation test failure | `878429f48c80cd2d201774e6b7266564e5a09c89e0c760e891bc743c6c496118` |
| Native build logs, identical contents before/after the final change | `d6c88c1616d194ec9efcfcb3452aba2a266884a087e8fff900fdafce023ecfc4` |
| Final frontend build | `fd7e2177f1b14aef94ae5bca27ecfd321d75d6315036f6d5c122b7f4af1f5277` |

The prior [synthetic and real-memory resource measurements](2026-10-25-telemetry-memory-profile.md)
remain historical evidence. Avoiding repeated denial I/O does not establish an
overall memory reduction or CPU pass. The unchanged **2 MiB added-RSS and 0.5%
of one core over representative work** targets, renderer/IPC, all-six-native plus
web, whole-wire and production collector/ingress privacy qualification remain open.
