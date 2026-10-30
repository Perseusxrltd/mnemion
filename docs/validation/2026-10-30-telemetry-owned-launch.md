# Owned-launch accounting source qualification

30 October 2026. The resource-accounting adapter is diagnostic source. Its first
native run qualifies launch ownership and cleanup on all six targets. It has
not yet measured installed app overhead.
The 8 MiB additional RSS allowance per participating process and 0.5% of one
CPU core remain unaccepted. Production collection stays off.

Grok's original `7a7f5802`, first correction `7b5f5835`, and reviewed correction
`d0425efd` remain separate commits. Astra's review required Darwin's `wait4`
to own direct-child reaping, correct float-second CPU conversion, verified
process-group cleanup after root exit, correct libproc empty/error semantics,
a frozen launch identity, and rejection of actual cleanup failures. Those
source findings are resolved. The 13 focused non-lifecycle checks passed on
Windows; Astra retained the original output and applied formatting with an
unchanged Python AST. No duplicate lifecycle run was used for this review.

The [manual native workflow](../../.github/workflows/telemetry-owned-launch.yml)
runs the self-check once on each of the six existing native targets and retains
its source, launch mode, receipt and errors. It builds no installer or model.
The adapter owns the process group before releasing its child, and the observer
stays outside that group. Failed or missing cleanup prevents qualification.
The intentional invalid-handle exercise remains separate from real cleanup.

Windows uses job accounting that includes exited processes. Linux requires a
disposable delegated cgroup; unavailable support is recorded without claiming
qualification. macOS uses direct-child wait accounting and remains partial for
descendant CPU coverage. Missing counters stay missing. Commit, footprint and
cgroup memory totals are not substituted for RSS.

The native group query is bounded to 64 entries and rejects a full buffer as
incomplete. PID reuse does not replace the original launch identity or authorize
signaling another group. Native receipts are required before attaching this
adapter to an app workload and its fixed counterbalance.
No resource-budget pass follows from these source checks.

## First native run

[Run 41009326091](https://github.com/Perseusxrltd/mnemion/actions/runs/41009326091)
used source `23835d6f1a0f085f82ef9bf68ebfab263eee6f33`. All six original jobs
passed. Each launch receipt records that source and exit code zero; each
lifecycle receipt records ownership held, successful real cleanup, no cleanup
failure, and exercised termination. The Windows invalid-handle exercise is
separate from actual cleanup and did not authorize a retry.

| Target | Lifetime CPU coverage | Retained measurement limits |
| --- | --- | --- |
| Windows x64 | Complete for the owned job | Working-set observations remain sampled. |
| Windows ARM64 | Complete for the owned job | Two short-lived process identities were not sampled. |
| Linux x64 and ARM64 | Complete for the delegated cgroup | `memory.peak` was unavailable; cgroup totals are not substituted for RSS. |
| macOS x64 and ARM64 | Partial | Unreaped descendant CPU and RSS high-water counters remain unavailable. |

Astra reviewed these original artifacts without repeating the self-checks.
They qualify attaching the adapter to the existing 128-cycle workload and fixed
counterbalance, using equivalent ownership capability. They do not qualify app
overhead, the 8 MiB/0.5% budgets, or production collection. The compiled
Linux workload cannot establish installed acceptance on the other targets.

## Compiled-workload attachment

Grok candidate `7751354e` attaches the adapter to the existing Linux compiled
128-cycle workload and six-launch counterbalance. A transient service runs with
the runner's uid, gid, working directory and selected tool/home environment;
its identity probe must return that runner uid. If this capability is unavailable,
the original command runs once and accounting remains explicitly unqualified.
The observer stays outside the controller's owned child group. Phase boundaries
are sampled and descriptive; lifetime CPU is retained separately.

Astra reviewed the source for this one measurement. Five focused source cases
passed before the execution-identity correction; only the changed identity case
was repeated and passed. The installed launcher is not attached by this change,
and the first compiled-workload result below does not establish a resource-budget pass.

## First owned compiled-workload result

[Run 41013901369](https://github.com/Perseusxrltd/mnemion/actions/runs/41013901369)
completed on source `c8f75870ca0c3df1e8bd4af5e4456a403f80bbba`. Its original
provenance/functional qualification binds all 2,351 source files and the fixed
six-case order. Each case completed 128 cycles and 387 successful fixture API
calls: 768 cycles and 2,322 successful calls total. Only the two enabled cases
sent reports, one 25-byte report each (50 bytes total).

All six groups recorded complete Linux cgroup lifetime CPU including exited
descendants, with the observer outside the group. All cleanup passed without
retries or forced group termination. No sampler error, sample truncation or
ledger truncation occurred. The retained cleanup receipt confirms isolated
profiles and certificate removal, collector shutdown and unchanged production
disclosure. Astra reviewed the original evidence; no rerun was requested.

CPU seconds, descriptive only. Group totals include the controller; sampled
Electron CPU covers a different process set and interval.

| Case | Group lifetime CPU | Group active-phase CPU | Sampled Electron CPU |
| --- | ---: | ---: | ---: |
| r1 unavailable | 4.853519 | 1.275025 | 1.090 |
| r1 opted out | 4.865988 | 1.308331 | 1.070 |
| r1 enabled | 5.031845 | 1.406734 | 1.170 |
| r2 enabled | 5.013637 | 1.365476 | 1.180 |
| r2 opted out | 5.070468 | 1.307697 | 1.080 |
| r2 unavailable | 5.060712 | 2.493675 | 1.130 |

Matched RSS growth differences against the unavailable case in the same
replicate, in MiB. Each cell is maximum matched difference / final checkpoint
difference. All nine checkpoints matched; maxima include the zero initial
difference. These are sampled growth differences, not causal allocations or
unsampled peaks.

| Case | Main RSS difference | Renderer RSS difference |
| --- | ---: | ---: |
| r1 opted out | +0.297 / -0.367 | +0.637 / +0.637 |
| r1 enabled | +3.270 / +3.270 | +0.754 / +0.648 |
| r2 enabled | +5.660 / +5.660 | 0.000 / -5.512 |
| r2 opted out | +0.277 / +0.188 | 0.000 / -6.594 |

Phase boundaries are polled. Every owned accounting report ends with a recorded
canonical count of 96 because the transient 128-cycle marker was overwritten
before observation; the separate functional receipt proves 128 completed
cycles per case. Four cases also miss the `finished` marker and classify the
interval until `closed` as active. Native attachment should carry actual
cumulative counts in terminal markers rather than infer missing counts. These
limitations do not invalidate the retained lifetime counter or functional result.

The r2-unavailable connection phases account for 1.415371 CPU seconds versus
0.209794 in r1, while its startup phase falls from 2.015347 to 1.274261 seconds.
The active-total difference does not establish a saving or causal overhead.
Linux `cgroup_memory_peak_bytes` and lifetime identity count remain unavailable;
per-process kernel high-water covers observed live processes, not unseen exited
processes. Missing values remain null, and overall coverage remains partial.

This is Linux x64 compiled-source evidence only. It does not qualify installed
or all-platform resource behavior, the 8 MiB/0.5% budgets, or production
collection. All prior failures and their original results remain unchanged.
