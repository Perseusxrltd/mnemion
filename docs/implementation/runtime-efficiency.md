# Runtime efficiency across Mnemion

Quentin's 30 October 2026 clarification applies to the whole product: Mnemion
must remain light in the background and use resources when useful work needs
them. This extends the existing F06/R04 requirements and the background,
librarian and telemetry work; it does not add a competing feature milestone or
remove any of the 66 requirements. Whole-product acceptance remains open.

## Required behavior

- A remote client must not load an embedding model or start a local workspace
  solely to remain connected to a team workspace.
- Idle and tray operation must avoid continuous rendering, repeated full scans,
  unnecessary network polling and model calls. Essential health, update and
  capture work must use bounded checks and coalesce repeated notifications.
- Models load on demand, share a managed owner where supported, and release
  idle allocations without losing memories or interrupting active inference.
- Foreground memory operations take priority over indexing, sync, evaluations
  and librarian maintenance. Background work uses bounded batches, yields and
  resumes from durable progress instead of restarting a full job.
- Current RAM/CPU pressure, battery, thermal and network-cost signals guide
  optional work. Missing signals stay unknown. Deferral must be visible and
  must not discard accepted memories, weaken access checks or fake freshness.
- People and authorized agents retain the same resource controls. A lowered
  budget takes effect cooperatively; it must not kill an active write or erase
  its recovery state.
- Dashboards and the memory map render and refresh when needed. An inactive
  view must not keep expensive analysis or animation running for display only.

Existing [RAM controls, shared models, idle eviction and inference
fairness](../service/memory-resources.md) provide part of this behavior. Their
documented measurements retain their original scope. They do not prove that
every background process is already light on every supported machine.

The shared [librarian](../service/librarian.md#background-operation) now backs
off empty queue checks to a 30-second sleep cap, with a coalescing local wake
after a queued API run commits. Active steps retain their two-second pacing and
resource checks. This reduces the frequency of idle queue claims; it is not a
measurement of CPU or RAM savings across the application. Scheduled and
cross-process submissions retain the bounded fallback.
The [focused scheduler checks](../validation/2026-10-30-librarian-idle.md)
cover those behaviors and their limits. The idle backoff is published in
4.46.58; all six public auto-update checks and website synchronization passed.
That release validation is separate from the counter checks below.

The desktop source change removes idle timer wakeups. The earlier two-second
tick already returned before file, native, credential or network work when
nothing was due. Each enabled source keeps its saved next scan time; empty
or fully paused lists leave no scheduler timer. Startup, save, resume and
Sync still request prompt scheduling. Automatic follow-up work already due
retains the two-second gap. When no usable stored deadline can be selected,
unusable deadlines fall back to a bounded delay based on the source interval;
invalid current-clock readings are handled separately. Update suspension
clears the wake. Resume restores scheduling; close cancels wakes and drains
owned work, and late callbacks cannot restart it. The helper's two-second
memory sample during a scan is unchanged. The
[reviewed lifecycle checks](../validation/2026-10-31-source-deadline-scheduling.md)
use controlled time and do not measure CPU/RAM savings. F06/R04 remains partial.

The capture status display now disarms its age-refresh interval while the page
is hidden. Returning to the page refreshes the age immediately and resumes the
existing one-minute cadence. Removing coverage or closing the view clears the
timer and listener; late callbacks cannot restart them. This is display-only
work: capture and delivery continue on their existing schedules. The
[source review and frontend typecheck](../validation/2026-10-31-capture-ui-and-service-bootstrap.md)
cover this change; no whole-application CPU or RAM saving is claimed.

The [native counter follow-up](../validation/2026-10-31-native-memory-counters.md)
improves Windows lifetime measurements and cleanup reporting. The Darwin
adapter now retains live per-process kernel RSS peaks. The corrected C probe
and actual Python adapter passed component checks on both Mac targets, with
partial coverage and successful cleanup. The original decoder failure remains
preserved. These diagnostics do not add a production background worker or
establish whole-product CPU/RAM savings or resource acceptance. Production
telemetry remains off.

The corrected Mac child reader passed a further native component check on
both targets, each observing one deliberately held live descendant. That
fixture is separate from the ordinary work ledger; coverage across the full process lifetime
remains incomplete.

The [installed process-role evidence](../validation/2026-10-31-installed-process-roles.md)
adds absolute RSS observations at the existing workload checkpoints, with
explicit ownership and missing-data checks. It adds no production polling.
Focused source checks and the installed Mac ARM workload passed. All six cases
retained the nine expected checkpoints and completed 128 memory cycles each,
with 2,310 successful API requests overall. The role comparisons are available;
whole-process lifetime coverage and the full CPU/RAM comparison remain open.

The [Python permission-read and Linux residency follow-up](../validation/2026-10-31-telemetry-permission-and-residency.md)
removes full-status reads from Python observation startup while retaining
fresh consent checks at persistence and delivery. Linux diagnostic snapshots
keep current RSS and its components from the same observation, separate from
kernel high-water marks. Three corrected producer cases and Linux source
fixtures passed, with the original failures preserved. Neither change adds
production polling or qualifies measured CPU/RAM savings. Low idle resource
use across the whole product remains required and unaccepted.

## Acceptance work

Measure the complete owned process set, including the app, local engine,
database, model worker and short-lived helpers. Separate a remote client from
a computer hosting a workspace. Record idle/tray and active CPU, wakeups,
resident memory, disk and network traffic, foreground latency, queue age and
progress after interruption. Keep cold starts separate from warm operation.

Exercise modest hardware, each supported OS/architecture, a lowered RAM budget,
memory pressure, battery constraints, offline recovery and an active ingestion
backlog. A smaller installer, low JavaScript heap, an empty workspace or one
quiet process cannot stand in for these measurements. Missing counters and
unobserved periods remain explicit.

The current [telemetry-specific allowance](telemetry-resource-budget-2026-10-30.md)
remains unchanged. It is not a whole-application RAM or CPU target. Establish
whole-product targets from representative measurements and retain failed
results; do not raise limits automatically to make a check pass.

Continue the current telemetry milestone and its concrete fixes, including
the [CPU admission follow-up](../validation/2026-10-30-telemetry-cpu-admission.md).
Use this contract when reviewing the existing background scheduler and remaining
F06/R04 acceptance, without starting parallel fragments of the roadmap.
