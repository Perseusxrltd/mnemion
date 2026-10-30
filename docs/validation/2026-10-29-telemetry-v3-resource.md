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

## Attribution run 40976743563 completed

That journey has now completed on source
`7ee617691ead16c17bbdb9eb797e03f20f186325`. Run **40976743563**, artifact
digest `27d52409226332746627e7f345a2f3d00afc0106025dd257ea4c0e2d81796531`,
finished all six source-bound compiled Linux cases. Electron **44.9.3**, Node
**24.22.0**, x64, `packaged: false`. Each case matched **2,309** reviewed
source files and **387/387** fixture API calls. Attribution was on. Comparison
and phase memory were off. This section does not subtract run 40967691671 or
reclassify run 40971963055. The admission trace still has no production
behavior change.

Both enabled cases were `reason: allowed` with `network: unknown` and
`constrained: false`. Each accepted one **25-byte** `/v3/report`, reserved
**65,536** bytes, cleared its lease, and left **8** queue cells,
`maximum_producer_count` **64**, **106** snapshots and **65** accepted writes.
The private database was **28,672** bytes in every case, including the
controls. Unavailable and opted-out sent no report, recorded no instrumented
sqlite, prepare, network, reserve or transport call, and accepted no writes.
Opted-out still counted **53** snapshot calls; unavailable counted **0**. An
empty call map means those snapshot calls returned before `open`. It does not
identify which earlier branch returned.

Enabled call totals, both repeats: `sqlite.open=139`, `sqlite.close=139`,
`conditions.prepare=1`, `network_cost.start=1`, `delivery.reserve=1`,
`transport.socket=1`. Allocation errors were empty. No new Electron process
appeared. These are first-call windows around the named methods. They are not
causal ownership of the resident set, and they are not the paired 2 MiB or
0.5% comparison.

| Window | r1 RSS / file / anonymous / heapUsed | r2 RSS / file / anonymous / heapUsed |
| --- | --- | --- |
| `sqlite.open` | 1,179,648 / 983,040 / 217,088 / 44,032 | 1,179,648 / 1,048,576 / 192,512 / 49,896 |
| `sqlite.close` | 0 / 0 / 8,192 / 4,764 | 0 / 0 / −20,480 / 4,764 |
| `network_cost.start` | −147,456 / 81,920 / −262,144 / 89,220 | 61,440 / 81,920 / −266,240 / 89,360 |
| `conditions.prepare` | 1,101,824 / 278,528 / 630,784 / 798,924 | 1,073,152 / 344,064 / 667,648 / 809,340 |
| `delivery.reserve` | 524,288 / 0 / 638,976 / 207,160 | 655,360 / 0 / 479,232 / 215,164 |
| `transport` | 1,908,736 / 524,288 / 1,536,000 / −1,281,348 | 1,826,816 / 327,680 / 1,503,232 / −1,237,360 |

`prepare()` awaits `network.start()` and then, on a first CPU sample, waits
**250 ms** before the second `read()`. The probe records the network window
before `prepare` completes. The prepare spans are **255.488 ms** and
**258.189 ms**. That wait is the existing admission delta, during which other
app work can run. It is not a spare telemetry allocation. Removing it would
leave the first sample incomparable. This run's guard was `allowed` only after
the second sample. Clocks stay as they are.

The first `open()` window includes `import('node:sqlite')`, one
`DatabaseSync`, and the existing pragmas, including `mmap_size=0` and
`cache_size=-128`, before the method returns. Node's `DatabaseSync` is one
connection, and `close()` is `sqlite3_close_v2()`. SQLite disables
memory-mapped I/O when `mmap_size` is 0. The database file is 28,672 bytes, so
that file cannot be the whole 983,040 / 1,048,576 file-backed rise. No mapping
name was recorded. The rise is not labeled as a library. The other 138 opens
were counted, not windowed. They are not 138 copies of this first-open rise.
Each open still does a fresh filesystem check and drops the handle on close.
Statements are already reused inside one `recordMany` transaction. The wire
encoder and the release route address are already cached. Company policy,
schema, consent, lease, final send, review bytes, cancellation and budgets
are re-read on purpose. Caching a positive policy result would weaken those
checks. A retained connection is a separate design question: it need not cache
policy, but would require fresh transactions and independently verified file
identity, permissions, replacement, failure and ownership handling. These
windows do not establish that such a design would save resident memory.

The transport windows rise by 1,908,736 and 1,826,816 RSS bytes while
`heapUsed` falls by 1,281,348 and 1,237,360. The explicit buffers on that path
are the 25-byte body, 4,096-byte socket marks, and the 32,768-byte TLS cap.
The falling heap value is compatible with garbage collection; other app work
and the observer can also affect the same window. The counters do not assign
the resident-set rise to any one of those causes or identify an unnecessary
buffer. TLS and the storage engine stay as they are.

Import windows are unstable across enabled and control cases, from 2,752,512
to 6,946,816 RSS bytes, with file-backed rises in the controls as well. They are
not an enabled-only telemetry cost. Whole-process `electron_cpu_ms` on the
enabled cases was 2,580 and 2,590 over about 29.3 s and 29.2 s. Comparison was
off, so those figures are not a one-core percentage against unavailable.
`resource_acceptance` stays false. The 2 MiB and 0.5% gates stay unaccepted.
Collection, destination and route stay false/null/null. V08 remains Building.
All 66 requirements remain.

No runtime file was edited. No regression test was added. This clone did not
run the Electron suite.

The bounded redundant-work search in `telemetry-store.ts`,
`telemetry-activity.ts`, `telemetry-delivery.ts` and `telemetry-transport.ts`
did not select a runtime patch. The first-open window alone is below 2 MiB;
accepting it does not qualify total process overhead or CPU. It includes cold
initialization and cannot be assigned to every later connection. Neither a
budget waiver nor weaker freshness checks follows from these observations.
Further optimization needs a separate design with an identified avoidable cost
and preserved ownership and policy checks. No automatic repeat of this
attribution or phase-memory workload is selected by this review.
