# Telemetry resource process-role controls — 27 October 2026

This source follow-up, prepared on base
`0dd5999652236ceeda7e7acd753c29c5cc2bf5c5`, corrects diagnostic controls.
Focused checks passed. The selected comparison, run **40453953300** on source
`6ac7700312e9c77a9793cd6e740419f1b39e2c5e`, completed all six functional cases.
**Resource acceptance remains false.**

## Retained finding

The [original metadata-allocation diagnostic](2026-10-27-telemetry-metadata-allocation-results.md),
run `40416923461` on source `192b0df98644b845fd3117516ec9d42c4167acfa`,
recorded two Electron `Tab` processes in `r1-enabled` and one in every other
case. Their exact identities were not recorded. The old probe requested
DevTools closure without waiting for its lifecycle to finish, but this does
not establish that the second process was DevTools or explain the observed
resource differences.

All six original cases, ambiguous renderer comparison and failed resource
qualification remain retained. Profiled observations establish neither a
causal regression nor production-only telemetry overhead.

## Diagnostic changes

- [Development startup](../../studio/electron/application.ts) honors
  `MNEMION_STUDIO_DEVTOOLS=0` before opening DevTools. The diagnostic sets this
  explicitly; normal packaged startup is unchanged.
- The [app probe](../../studio/electron/scripts/probe-telemetry-renderer.mjs)
  matches the app window's OS process ID to Electron's single `Tab` process in
  every sample. Missing or extra renderers, additional windows or open DevTools
  reject the sample. Numeric web-content process mappings and fixed content types
  remain in failed samples for investigation, without recording their titles or
  URLs. Other process roles remain recorded.
- The [report reader](../../deploy/report_telemetry_renderer.py) independently
  checks those numeric identities against process rows and requires stable
  app main/renderer identities across comparison samples. It retains transient
  processes that appear only between the first and last samples, makes incomplete
  CPU accounting explicit, and reports CPU differences for each comparable role.
- The [existing probe](../../deploy/probe_telemetry_renderer.py) adds a separate
  `--comparison` mode without allocation attribution. It retains 128 real
  memory cycles per case, in the fixed order `r1-unavailable`, `r1-opted_out`,
  `r1-enabled`, `r2-enabled`, `r2-opted_out`, `r2-unavailable`. Each comparison
  uses its own triplet's unavailable baseline. Process sampling remains active;
  allocation attribution is a separate, mutually exclusive mode.

The report regression selection passed **15 tests**. A separate private
verification selection passed one valid case and rejected eight invalid cases,
including an extra/replaced renderer, debugger, missing ownership or phase,
extra window, boolean PID and enabled allocation attribution. Re-reading the
original six-case artifact preserved every earlier result and comparison.
The Electron build, Python lint and Node probe syntax checks passed.

## Completed comparison

The original workflow succeeded, with no automatic retry. Each case used the
unpackaged Linux x64 app, Electron **44.9.3** / Node **24.22.0**, and matched
all **2,114 reviewed source files**. Each retained 118 built inputs and 602
frontend assets. The six 128-cycle journeys completed **387/387 successful
fixture API requests each**, **2,322 total**. Each enabled case delivered one
accepted four-byte report; unavailable and opted-out cases delivered none.
Forbidden metadata was absent, all leases cleared and fixture cleanup passed.

All six cases verified stable app main/renderer identities with no extra
renderer or debugger in their samples. Allocation attribution was disabled;
there was no forced GC, warmup, idle padding or reduced workload. No persistent
SQLite handle or positive permission cache was introduced.

The table compares growth against the unavailable case in the same triplet.
Maximum means the largest difference at a matched sampled phase; ending means
the difference at the final 128-cycle phase. CPU deltas use the corresponding
unavailable case's elapsed time and are descriptive percentages of one core.

| Case | Process | Maximum matched RSS difference (bytes) | Ending RSS difference (bytes) | CPU delta (%) |
| --- | --- | ---: | ---: | ---: |
| r1-opted_out | App main | 1,585,152 | 1,449,984 | 0.0474 |
| r1-opted_out | App renderer | 5,111,808 | 4,247,552 | 0.0474 |
| r1-enabled | App main | 3,579,904 | 3,342,336 | 0.2727 |
| r1-enabled | App renderer | 5,664,768 | 4,866,048 | 0.0474 |
| r2-enabled | App main | 3,366,912 | 2,490,368 | 0.2909 |
| r2-enabled | App renderer | 5,193,728 | 4,874,240 | 0.1047 |
| r2-opted_out | App main | 1,605,632 | 323,584 | 0.0465 |
| r2-opted_out | App renderer | 5,136,384 | 5,136,384 | 0.0582 |

Both enabled main comparisons and all four renderer comparisons exceed
**2,097,152 bytes** at matched phases. GPU, utility and external-process
observations remain in the retained receipt. Working-set sums double-count
shared pages; these sampled maxima are neither unsampled peaks nor differences
of per-run maxima. CPU comparisons cover comparable processes, with external
helpers sampled separately. The 100 ms sampling can miss short-lived children.
Negative differences are variance, not savings. These observations establish
no causal improvement, regression or production-only telemetry overhead.

Evidence bindings: source inventory SHA-256
`2fb4d65a4082ba147c0cef893f34c8733b578fb1d7ac8093618e1bde27f8d891`;
retained qualification receipt SHA-256
`e9ba9c1072008372485072bc37fe3a51cf57a208c9683747f946688d844e16b9`;
original artifact archive SHA-256
`d06a10c11525281fa69fa6702bc254cb3c1d50a21b61fcbfb10145bcf3ea1e0b`.
No new resource run is selected.

The **2 MiB added RSS / 0.5% of one core** ceilings remain unchanged. This
comparison provides no general CPU, resource, installed-platform or
provider/privacy acceptance. All 66 requirements and their states remain
unchanged; V08 is **Building**, production collection is `false`, destination
and route are `null`, and release certificate authorities remain empty.
