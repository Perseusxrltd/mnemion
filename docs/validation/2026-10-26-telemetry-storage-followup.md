# Telemetry storage follow-up — 26 October 2026

The fixed six-launch [run 40290150459](https://github.com/Perseusxrltd/mnemion/actions/runs/40290150459)
completed successfully on source
[`de53ba4609f848f7e91fdc9a8383ded9fb70884f`](https://github.com/Perseusxrltd/mnemion/commit/de53ba4609f848f7e91fdc9a8383ded9fb70884f).
Retained-artifact qualification completed at **08:18:44 UTC**, matching all
**1,998 reviewed files in each of six functional journeys**. **Resource acceptance
remains false:** both enabled main-process matched maxima and ending differences
exceeded the unchanged 2 MiB target. The next step is an explicit architecture
review, without another benchmark run or a budget revision.

## Fixed plan and functional result

The plan was recorded at **08:07:49 UTC**, after the
[storage-slot correction](2026-10-26-telemetry-storage-slot.md) demonstrated one
live SQLite handle instead of 32 in its separate concurrent-call diagnostic.
The follow-up retained the existing compiled-app
[runner](../../deploy/probe_telemetry_renderer.py),
[Electron probe](../../studio/electron/scripts/probe-telemetry-renderer.mjs) and
[analyzer](../../deploy/report_telemetry_renderer.py). It allowed exactly two
counterbalanced triplets, with 128 save/fetch/lexical-search cycles per launch,
no forced garbage collection, idle padding or replacement of pressure/consent
checks. Every original outcome is retained in the declared order:

| Launch | Successful fixture API requests | Accepted local writes | Accepted four-byte TLS reports |
| --- | ---: | ---: | ---: |
| R1 unavailable | 387/387 | 0 | 0 |
| R1 opted out | 387/387 | 0 | 0 |
| R1 enabled | 387/387 | 66 | 1 |
| R2 enabled | 387/387 | 66 | 1 |
| R2 opted out | 387/387 | 0 | 0 |
| R2 unavailable | 387/387 | 0 | 0 |

The six journeys completed **2,322 successful API requests and 2,304 memory
operations**, with **zero model calls**. They used actual compiled source-app
renderer/IPC paths, Electron **44.9.3 / Node 24.22.0 on Linux x64**, disposable
memory fixtures and a local TLS collector. Each enabled case retained nine queue
cells and cleared its delivery lease. Fixture content was absent from the queues.
No aggregate was published. All four cleanup checks passed: isolated profiles
removed, collector stopped, temporary certificate profile removed and production
disclosure unchanged.

## Resource observations

Each comparison uses its own replicate's unavailable baseline and all nine
matched phases. Electron's `Browser` role is its main process; `Tab` is the
renderer. The CPU column describes the observed Electron-process difference over
the baseline interval, not CPU attributable solely to telemetry.

| Condition | Main maximum matched RSS growth difference | Main ending RSS growth difference | Profiled CPU difference, % of one core |
| --- | ---: | ---: | ---: |
| R1 opted out | 8,495,104 bytes | 385,024 bytes | −0.036066% |
| R1 enabled | **3,121,152 bytes** | **2,125,824 bytes** | 0.228418% |
| R2 enabled | **3,235,840 bytes** | **2,207,744 bytes** | 0.317356% |
| R2 opted out | 1,048,576 bytes | 815,104 bytes | 0.047016% |

Both enabled main maxima occurred at 32 cycles. The original summary also retains
all GPU and renderer outcomes, including **9,035,776 bytes** of matched GPU
difference in R1 opted out and **10,276,864 bytes** of matched renderer difference
in R2 enabled. Negative differences and variation between roles/runs are not
memory savings or telemetry accelerating the application.

The [earlier attribution run](2026-10-26-telemetry-attribution.md) and its original
failures and observations remain intact. This follow-up compares current source
against current-source unavailable baselines. CPU admission, review clocks and
controls, wire format and helper ownership also changed since that earlier
source; the comparison does not isolate a causal storage-slot improvement.

## Limits and decision

This is compiled source-app and retained-artifact qualification, not an installed
native matrix or an independent rebuild. Phase-matched maxima, differences of
per-run maxima and ending growth are distinct observations; none captures every
peak. First-call instrumentation can overlap other work and perturb timing and
allocation. The 100 ms external sampler can miss short-lived helpers, sampled
CPU accounting is incomplete, and RSS sums can count shared pages repeatedly.
Two triplets do not establish stable causal overhead or a universal maximum.

All six outcomes are retained under the fixed stop rule. Further work is an
explicit review of cold initialization and storage/runtime ownership, preserving
fresh policy/permission checks and nonwaiting coordination. No repeat benchmark,
small tuning loop or budget increase is selected from these results. The
**2 MiB added RSS per participating process / 0.5% of one core** gates remain
unchanged and unaccepted, as do full platform, wire, privacy and utility gates.
V08 remains **Building**; all **66 requirement texts and states** are unchanged.
Production collection/destination/route remain **false/null/null**.

## Original SHA-256 evidence

The qualification receipt binds the original source, workload, summary and cleanup
files. The summary's input digest matches the retained workload receipt; no raw
logs, private paths or application content are published here.

| Original evidence | SHA-256 |
| --- | --- |
| Declared plan | `5e5b2870bd347cae6ee02e1987e962fcb0333845c72261d0f3e4343f4b6abf47` |
| Retained qualification receipt | `eb276b571d8f50f7d14f0870f55d20c5f3eb71d9d62a13de3ce785bf4f68812f` |
| Reviewed source inventory digest | `dffc9304adc0950ac640932922598394ef5daac7648fe619eafc8fd4b24acfe4` |
| Original source receipt | `8d1019c428e60900ae0dade926d6173ea72c08d0c8ad49d022117342cfba6296` |
| Original workload receipt | `c3c129e626530880f8c31baa9f0a398414d13d22933173f54da0320588f0b74c` |
| Original resource summary | `2528c3944544bd24c39a1dacee8dbc2c7313c6d4b3cc5d77aebcfb851fb4def5` |
| Original cleanup receipt | `1dfdad0691c70f0fcdaad9a0e56f94675038eaccb5de8e0393914569586d75a1` |
