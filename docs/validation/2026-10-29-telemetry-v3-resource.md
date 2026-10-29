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

## Attribution run 40971963055 failed

Run **40971963055** on source `401c102304f951ebc1baec958831dc102a028b21` completed
all six fixed cases and correctly failed the journey. It is not a pass and not
an overhead result. Both enabled cases made **zero** reservations and **zero**
collector reports. Accepted writes were 65, snapshots 106, and memory cycles
128. Each case had 387/387 successful fixture API calls. The four
unavailable and opted-out controls completed. Setup replies were enabled,
unmetered, disclosure acknowledged, and storage ready. Allocation errors were
empty. Cleanup was true. Production collection stayed off.

Both enabled call maps were `sqlite.open=133`, `sqlite.close=134`,
`conditions.prepare=1`, `network_cost.start=1`, `delivery.reserve=1`, with no
`transport.socket`. The prepare windows were 259.845 ms and 258.973 ms. The
reserve windows were 0.849 ms and 0.715 ms. `closeDatabase` returns immediately
when it has no connection, but the attribution wrapper still counts that call.
Aggregate open/close counts and these sub-millisecond windows do not
conclusively prove the exact reserve guard. The clock bound can change after
`eligible`, and a caught exception is still possible. The evidence points to
the pre-database checks. The exact refusal is not yet recorded. Cohort
selection and `reviewedDesktopRelease` run only after `open(true)`; these
counts do not record those later checks as the cause.

`eligible` had already passed the same stamp and clock bound on the way into
`prepare`. That bound can change before `reserve`. The first CPU sample has no
prior reading, so `prepare` takes its existing 250 ms delta even when the
machine is idle. That delay does not identify a busy CPU, a SQLite failure, or
a mapped library. `prepare` still returns true when the second reading remains
constrained. `reserve` then uses the live `read()` already installed as its
environment. The `{ network: 'unknown', constrained: true }` argument is not
the decision when that reader exists. Which clause refused the reservation was
not retained.

The source change can record that clause on the same `read()` when the owned
attribution probe sets `traceAdmission` before the call. Ordinary reads leave
the guard unset: they do not allocate it or store a reason. The probe does not
read the gauges again, does not change the returned network or constrained bit,
and does not change reserve, budgets, permissions, or retry timing. It copies
`admissionGuard` only while the first `delivery.reserve` is inside that read,
into `allocation.reserve_guard`. A null `reserve_guard` is the absence of a
captured first-read diagnostic, not proof of an exact earlier branch. This
diagnostic has not established the cause. It is not live qualification.
`resource_acceptance` stays false.

The reviewed follow-up passed the normal Electron build, including its real
native helper, and **20 focused admission/network checks** on Linux x64 with
Node 22.22.0. The checks cover the fixed diagnostic fields, single gauge reads,
ordinary reads without a guard object, sensor order and short-circuit behavior,
CPU sample comparability, metering, cancellation and native clock boundaries.
There were no failures or skips. The new guard checks are registered in the
normal Electron test command. No app journey or resource result is claimed by
these component checks.

The next bounded action is one attribution journey on this source. Read
`allocation.reserve_guard.reason` for both enabled cases. Do not rerun the
phase-memory matrix and do not reclassify run 40971963055.
