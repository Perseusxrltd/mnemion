# Telemetry cold initialization and storage ownership — 26 October 2026

This source review retains the desktop's existing owner and shared private
SQLite coordination. It implements no optimization and accepts no resource
result. V08 remains **Building**; collection/destination/route remain
**false/null/null**, and all 66 requirement states are unchanged.

The [one completed attribution run](2026-10-26-telemetry-attribution.md),
[40265207114](https://github.com/Perseusxrltd/mnemion/actions/runs/40265207114),
measured source `dc98218c70c3ec4453ee6f54065474ac4b3af969`. Both enabled matched
main-process maxima exceeded 2 MiB: **3,608,576 / 3,391,488 bytes**. First
SQLite-open windows added **917,504–983,040 bytes** of file-backed residency;
common import windows added about **2.09–2.37 MB** of Linux RSS. These overlapping
windows identify neither a particular mapping nor SQLite as the sole cause.
The original decision SHA-256 is
`16d0a678592ed7a17443c921611a9810e188f1a46b70137c8c96a0adeef6c089`.

## Existing ownership

The reviewed source follows baseline
`dffbfa49aa3565512c622c5d784bceb7da52eff8`; it includes later report-review work
that the earlier attribution run did not measure.

| Boundary | Current source behavior and constraint |
| --- | --- |
| App lifetime | [The service bridge](../../studio/electron/service-bridge.ts) statically imports the telemetry classes but constructs one activity/catalog on demand. Local workspace creation is separate. A desktop connected only to a remote workspace need not have a persistent local Python engine. |
| Storage runtime | [NativeTelemetryStore](../../studio/electron/telemetry-store.ts) already loads `node:sqlite` dynamically after private-store checks. It retains the module promise, not a database connection. Unavailable and known-negative snapshots can return `null` before opening SQLite. Deferring SQLite import is therefore already implemented. |
| Transactions | Each admitted read/write opens a fresh connection with zero lock waiting. Current file permissions, policy, company restrictions and generation/revision remain authoritative. `shrink_memory` and close run on exits; closing a connection does not prove that runtime/code pages leave RSS. |
| Delivery | [DesktopTelemetryActivity](../../studio/electron/telemetry-activity.ts) offers work only after a committed observation or explicit approval. The [existing owner](../../studio/electron/telemetry-owner.ts) has one active attempt, no wake timer and active cancellation. Transport code is already dynamically imported. |
| Explicit controls | The bridge may run the existing engine for an explicit telemetry control action. This is separate from producer recording and delivery. Moving ordinary measurements through a new Python subprocess per call would add startup/lifetime costs and cannot provide a persistent owner for remote-only desktop use. |

Shared SQLite remains the authority for Python and Electron choices, staged
reports, contribution limits and durable spending. An optimization must retain
fresh ACL/file-replacement checks, generation/revision fencing, atomic report
claiming and final handoff, and zero-wait producer/delivery coordination. It
must not create a second queue, cache positive consent, require a local memory
engine, or introduce a telemetry daemon.

## Concrete decision still required

Keep storage and delivery in the existing desktop lifetime. The next design
decision is whether separating the optional control/review dependency graph
from the minimal producer path can reduce cold activation, or whether the
storage binding itself needs an in-process alternative. Current static imports
and the already-lazy SQLite/transport boundaries make those different changes.

An import-boundary change may reduce unavailable-path initialization without
reducing the enabled-minus-unavailable peak. A different native SQLite adapter
would need the same file/schema and cross-runtime transaction guarantees plus
all native build targets; no lower residency has been demonstrated. Retaining
connections adds file-replacement, stale-authority and retained-memory concerns,
and is not justified by the existing evidence. Another close-call adjustment
does not address a demonstrated ownership change.

This review dispatches no benchmark and adopts no budget revision. The fixed
**2 MiB added RSS per participating process / 0.5% of one core** gates remain
unchanged and unaccepted. Choose and justify one bounded ownership change
before another measurement; preserve all six original outcomes. Sampled peaks,
ending values, overlapping first-call windows and Linux development-app results
do not establish a universal peak, causal saving or installed/platform result.
