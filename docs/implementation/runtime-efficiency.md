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

Continue the current telemetry milestone and its concrete fixes. Use this
contract when reviewing the existing background scheduler and remaining
F06/R04 acceptance, without starting parallel fragments of the roadmap.
