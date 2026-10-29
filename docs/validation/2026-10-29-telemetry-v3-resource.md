# Phase-memory resource comparison — 29 October 2026

Run **40967691671** on source `1adc472af8874ccdb261f7532eeab0463d888a40`
completed six functional Linux compiled-Electron cases. Each case matched
**2,301** source inputs, ran **128** memory cycles and **384** real fixture
memory operations, and made **387/387** successful API requests. Electron
**44.9.3**, Node **24.22.0**, x64, not an installed package. Both enabled
cases accepted one **25-byte** `/v3/report` body, one **65,536-byte**
reservation, **65** accepted writes and **106** snapshots. Unavailable and
opted-out cases sent no report. Cleanup is all true. This is not installed
resource qualification. `resource_acceptance` stays false.

The first private verifier failed because it required comparison and
attribution fields on a schema-3 summary. Those flags belong on the source
and combined receipt. Source and artifacts were not changed. The corrected
checker passed **13** real-schema positive and negative checks. That original
verifier failure is retained. Run **40965218896** remains failed before any
measurement.

## Four comparisons

Matched RSS is enabled or opted-out growth minus the paired unavailable case.
The 2 MiB ceiling applies to each participating process. **2,097,152** bytes
is 2 MiB. Main and renderer observations remain unaccepted.

| Comparison | Main maximum | Where | First-delivery VmRSS | First-delivery file / anonymous |
| --- | --- | --- | --- | --- |
| r1-enabled | 5,271,552 | 96 cycles | 2,719,744 | 1,589,248 / 1,130,496 |
| r2-enabled | 2,887,680 | first delivery | 2,936,832 | 1,523,712 / 1,413,120 |
| r1-opted_out | 10,330,112 | 128 cycles only | −282,624 | −196,608 / −86,016 |
| r2-opted_out | 69,632 | 96 cycles | −143,360 | −131,072 / −12,288 |

Both enabled maxima are above 2 MiB. From the first delivery through the last
checkpoint, enabled file-backed RSS stays about 1.5–1.9 MiB in both repeats.
Opted-out file-backed differences stay negative. That split does not name a
library or a callsite.

Anonymous RSS and V8 `used_heap_size` do not move together. On r1-enabled at
96 cycles, anonymous growth is 3,424,256 bytes and `total_heap_size` growth is
3,043,328, while `used_heap_size` growth is 713,916. By 128 cycles that case's
VmRSS difference is 1,667,072 and anonymous growth is −53,248, while VmHWM
remains high. r2-enabled does not repeat the 96-cycle spike; its 96-cycle
VmRSS difference is −921,600. The r1-opted-out 10,330,112-byte maximum is the
final checkpoint only. Its earlier main phases range from −245,760 to 147,456
bytes, and its final VmHWM difference is −507,904. r2-opted-out never shows
that jump. Those single checkpoints are variance and garbage-collection
ambiguity, not a steady cost and not a reason to drop a sample.

r2-enabled renderer maximum is 2,314,240 bytes at 64 cycles, also above 2 MiB.
The other renderer maxima are 634,880, 45,056 and 1,933,312 bytes. GPU maxima
are 458,752 and 602,112 bytes for the enabled cases.

Instrumented one-core CPU differences are 1.0455147417578587% and
0.6922571042885327% for the enabled cases, and about 0.07% for both opted-out
cases. This run cannot pass the 0.5% ceiling. CPU stays descriptive.

## No source change

`telemetry-store.ts` already loads `node:sqlite` only for an active disclosed
measurement, sets `mmap_size` to 0, and closes each transaction. Opted-out
still opens that path once before its negative cache. The wire encoder and
the catalog read are already cached. Nothing in these counters identifies an
avoidable allocation that can be removed without guessing a mapped file or
weakening policy freshness, final-send gates, review bytes, cancellation,
trust, storage, cadence or the 19 metric meanings. No runtime file was edited.
No regression suite was run for a change that was not made.

## Next measurement

Do not repeat this phase-memory workload yet. In the existing CLI and
workflow, comparison and attribution are mutually exclusive journeys, and
phase memory cannot be combined with attribution. The planned next
measurement is a separate `--attribution` diagnostic on this same source:
comparison false, phase memory false, the existing fixed six-case order, and
no new sampler. Read the existing before/after first-use captures for SQLite,
reservation and transport: `sqlite.open` before and after, `delivery.reserve`
before and after, and `transport.before_connect` with `transport.after_close`.
Those captures record main-process Linux counters only when the method runs.
Compare windows and paired controls inside that same attribution run. This
phase-memory run is context only. Do not subtract samples across different
runs. Do not add smaps, heap dumps, a process, or a timer. Do not treat the
file-backed plateau as a named subsystem until that boundary is measured.

V08 remains Building. Collection, destination and route stay false/null/null.
All 66 requirements remain. The 2 MiB and 0.5% gates stay unaccepted.
