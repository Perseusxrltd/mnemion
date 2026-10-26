# Telemetry attribution: six-case diagnostic

**Completed diagnostic, 26 October 2026, 03:55 UTC.** The one declared six-launch
run completed successfully, and retained-artifact qualification verified all six
functional journeys. **Resource acceptance remains false:** both enabled runs
exceeded the unchanged 2 MiB target at matched main-process phases. The decision
is to review cold initialization and storage-runtime ownership, without another
benchmark dispatch or a budget revision. At this checkpoint, frozen 4.46.13
remains separate and pending native/public acceptance; production telemetry
stays disabled.

## Declared experiment and stop rule

The [runner](../../deploy/probe_telemetry_renderer.py) accepts `--attribution`;
the [existing diagnostic workflow](../../.github/workflows/telemetry-renderer.yml)
exposes an optional input defaulting to false. The default three-condition mode
is retained. The declared attribution order is fixed:

| Replicate | Launch order |
| --- | --- |
| 1 | Unavailable, opted out, enabled |
| 2 | Enabled, opted out, unavailable |

The plan allows **six launches**, each with **128 save/fetch/lexical-search
cycles** (384 memory operations), plus the existing onboarding flow. It requires
source freezing before dispatch, disposable profiles, no model calls, no forced
garbage collection or idle padding, and no replacement of the actual pressure or
consent checks. It does not qualify a pressure-stress workload.

After examining all six original outcomes, **stop and identify one allocation
mechanism or make an explicit documented architecture/budget decision**. Do not
add runs or select small optimizations to obtain a favorable number. A proposed
budget revision is not an accepted change to the resource contract.

## Instrumentation and comparison

The [Electron probe](../../studio/electron/scripts/probe-telemetry-renderer.mjs)
adds at most **32 first-activation samples per launch**, using numeric process,
V8 and OS counters around telemetry imports, SQLite open/close, network-cost
startup, condition preparation, reservation and the owned transport connection.
It records no memory contents, network identifiers or raw mapping paths in those
samples. Nine workload phases cover before/after connection and the first, 8th,
16th, 32nd, 64th, 96th and 128th completed memory cycles.

The [analyzer](../../deploy/report_telemetry_renderer.py) compares each condition
with the unavailable baseline from its **own replicate**. It subtracts growth
at matching phases, then finds the largest matched difference. Duplicate phases
are rejected; ambiguous process roles and replaced processes cannot masquerade
as continuous measurements. The previous difference of per-run maxima is
retained as a separate observation.

## Earlier source checks and offline findings

Before dispatch, the source checkpoint consisted of the following checks and
offline reanalysis; no six-launch result existed then.

The [five report tests](../../tests/test_telemetry_renderer_report.py) passed in
**2.73 seconds**. They cover different peak phases, process replacement, duplicate
phases, ambiguous roles and correct replicate baselines. Node syntax and the
selected Ruff checks also passed. The saved check receipt binds the four
inspected diagnostic/test source files by SHA-256.

Backward-compatible artifact qualification passed against the original three
journeys from source `b9a29886830b63fac75c863e57d55287cc9bd321`,
[run 40260081248](https://github.com/Perseusxrltd/mnemion/actions/runs/40260081248).
It retained all **1,961 reviewed source matches per journey**, functional results
and cleanup, with `attribution: false` and `resource_acceptance: false`.
**No application or workload was replayed.**

The offline analyzer used that original workload receipt's five available phases:

| Main-process condition, compared with unavailable | Previous difference of sampled maxima | Maximum matched-phase growth difference | Phase |
| --- | ---: | ---: | --- |
| Enabled | 3,440,640 bytes | **3,440,640 bytes** | 32 memory cycles |
| Opted out | 1,187,840 bytes | **1,318,912 bytes** | Workspace connected |

The enabled result still exceeds **2 MiB**. The changed opted-out value corrects
how existing observations are compared; it is not a new performance result.
The [original SQLite/renderer report](2026-10-26-telemetry-sqlite-cleanup.md)
and its receipts remain preserved.

## Completed six-launch result

[Run 40265207114](https://github.com/Perseusxrltd/mnemion/actions/runs/40265207114)
completed successfully at **03:49:17 UTC** on source
[`dc98218c70c3ec4453ee6f54065474ac4b3af969`](https://github.com/Perseusxrltd/mnemion/commit/dc98218c70c3ec4453ee6f54065474ac4b3af969).
Qualification at **03:50:01 UTC** matched all **1,966 reviewed files in each
variant**. All six original outcomes are retained in the declared order:

| Original launch | Successful API requests | Accepted local writes | Accepted four-byte TLS reports |
| --- | ---: | ---: | ---: |
| R1 unavailable | 387/387 | 0 | 0 |
| R1 opted out | 387/387 | 0 | 0 |
| R1 enabled | 387/387 | 66 | 1 |
| R2 enabled | 387/387 | 66 | 1 |
| R2 opted out | 387/387 | 0 | 0 |
| R2 unavailable | 387/387 | 0 | 0 |

Each journey verified 128 save/fetch/lexical-search cycles: **2,322 successful
API requests, 2,304 memory operations and zero model calls** across the batch.
Each enabled case spent one 65,536-byte reservation and cleared its lease;
its database was 24 KiB. Fixture content was absent from the queues. All four
cleanup checks passed: isolated profiles removed, collector stopped, temporary
certificate profile removed and production disclosure unchanged. No aggregate
was published.

The main-process comparisons use each replicate's own unavailable baseline;
all nine phases matched. CPU differences below are **profiled observations**,
not causal estimates or acceptance:

| Condition | Maximum matched RSS growth difference | Ending RSS growth difference | Profiled CPU difference, % of one core |
| --- | ---: | ---: | ---: |
| R1 opted out | 1,306,624 bytes | 1,228,800 bytes | 0.375667% |
| R1 enabled | **3,608,576 bytes** | 3,125,248 bytes | 0.295167% |
| R2 enabled | **3,391,488 bytes** | 1,933,312 bytes | 0.307298% |
| R2 opted out | 978,944 bytes | 622,592 bytes | 0.217670% |

Both enabled matched maxima occurred at 32 cycles and exceeded 2 MiB. The lower
R2 ending observation does not replace its above-target matched maximum.

## Decision after the fixed batch

The four observed first SQLite-open windows added **917,504–983,040 bytes of
file-backed residency**; common telemetry-import windows added about
**2.09–2.37 MB of Linux RSS**. The first close did not return those file-backed
pages within its observation window. These windows can overlap other work;
they identify neither a particular mapped file nor SQLite as the sole cause of
the above-target difference. A 24 KiB database is not its runtime's RSS cost.

The stop rule is applied. Next work is a cold initialization and storage-runtime
ownership review of the [service bridge](../../studio/electron/service-bridge.ts)
and [telemetry store](../../studio/electron/telemetry-store.ts), preserving fresh
policy/ACL/generation checks, zero-wait producers and durable spending. No repeat
of the six cases, speculative close-call tuning or numeric budget revision is
selected from this result.

## Limits and remaining acceptance

First-call windows can overlap other application work, so their deltas cannot
be summed or attributed wholly to one component. Instrumentation changes
allocation and timing; profiled CPU is not resource qualification. The first
bootstrap sample follows the probe's own imports and does not measure complete
process startup. Nine phase samples do not capture unsampled peaks. The 100 ms
external sampler and reaped-child counters still provide incomplete process/exit
accounting; reaped CPU is kept separate to avoid double counting. RSS can include
shared pages and allocator retention.

Two counterbalanced triplets cannot prove a universal maximum or stable causal
overhead. The **2 MiB added RSS per participating process and 0.5% of one core**
ceilings remain unchanged and unaccepted. Full pressure/tail-latency, wire,
installed-platform, production ingress/privacy and exact-next-packet acceptance
remain open. All **66 requirement texts and states** are retained; V08 remains
**Building**, with production collection/destination/route **false/null/null**.

## SHA-256 provenance

| Retained evidence | SHA-256 |
| --- | --- |
| Declared attribution plan | `55e76332285446cb486d79437e4f362e09c6f7c40f4e0ab3037d984212d244e1` |
| Focused checks receipt | `67c59dcb71ca4a177a1945c1ed989f2a8b7eb99011fedbe867d9d034ee045658` |
| Offline phase-aligned summary | `c73eba409d27029cf6f99243bd87887f8dfcb5de0058f18e9d168ccea85249e9` |
| Backward-compatible qualification | `d4b1a87475c8003b50843c74b49928543dec20f843e9bf0eab813be878d92fbb` |
| Original workload receipt, unchanged | `2f9a099c118f3d826e46f6e21f64f875b4da1ed09fc3135799ffd1bcf5e8221a` |
| Completed attribution decision | `16d0a678592ed7a17443c921611a9810e188f1a46b70137c8c96a0adeef6c089` |
| Six-case qualification receipt | `840333479057633f4c9979927df05a938694a76f4fcfddb8934e58b47c85c58d` |
| Six-case matched-phase summary | `96b0aee7860fee1ddc60467571b80ec6f4e952ecad216bbb2344ea63cb9ef248` |
| Six-case original workload receipt | `30fdc51ae5a51dcec4bd602e26dfa2b0cb7c872f6e559494c12098979e092920` |
| Completed workflow metadata | `141d1cead67645751ae2840f2120ed21f3ec4877eaa8a70f32b7549d128122d0` |
