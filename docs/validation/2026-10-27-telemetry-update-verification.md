# Update verification observations — 27 October 2026

Update integrity checks previously contributed only to the enclosing download
cycle. This source follow-up adds `update.verify` at observable boundaries,
fixes timing lost during asynchronous privacy reads, and prevents late updater
callbacks from acquiring telemetry after shutdown.

The work is based on `e03513dfba4817025e9fe8b1a8428268b1671c6b`.
**91 Python tests, 48 compiled Node tests and 29 browser-source tests passed**,
with no Node skips. The current SDK and Electron builds passed. Seventeen
recorded runtime, test and mapping inputs still matched after the checks.
[Machine-readable results](2026-10-27-telemetry-update-verification.json)
retain their hashes and qualification limits.

V08 remains **Building**. Collection/destination/route remain
**false/null/null**, with release certificate authorities empty. Catalog and
wire formats, all 66 requirement texts and the resource ceilings are unchanged.
This source batch does not request a separate native release.

## Observed boundaries

| Owner | Observation and limit |
| --- | --- |
| Windows desktop | The explicit post-transfer verification event starts a validation attempt. Ready, error or cancellation ends it. A cached installer can enter this stage without another download. Manifest checks and earlier cache inspection are not separately counted. |
| macOS desktop | The native verification/extraction event starts the measured stage; ready, error or cancellation ends it. Its elapsed time includes extraction and preparation, not just signature verification. |
| Linux AppImage | The original download-attempt policy is captured before completion. Actual transfer progress followed by `update-downloaded` establishes a successful integrity completion. No separate verification start is exposed, so this outcome omits phase latency. Opaque errors are not classified as verification failures. |
| Automatic managed host | Fresh staging measures the final installed-package and runtime-wheel integrity checks under the watcher's own acknowledged policy. A failed read-only integrity check records failure; other interrupted mutation outcomes remain unconfirmed. Manual calls, ready-runtime reuse and reusable runtime inspection gain no owner. |

The pinned Linux updater can emit `update-downloaded` for same-session cache
reuse after checking only existence. That callback alone cannot establish a
fresh verification. Requiring transfer progress in the same attempt prevents
backfilling the earlier integrity result. This follow-up changes no updater
security check, download algorithm, package bytes or installation behavior.

Repeated progress or verification events do not duplicate the same active
attempt. A retry can have its own observed validation attempt while the
enclosing download still has one terminal cycle outcome. These are different
units and must not be summed as unique user actions. Opt-out and replacement
of the privacy store invalidate original measurements; quit discards them and
prevents subsequent callbacks from taking a new privacy snapshot.

`TelemetryWorkflow` now captures its monotonic start before awaiting policy.
Otherwise work that completed while the policy read was pending could appear
to take almost no time. Completion callbacks also capture their actual end
before waiting for the original pending owner. A reproduced case reported
230 ms for a 40 ms phase; the corrected measurement reports 40 ms. Known
completions without an observable phase start use an explicit untimed outcome,
rather than reporting a fabricated duration.

## Evidence

The Python selection includes real tiny signed package archives and the actual
installed-file comparison, with only the dependency installer simulated. It
checks intact and tampered packages under both automatic and unowned calls:
tampering still prevents a ready runtime, manual work emits nothing, and a
reused ready stage adds no observations. Policy tests cover opt-out, company
restrictions and replacement of the private store.

The compiled Node selection checks validation retries, cached platform
validation, Linux transfer/completion callbacks and cache exclusion, cancellation,
original-policy fencing, late events after quit and delayed-policy timing.
The browser selection verifies the updated read-only coverage preview.
These are source and controller checks, not installed Windows/macOS validation.

The regenerated inventory has **94 mapped categories and zero unmeasured
categories**. Its **634 declared actions** comprise **362 mapped, 265 excluded,
seven delegated and zero unmeasured**. These totals describe declarations;
they do not prove every runtime call site or activate collection.

Private qualification SHA-256:
`0e8400f32d193affe382e6c4bc97fdf705dfaa0ae23556c59360333c3001cd74`.
The original implementation plan, Linux cache-boundary refinement, dependency
checks and first successful selection of 47 Node checks remain retained, as
does the failing completion-time reproduction. After correcting that timing
case, the rebuilt Electron source passed all 48 Node checks. The 91 Python
and 29 browser checks covered unchanged inputs and were not repeated. The separate
[setup disclosure follow-up](2026-10-27-telemetry-setup-disclosure.md) also passed
its compiled Linux Electron review journey on the earlier integrated source.

Final installed app/agent/headless/web journeys, whole-wire budgets, resource
and tail-latency acceptance, actual provider privacy and aggregate attack/utility
evidence remain required in the [acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md).
