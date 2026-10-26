# Browser admission and review — 26 October 2026

This source follow-up is based on
`cce346d4085661406b62cabedde0afaa34f38d50`. Browser ownership now propagates
cancellation through eligibility and sensor startup. The compiled browser app
passed ten privacy/review checks with real pressure observations and one approved
four-byte TLS report. Production trust and resource acceptance remain open.

## Pressure and owner cancellation

A fixed Chromium **155.0.8059.12** trace admitted a nominal first sample after
**2,414.2 ms**, with sample age **0.6 ms**. Constrained state became false while
metering remained unknown. The trace forwarded native callbacks and records
without substituting signals, permissions or the clock. It used the unchanged
pressure module with SHA-256
`3f00a1e3da7943a8aff743e34cca674df32eb790720cada1409619e8d1b9263a`.
This sensor-only trace sent no report or model request; browser and HTTP fixture
cleanup passed.

The prior [3,002.1 ms refusal](2026-10-26-telemetry-browser-pressure.md), original
1,002.6 ms refusal, startup-only pass, dependency error and both unit
reproductions remain retained. The previous timeout's cause is still unproved.
The three-second initial wait, two-second actual-sample freshness ceiling and
network, heap and visibility gates are unchanged.

The original [BrowserTelemetryActivity](../../studio/frontend/src/workspace/telemetry-activity.ts)
ignored its parent's abort signal during eligibility. Retained unchanged-source
tests reproduced late eligibility starting a sensor after opt-out or page exit,
and owner cancellation failing to stop a sensor already starting. The corrected
owner checks cancellation before and after eligibility, propagates it through
the sensor's lifetime and removes the listener during cleanup. Final reservation,
current-policy, spending, transport and lease checks remain required.

All **134 browser telemetry source tests passed**, with zero failures or skips.
The frontend build passed in **16.831 seconds**. The unchanged-owner failures
remain retained separately from those passing checks.

## Compiled browser-app journey

The actual Chromium app passed **all ten privacy/review checks** across **two
launches** and **three save/fetch/recall cycles: nine memory operations**. Its
**161 successful fixture HTTP requests include app assets**. The app and probe
shared compiled policy/client modules; all **2,185 source and existing compiled
inputs** matched, and the new frontend build recorded **578 assets**.

The checks covered fresh disclosure, workspace onboarding, controls before
permission, app acknowledgement, exact report review, cross-tab opt-out,
empty re-enable, discard without spending, approved delivery, and persistence
of opt-out, review mode and spent allowance after browser restart. Exactly
**one accepted four-byte TLS report** matched the inspected body. The collector
retained zero metadata after its boundary and published no aggregates. There
were no model calls or nonfixture page requests.

Native pressure callbacks supplied a nominal record with age approximately
**0.7 ms**, without substituted signals or time. TLS used an exception for the
exact temporary certificate's SPKI hash in this disposable browser profile;
**production browser certificate validation is not qualified**. The actual
source server and content security policy were exercised within that fixture.

Original failed fixtures remain under `browser-app/` and
`browser-app-corrected/`. Two correction receipts preserve the changes: replace
desktop-only selectors with the actual web form, wait for saved state after
asynchronous checkbox updates, and keep the listener/temporary tree alive until
owned cleanup finishes. These fixture repairs changed no runtime or policy.
The first fixture closed its browser contexts but has **no Python cleanup
receipt** because of the listener-lifetime error; its cleanup remains
unqualified. The second and final fixtures have passing cleanup receipts.
The final fixture closed both browser contexts, stopped the driver and collector,
removed its temporary state and left Python telemetry disabled.

## Evidence and limits

The private `2026-10-26-telemetry-browser-admission` evidence set retains original
failures, correction receipts, source/build manifests, pressure callbacks and
cleanup. The closed summary binds the individual app receipts and corrections.

| Receipt | SHA-256 |
| --- | --- |
| Closed browser-app qualification | `82b946d04d2af0b171b609912abd6ed4b361252a5f32b45db6f7db22cb85c9a8` |
| Final app journey | `d988e3c52d7f08b3def9b98cefed3c24be146f0fa135595e40cc78d7d2697069` |
| Corrected source tests and build | `e8f4da6536f838f5e043943f14a9011710d913def1ba64f44ebcb1ec1d25ec5c` |
| Separate actual pressure trace | `21c6d56b2f02f4447237d6706aa4b150c4a9e279f37405c5d6bb457872a322b5` |

This is functional evidence for the recorded compiled browser app and fixture.
It establishes no resource saving, installed-platform, whole-wire or provider
privacy acceptance. Earlier RSS failures remain retained and the **2 MiB /
0.5%** gates remain unqualified. All 66 requirement texts and states are
unchanged. V08 remains Building with collection/destination/route
**false/null/null** and an empty release CA list.
