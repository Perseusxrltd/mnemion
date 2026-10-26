# Fixed allocation resource follow-up

**26 October 2026: six functional cases completed; resource acceptance fails.**
The predeclared [diagnostic run 40372901181](https://github.com/Perseusxrltd/mnemion/actions/runs/40372901181)
used source `4779cf11fa1b090f8ff7c0430558626c53617d36`. Every case matched
**2,045 reviewed source files**. The source-built, unpackaged app used Electron
44.9.3/Node 24.22.0 on Linux x64; this is not an installed-platform qualification.

## All six cases retained

Two counterbalanced triplets ran unavailable, opted-out and enabled conditions.
Each completed 387 successful fixture API requests and 384 memory operations:
**2,322 successful requests and 2,304 operations in total, with no model calls**.
Only disposable enabled copies could report to the fixture collector.

| Original case | Successful API requests | Receipt `accepted_writes` | Fixture reports / body bytes |
| --- | ---: | ---: | ---: |
| r1-unavailable | 387 | 0 | 0 / 0 |
| r1-opted_out | 387 | 0 | 0 / 0 |
| r1-enabled | 387 | 65 | 1 / 4 |
| r2-enabled | 387 | 65 | 1 / 4 |
| r2-opted_out | 387 | 0 | 0 / 0 |
| r2-unavailable | 387 | 0 | 0 / 0 |

Unavailable cases took no workflow snapshots; opted-out cases took 127 and
enabled cases 175. The enabled producer count remained capped at 64, separate
from the receipt's total accepted writes. All leases cleared. Isolated profiles
and certificate state were removed, the collector stopped and production
disclosure stayed unchanged. These fixture results do not qualify provider logs,
whole-wire traffic or production delivery.

## Matched resource differences

All values below compare each condition with its own replicate's unavailable
baseline. RSS values are bytes. Electron's `Browser` role is the main process;
`Tab` is the renderer. Maxima are the maximum differences at matched sampled
phases, not differences between independently sampled peaks.

| Condition | Main matched maximum | Main ending | Renderer matched maximum | GPU matched maximum | Utility matched maximum | Combined CPU difference, % of one core |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| r1-opted_out | 1,175,552 | 446,464 | 200,704 | 356,352 | 81,920 | 0.203 |
| r1-enabled | 3,145,728 | 2,768,896 | 876,544 | 1,351,680 | 0 | 0.537 |
| r2-enabled | 3,186,688 | 2,428,928 | 9,150,464 | 5,615,616 | 180,224 | 0.198 |
| r2-opted_out | 1,896,448 | 1,024,000 | 8,183,808 | 5,423,104 | 98,304 | -0.023 |

Both enabled main maxima and endings exceed the unchanged **2,097,152-byte
(2 MiB)** ceiling. The combined Electron CPU differences are descriptive and
normalized to baseline elapsed time; they are not per-process profiled CPU or
stable acceptance against the unchanged **0.5% of one core** gate. A lower value
in one replicate cannot establish a pass. Negative differences reflect variation,
not demonstrated savings.

The original receipt retains every role's endings and sampled peaks, both
opted-out comparisons, phase data and first-call attribution. Shared pages,
overlapping initialization, attribution instrumentation and 100 ms external
sampling limit causal interpretation; short-lived helpers can be missed.

## Decision and evidence

The [transaction metadata change](2026-10-26-telemetry-query-ownership.md) retains
its demonstrated reduction in statement wrappers and returned row objects.
This follow-up does **not** establish causal RSS/CPU savings or resource
compliance. The one declared workload is complete; no replay or budget revision
is selected. Further performance work needs an evidence-supported initialization
or storage/runtime decision using the retained attribution first.

The earlier [storage follow-up](2026-10-26-telemetry-storage-followup.md),
[initial attribution](2026-10-26-telemetry-attribution.md) and
[rejected private SQLite experiment](2026-10-26-telemetry-private-sqlite.md)
retain their original outcomes. No earlier failure or unfavorable phase is
replaced by this result.

`allocation-followup-decision.json` records the stop and remaining gates.
The retained `qualification.receipt.json` binds all six originals; SHA-256:
`03c2491e7e885f6a13bb2e2f7ea7650e47ccbc1089ce46c4fb4cd127f3813f91`.
The matched source-inventory digest is
`7e36c0e130926e373cb57c6f8aaf3a1cdb83cca05b0fbcbbd843e2b60c6a9f59`.

All 66 requirement states remain unchanged. V08 stays **Building**, with
collection/destination/route **false/null/null**. Resource, provider/ingress
privacy, whole-wire and installed-platform acceptance remain open.
