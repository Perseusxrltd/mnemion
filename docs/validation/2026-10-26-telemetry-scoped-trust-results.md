# Scoped-trust resource result — 26 October 2026

The fixed [resource run 40386632526](https://github.com/Perseusxrltd/mnemion/actions/runs/40386632526)
completed all six functional cases at source
`4b8e8a3e407970c271600be803e387b0143a70c7`. Each case matched **2,053 reviewed
source files**. The source app was unpackaged Linux x64, Electron 44.9.3 / Node
24.22.0. These results do not qualify installed platforms or production privacy.

**The unchanged 2 MiB resource gate still fails.** Enabled main-process matched
maxima were **4,341,760 / 3,428,352 bytes**, with endings of
**2,625,536 / 3,215,360 bytes**. No repeat measurement is selected.

## Retained comparisons

The two fixed triplets ran unavailable/opted-out/enabled, then
enabled/opted-out/unavailable. Each comparison below uses its own triplet's
unavailable baseline; all recorded phases matched. Cells show **matched maximum
/ ending RSS differences in bytes**. `Browser` is the Electron main process;
`Tab` is the renderer. All roles and both opted-out controls are retained.

| Comparison | Main / Browser | Renderer / Tab | GPU | Utility |
| --- | --- | --- | --- | --- |
| r1 opted-out | 1,888,256 / 1,400,832 | 4,145,152 / 77,824 | 245,760 / 229,376 | 303,104 / 303,104 |
| r1 enabled | 4,341,760 / 2,625,536 | 0 / -4,505,600 | 0 / -1,671,168 | 200,704 / 131,072 |
| r2 enabled | 3,428,352 / 3,215,360 | 495,616 / 253,952 | 2,981,888 / 2,859,008 | 167,936 / 4,096 |
| r2 opted-out | 1,486,848 / 368,640 | 458,752 / 458,752 | 3,645,440 / 3,633,152 | 372,736 / 372,736 |

Combined Electron CPU differences, normalized to each baseline's elapsed time,
were respectively **0.165100%, 0.436336%, 0.314023% and 0.116305% of one core**.
These describe this profiled workload, not stable overhead or per-process CPU
acceptance. The **0.5%** limit remains unchanged. Negative RSS differences do
not establish savings. Shared-page accounting, overlapping attribution work
and 100 ms external sampling also limit interpretation and can miss short-lived
helpers; matched maxima and endings are distinct from unsampled peaks.

## Evidence and limits

The closed authoritative summary is `resource-followup-result.json` in the
private `2026-10-26-telemetry-scoped-trust` evidence set. It identifies the
original `resource-diagnostic/retained/qualification.receipt.json`, SHA-256
`60bf6c684ac2893bcee573257553510ebb71658e2d45a22d74c5786da6bfa9b4`, and the
retained original artifacts beside it. Cleanup passed: isolated profiles and
the certificate profile were removed, the collector stopped, and the production
disclosure was unchanged.

Ambient fixture trust differed across source revisions. Comparing this run
with the [earlier allocation result](2026-10-26-telemetry-allocation-followup.md)
cannot isolate a causal effect of scoped trust. That earlier failure, all its
controls and the rejected SQLite experiments remain retained. The
[source trust qualification](2026-10-26-telemetry-scoped-trust.md) established its
bounded trust behavior, not a resource saving; this completed follow-up does
not establish one either.

All 66 requirement texts and states remain unchanged. V08 stays Building,
collection is unavailable, destination and route address are null, and the
release authority list is empty. There is no CPU, resource, installed-platform,
provider/privacy or full V08 acceptance. No outcome from a separate report-review
journey is credited here.
