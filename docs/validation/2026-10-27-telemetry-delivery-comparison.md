# Desktop delivery comparison: resource gate still fails — 27 October 2026

[Run 40483350394](https://github.com/Perseusxrltd/mnemion/actions/runs/40483350394)
on source `29dcd70d79b763e274731a94a9b2948603df5250` completed successfully;
the retained qualifier exited **0**. This is the declared comparison after the
[native delivery-opportunity correction](2026-10-27-telemetry-delivery-opportunity.md),
using the unpackaged Linux x64 app, **Electron 44.9.3 / Node 24.22.0**, without
allocation attribution. It predates the
[browser/Python owner follow-up](2026-10-27-telemetry-owner-saturation.md).

All six cases completed **128 memory cycles and 387/387 successful fixture API
requests each**. Each matched **2,143 source files**, verified the actual app
process roles and native setup controls, and recorded no page errors. All six
functional journeys completed:

| Case, in original order | Accepted telemetry writes | Reserved attempts | Accepted reports / body bytes |
| --- | ---: | ---: | --- |
| r1-unavailable | 0 | 0 | 0 / 0 |
| r1-opted_out | 0 | 0 | 0 / 0 |
| r1-enabled | 65 | 1 | 1 / 4 |
| r2-enabled | 65 | 1 | 1 / 4 |
| r2-opted_out | 0 | 0 | 0 / 0 |
| r2-unavailable | 0 | 0 | 0 / 0 |

Each enabled reservation charged 65,536 bytes; that allowance is not measured
wire traffic. No forbidden collector metadata was observed. All leases cleared;
isolated profiles and certificate fixtures were removed, the collector stopped,
and production disclosure remained unchanged.

## Resource observations

The table shows **RSS growth differences in bytes** from the same-round
unavailable case, at matched work phases. Endings are the matched 128-cycle
phase; maxima are sampled phase maxima, not unsampled peaks or causal telemetry
allocations. The retained evidence also includes the other process roles.

| Case | App role | Maximum matched difference | Ending difference |
| --- | --- | ---: | ---: |
| r1-opted_out | Main | 2,723,840 | 1,040,384 |
| r1-opted_out | Renderer | 4,435,968 | −143,360 |
| r1-enabled | Main | 3,768,320 | 2,039,808 |
| r1-enabled | Renderer | 4,833,280 | −602,112 |
| r2-enabled | Main | 3,129,344 | 2,625,536 |
| r2-enabled | Renderer | 1,032,192 | 118,784 |
| r2-opted_out | Main | 1,785,856 | 1,245,184 |
| r2-opted_out | Renderer | 380,928 | 90,112 |

Both enabled main-process maxima exceed **2,097,152 bytes (2 MiB)**, as do three
other listed maxima. **Resource acceptance remains false.** Combined Electron
CPU deltas were 0.1799%, 0.3598%, 0.2230% and 0.0469% of one core respectively
for r1-opted_out, r1-enabled, r2-enabled and r2-opted_out. These window observations
do not establish general CPU qualification, resource savings or production-only
overhead. The **2 MiB per participating process / 0.5% of one core** ceilings
remain unchanged.

The retained qualification receipt has SHA-256
`43281461ce7011609bb181e0f6d12e1f2bf81067f0af581dbfeef6fb273a2230`;
the original archive has SHA-256
`6807e0cbd4070ae85446b7c3aa9cfb6fb3f4ed1230bc5f82912b215d13ffc441`.
[Original run 40477197149](2026-10-27-telemetry-catalog-comparison.md) remains
failed and its exact cause unproved; this changed-source comparison does not
rewrite or retry that run. No further app comparison is selected.

This is scoped source-app evidence, not current browser/Python, installed
cross-platform, full-wire, provider/privacy or aggregate acceptance. No release
or production activation is established. All 66 requirement states remain;
V08 is **Building**, collection/destination/route **false/null/null**, with empty
release CAs. The [acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md)
retains the full remaining gates and all prior failed evidence.
