# Telemetry resource budget revision

30 October 2026. Engineering decision for the next V08 acceptance work.
**Resource acceptance remains unproven and production collection stays off.**

The current RAM allowance is **8,388,608 bytes (8 MiB) of additional resident
working set per participating process** in the declared installed acceptance
workloads, including cold activation and delivery. CPU remains at **0.5% of
one core averaged over fixed active work**. This replaces the initial 2 MiB
engineering allowance; it does not change the user's requirements for an
efficient product that works on modest hardware.

## Why revise the allowance

The [recorded compiled-app comparison](../validation/2026-10-29-telemetry-v3-resource.md)
measured enabled main-process maxima of 5,271,552 and 2,887,680 bytes.
An 8 MiB allowance leaves approximately 3 MiB above the larger observation.
The later attribution recorded a 1,179,648-byte first SQLite activation rise
in both repeats and transport windows of about 1.8 MiB while used heap fell.
Those windows cannot be added together or attributed to specific mappings.
They support budgeting several MiB for native initialization and allocator
behavior, without proving an irreducible cost or acceptable implementation.

Retaining a SQLite connection was rejected because it blocked Windows database
replacement and kept an old generation. Fresh storage/ACL checks, current
consent and the existing owner remain. We will not trade those protections for
a smaller measurement. The recently reviewed validation change removes known
discarded allocations, but has no measured RAM or CPU saving yet.

No model or new persistent service may be loaded solely for telemetry.
The queue, record age, per-attempt and daily wire limits, bounded producer work,
pressure controls, opt-out and company policy remain unchanged. Saturation
must discard optional telemetry rather than delay canonical memory work.

## What must now be measured

Qualify the reviewed implementation using fixed, counterbalanced unavailable,
enabled and opted-out installed journeys. Pin source, installer hashes and any
declared diagnostic configuration differences. Cover the six native targets
and the real browser/headless paths, cold activation, actual delivery,
sustained memory work, saturation and cancellation.

Retain startup differences, maximum matched-phase differences, sampled peaks,
endings, file-backed and anonymous residency, and process identities. Include
short-lived helpers. Heap usage, averages, a warm-only start or forced garbage
collection cannot replace working-set measurements. Document sampling limits;
this budget is not a guarantee about every unsampled instant.

Measure CPU over the same fixed active work without adding idle time. The
existing observer can miss short-lived processes and its CPU values are lower
bounds; changing a report threshold cannot qualify CPU. Preserve foreground
operation latency and verify refusal under real resource constraints.

## Evidence that can reject the implementation

The historical opted-out excursion of 10,330,112 bytes already exceeds the
new allowance. An earlier source revision also exceeded 8 MiB while enabled.
These failures and uncertainties remain recorded. No old run is rescored as
a pass, and the unchanged compiled workload will not be repeated merely to
obtain a favorable result.

Any new unexplained excursion above 8 MiB, continuing growth, missing process
accounting, CPU above 0.5%, or degradation of canonical memory work prevents
acceptance. The budget must not rise again automatically after a failed run.
Installed delivery, browser admission, operated collector privacy and useful
fleet data remain separate open requirements. All 66 product requirements
retain their text and status.
