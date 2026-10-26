# Telemetry attribution diagnostic preparation

**Source checkpoint, 26 October 2026.** The existing renderer probe now has an
optional six-launch attribution mode. **It has not been dispatched or run.**
Completed evidence consists of focused report checks, compatibility with retained
artifacts and offline reanalysis of an earlier workload. Frozen 4.46.13 is
separate and unchanged by this diagnostic work; none of these results qualifies
that release or activates production telemetry.

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

## Completed checks and offline findings

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
