# Metadata-allocation resource result — 27 October 2026

The original [4.46.32 diagnostic run 40416923461](https://github.com/Perseusxrltd/mnemion/actions/runs/40416923461)
completed successfully at source `192b0df98644b845fd3117516ec9d42c4167acfa`.
All six functional cases matched **2,075 reviewed source inputs**. The app was
unpackaged Linux x64, Electron 44.9.3 / Node 24.22.0. These are profiled
diagnostics; **resource acceptance remains false**.

Enabled main-process matched maxima were **9,261,056 / 2,936,832 bytes**;
ending matched-phase differences were **9,261,056 / 1,593,344 bytes**. Both
maxima exceed the unchanged **2 MiB** ceiling. The second ending alone does not
qualify the workload. No new resource run or budget change is selected.

## Both orders and all roles

The fixed orders were unavailable/opted-out/enabled, then
enabled/opted-out/unavailable. Each comparison uses its own triplet's unavailable
baseline. Cells show **maximum / ending matched-phase RSS growth differences
in bytes**; the ending phase is `128_memory_cycles`. `Browser` is the Electron
main process and `Tab` its renderer. Every reported role matched all recorded
phases. The first enabled renderer has an ambiguous initial `Tab` role, so the
qualifier supplies no matched comparison for it.

| Comparison | Main / Browser | Renderer / Tab | GPU | Utility |
| --- | --- | --- | --- | --- |
| r1 opted-out | 2,711,552 / 2,711,552 | 2,805,760 / 2,031,616 | 3,805,184 / 3,805,184 | 188,416 / 32,768 |
| r1 enabled | 9,261,056 / 9,261,056 | Unavailable: ambiguous initial role | 6,250,496 / -901,120 | 716,800 / 618,496 |
| r2 enabled | 2,936,832 / 1,593,344 | 4,116,480 / 4,116,480 | 2,592,768 / 2,592,768 | 131,072 / -86,016 |
| r2 opted-out | 1,388,544 / 684,032 | 4,472,832 / 3,940,352 | 2,539,520 / 2,441,216 | 118,784 / -196,608 |

Combined Electron CPU differences, normalized to the corresponding baseline's
elapsed time, were respectively **0.093325%, 2.741420%, 0.419155% and 0.186291%
of one core**. These are descriptive profiled observations, not per-process CPU
qualification; the **0.5%** ceiling is unchanged. Attribution can perturb
allocation and timing, overlapping first-call windows cannot isolate costs,
shared pages can be counted more than once, and 100 ms sampling can miss brief
helper processes. Matched maxima differ from differences of run maxima and from
unsampled peaks. Negative differences establish no saving. The observations
cannot establish that the metadata correction caused a regression or assign
all measured memory to production telemetry overhead.

## Functional evidence and remaining limits

Each case completed **128 memory cycles** with verified results and **387
successful fixture HTTP requests**. Each enabled case accepted one four-byte
report; unavailable and opted-out cases sent none. Forbidden metadata and model
calls were zero. All leases cleared; isolated profiles and the certificate
profile were removed, the collector stopped and production disclosure remained
unchanged.

The private `2026-10-26-telemetry-metadata-allocation` evidence set retains the
original workload receipt, summary, archive and watch result. The authoritative
`qualification.receipt.json` has SHA-256
`d70db8d88d1a274765695e93b6ffb7b7f725e60f12e9c041137a269c906050f5`.
The [source correctness results](2026-10-26-telemetry-metadata-allocation.md),
original 5/3/130 operation-count failures, earlier resource failures and rejected
experiments remain retained. No RSS/CPU saving, installed-platform,
provider/privacy or full V08 acceptance follows from this workflow success.
All 66 requirement texts and states remain unchanged. V08 stays Building;
collection/destination/route remain **false/null/null**, with release CAs empty.
