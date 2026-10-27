# Deferred delivery after collection saturation — 27 October 2026

This source follow-up is based on
`bc4d6e0892af35e5952f14a4d18e35924c2a0157`. A retained actual Electron regression
reproduced a stranded queue: admission temporarily refused delivery, 64 permitted
contributions exhausted that workflow's collection allowance, and later awake
work never offered the already committed queue again. The ready case failed
with **zero TLS requests instead of one**. A second genuine regression then
showed that a live exhaustion hint could make `TelemetryWorkflow.begin` return
null before `recordMany`, even after the delivery cadence elapsed. That earlier
path also failed zero-versus-one; both original failures remain retained.

The [shared owner](../../studio/electron/telemetry-owner.ts) now retains a defensive
copy of one prior committed revision/generation stamp. The
[desktop activity](../../studio/electron/telemetry-activity.ts) can reoffer it
during ordinary awake work at both refused recording and valid, explicitly
scoped workflow-snapshot boundaries. Snapshot refusal is preserved; unscoped
inspection and unknown workflow/surface categories offer nothing. This uses the
existing minute cadence, without a timer, extra contribution, wire allowance
or shutdown flush. The stamp identifies prior work; it is not cached permission.
Reservation and send still require fresh policy, eligibility, sensors, spending
and transport checks. Paused owners cannot deliver, and close forgets the stamp.

## Scoped qualification

The [TLS regressions](../../studio/electron/scripts/test-telemetry-transport.mjs)
now send once after readiness returns through either boundary; opted-out and
closed cases send zero.
Further refused observations do not add another request. The
[owner checks](../../studio/electron/scripts/test-telemetry-owner.mjs) also verify
defensive copies, cadence and that awake work cannot invent an originating stamp.
These fixtures use actual **Electron 44.9.3 / Node 24.22.0 on Linux x64**, real
local TLS and controlled clock/admission conditions, not an installed app journey.

The combined [CLI and delivery batch](2026-10-27-telemetry-cli-coverage.md) passed
**66 Python checks**, **50 actual Electron owner/transport checks**, and **six
browser-source checks**: five browser-activity checks using the shared owner,
plus the same one preview case already recorded earlier. All have zero skips;
the preview is counted once.
The final native selection includes the earlier 47 passes, not 47 additional
tests; that original receipt remains retained. Electron was rebuilt. The passing
Python/browser checks and SDK/frontend builds were reused after their inputs
were verified unchanged.

The 690 CLI/Python/frontend input bindings remain unchanged, with inventory
digest `154b2ce0ffed2cfd0a0ae2cbd0966ddde109c425c8c158db307ec33eecb28a1f`.
The final inventory adds native coverage for **851 files**, with digest
`862246dd9f37479311b7376b18e4129ac73a03171ca05d4844d57ff299668590`.
The closed final source-qualification receipt has SHA-256
`931634eda595aae42493fa160a064950666696a044a8e51217522ffa33d427a7`.
The earlier source qualification and runtime inventory remain preserved.

The [original app comparison](2026-10-27-telemetry-catalog-comparison.md), run
**40477197149**, remains **failed with five of six journeys completed**. This
separately reproduced bug is **not its established cause**. No replay of that
original, causal RSS/CPU saving or resource acceptance is credited. All earlier failed evidence
and the strict **2 MiB / 0.5%** ceilings remain binding.

The selected [changed-source comparison](2026-10-27-telemetry-delivery-comparison.md)
completed as run **40483350394** on `29dcd70d`, with all six 128-cycle functional
journeys, source bindings and cleanup qualified. Resource acceptance still fails
2 MiB. The original run is not replayed or retried, and its cause remains
unproved. No further app comparison is selected. The later
[browser/Python source follow-up](2026-10-27-telemetry-owner-saturation.md) has
separate checks and was not included in that app run.

All 66 requirement states remain unchanged, V08 remains **Building**, collection/
destination/route remain **false/null/null**, and release CAs are empty. The
[acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md) retains installed,
full wire, resource, provider/privacy and aggregate qualification requirements;
the action inventory still exposes 29 unmeasured CLI paths.
