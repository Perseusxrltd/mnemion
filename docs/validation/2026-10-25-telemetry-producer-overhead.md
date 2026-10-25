# Telemetry producer overhead

**Unreleased source checkpoint, 25 October 2026; V08 remains Building.** Native
and Python producers now skip repeated SQLite work after observing an explicit
opt-out or an exhausted contribution scope. Focused checks passed, and the
actual headless desktop/collector diagnostic completed at **18:59:36 UTC**.
Its opted-out and enabled RSS results still exceed the **2 MiB full-feature
target**. All 66 requirement texts and states are unchanged; production
collection remains false, with null destination and route.

## Denial-only hints

The [native store](../../studio/electron/telemetry-store.ts) keeps a fixed
65-byte scope bitset and an observed opt-out flag. The
[Python aggregate store](../../mnemion/product_telemetry/aggregate.py) keeps one
bounded hint for its most recently disabled/exhausted store; the
[workflow boundary](../../mnemion/product_telemetry/workflow.py) consults it before
reading policy again. These hints can only decline optional measurement work.

A hint requires the same private file version, day and valid monotonic interval
of at most **60 seconds**. A changed/replaced/unreadable file, changed day or
expired/invalid clock interval discards it when existing work next checks it.
There is no expiry timer, open database connection or positive consent cache.
File/revision races can drop extra samples; they cannot authorize collection.
Every accepted observation, reservation and final handoff still uses the current
policy, generation/revision, storage-permission and SQLite fences. Contribution
limits, opt-out clearing and spent delivery allowance are unchanged.

## Actual diagnostic and its limits

The reusable [Python runner](../../deploy/probe_telemetry_pipeline.py) and
[Electron probe](../../studio/electron/scripts/probe-telemetry-pipeline.mjs) start
the real headless app, wait for `client-ready`, and use actual gauges, a private
local TLS Collector, disposable profiles and temporary certificate trust.
The final runtime was **Electron 44.9.3 / Node 24.22.0, Linux x64**.

The workload makes **544 synthetic instrumentation calls**: 32 initial calls and
512 more after the daily scope is saturated. It does not run 544 memory
operations or a representative memory workload. The baseline is after bootstrap,
excluding startup/static-module cost; there is no forced garbage collection.
Process CPU can include concurrent app/runtime work and is not exclusively
attributable to the producer.

CPU, heap and network admission were not faked. The actual network cost was
unknown; an explicit **fixture-only unmetered declaration** allowed the enabled
attempt. This does not qualify automatic network-cost detection. Source
disclosure remained unavailable; only isolated variants changed in-memory
availability and their private saved choice.

| Final variant | Accepted aggregate writes | Accepted TLS reports | Process CPU | Added RSS |
| --- | --- | --- | --- | --- |
| Collection unavailable | 0 | 0 | **4.845 ms** | **180,224 bytes** |
| Collection-capable fixture, actual saved opt-out | 0 | 0 | **16.138 ms** | **3,424,256 bytes (3.27 MiB)** |
| Collection-capable fixture, enabled | 32 | 1 | **122.075 ms** | **6,709,248 bytes (6.40 MiB)** |

The unavailable and opted-out variants performed no condition checks or
reservations. The enabled variant delivered exactly **four body bytes**, retained
one spent **65,536-byte reservation**, cleared its lease and had a **24 KiB
database** before cleanup. Those reserved bytes are not measured full wire cost.
Every isolated profile was removed, the Collector closed, temporary certificate
trust was removed, and no aggregate was published. There were no production
memory/model calls or installed-app/host changes.

All **185 recorded source/build inputs** still matched the final inventory when
reviewed, as did both current probe scripts. The receipt and per-variant records
remain original evidence; they are not a native release or all-platform pass.

## Earlier measurements and failures retained

Before the opt-out hint, the same three-variant harness measured opted-out CPU
at **124.519 ms** and RSS at **6,307,840 bytes**; enabled CPU was **126.287 ms**
with **6,709,248 bytes** added RSS. Both harness scripts match the final run.
These observations support the scoped reduction in repeated denied work; they
are not a general app speedup or a representative-workload CPU qualification.

The earlier probe before saturation hints measured enabled CPU at **535.147 ms**
and RSS at **9,068,544 bytes**. Its already-saturated 512-call phase used
**433.222 ms** process CPU; the next saturation-hint probe recorded **14.438 ms**
for that phase. Those earlier runs remain separate from the final three-variant
source probe. Runtime/GC/timing variation prevents treating them as universal
latency or memory guarantees.

The first Python regression run had **one failure and 56 passes** because its
choice fixture omitted `expected_generation`. The corrected fixture retains the
generation check. Separately, the Python 3.12, 3.13 and 3.14 service jobs in
[CI run 40221952456](https://github.com/Perseusxrltd/mnemion/actions/runs/40221952456)
on source `f35f1074` each failed the same packaging fixture: it omitted the two
newly required native build scripts. The
[corrected fixture](../../service_tests/test_build_desktop.py) includes those
scripts and the C/header inputs, and verifies that changing them invalidates the
source digest. The integrity gate is unchanged. That old CI run completed with
nine passed jobs and three failed service jobs, all with the same fixture error;
the passing focused checks qualify the correction, not a rerun of the full CI.
The accepted [macOS component steps](2026-10-25-telemetry-native-conditions.md#macos-component-follow-up)
retain their separate scope.

## Focused source checks

| Check | Result |
| --- | --- |
| Python | **61 passed in 20.95 seconds**, including three packaging checks and the corrected fixture. |
| Native source/store checks | **18 passed, two Windows-specific skips**, 20 total, in 17.524 seconds. |
| Builds and lint | Electron build, frontend TypeScript/Vite (**4.69 seconds**) and Ruff passed. |

SHA-256 provenance; private raw logs and workstation paths are not published:

| Evidence | SHA-256 |
| --- | --- |
| Final three-variant diagnostic receipt | `eb22e03ae5daad987d603120e0600073a801beb84a268e97e211c44c94fdbcb5` |
| Final 185-input inventory | `e6eb0cea9bb006227430cfd664dda661198a80b4a62634bd26f7f254d844b552` |
| Final unavailable variant | `81ca3f87bb0291f8767f6f04054db126ecd93e138e609936aff4105c27f81d5d` |
| Final opted-out variant | `c91f124f97328d3093c1d428623621b4aa64a1a1316313aa35ce25cd3640506c` |
| Final enabled variant | `403e14f072df0597568efae5a0e2829e79ad1b1cd60193725788026c5087d838` |
| Same-harness run before opt-out optimization | `ca46eb6569ef06896b9aaadda756dad87629b7153119673bc3da2b37add7ae04` |
| Original probe before saturation hints | `9306f7b16d7ff3486fb5838891fe2d71128bb7c021edc70f77a3d264143b6abf` |
| Earlier saturation-hint probe | `b01a4664ed4f04159427dc6213e4e1c422bd8ba8ec90146303c62971eb6376d9` |
| Final Python checks | `12b8461f692dbcbabda912be9ba5ec00dada77bf8ae855c5236236565f5640a0` |
| Final native source/store checks | `1251ec917e25e9199b263d599aafa0b6be4b73593148f18e684a79230ea50ff1` |
| Electron build | `d6c88c1616d194ec9efcfcb3452aba2a266884a087e8fff900fdafce023ecfc4` |
| Frontend build | `026569eb4570f2cc0ac008baad84c72109e001c111e79dd51f6e56d8d5686bce` |
| Ruff | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` |
| Original missing-generation fixture failure | `20163efa62ee5e1694c226c713508917cda08d381b55279ed3cd755d80fe85f0` |
| Original CI service/Python 3.12 failure | `29ebaf55c24058167b1ff1a27ac1597fe1ac0efc919bfd5152c3fa2a5b89baa9` |
| Original CI service/Python 3.13 failure | `8504fd51be4a95ba38d00f2b84edab60a9b17b12017379b3b9954f0f32b7536b` |
| Original CI service/Python 3.14 failure | `d09da4f041aea5c695b708e88c39f2762e5a94acabdd7633f705c8ae2f261bbb` |

The [full V08 contract](../implementation/anonymous-product-telemetry.md) remains
open: representative-workload CPU and full resource limits, all six installed
native targets plus web, total wire cost, useful aggregation and production
collector/ingress privacy still need qualification. No resource target was
relaxed, and these diagnostics do not establish a telemetry release.
