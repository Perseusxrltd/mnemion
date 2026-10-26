# Browser pressure startup and sample freshness — 26 October 2026

This source follow-up, based on `f40a4bbc9cbca435c0b06292dd808fcd45ffe5ae` and
intended for 4.46.29, extends bounded pressure initialization and measures
freshness from the OS sample timestamp. Nine focused unit tests pass; final-source
nominal-browser qualification remains open after an actual startup refusal.

## Observed startup and source change

Actual Chromium **155.0.8059.12** produced these retained results without a sensor
override:

| Observation | Result |
| --- | --- |
| Original `BrowserConditions.start` | Refused at **1,002.6 ms**; constrained remained true and metering unknown. |
| Separate real `PressureObserver` reference | Returned a nominal reading at **1,055 ms** in its own observation. |
| Startup-only change, historical | Accepted an actual nominal first reading at **2,089.3 ms**; constrained became false and metering remained unknown. This preceded the sample-timestamp fix. |
| Final sample-timestamp source | Refused at **3,002.1 ms** with no usable first signal; constrained remained true, metering unknown and sample age unavailable. |

The final run failed its expected nominal qualification. Its cause is not
established, and no further pressure trial is selected this batch. The earlier
2,089.3 ms pass does not qualify the final timestamp source.

[BrowserConditions](../../studio/frontend/src/workspace/telemetry-conditions.ts)
now permits **three seconds** for initialization before report reservation,
instead of one. It also uses `PressureRecord.time` for the existing **two-second
freshness ceiling**. The [W3C definition](https://www.w3.org/TR/compute-pressure/),
retained in `pressure-spec-reference.json`, identifies the time data was obtained
from the system relative to the observer's global time origin. The old source
used callback `performance.now()`, which could make an old nominal sample appear
fresh. Current source rejects invalid, future, negative or expired sample times,
and rechecks age when reading the conditions.

Nominal-pressure, heap, network and visibility gates remain required. Missing or
critical signals still refuse admission; cancellation invalidates late callbacks.
Neither the five-second report lease nor privacy, spending or transport rules
changes. Unknown metering does not become permission to send.

## Qualification and retained failures

The private `2026-10-26-telemetry-browser-pressure` evidence set retains
`pressure-result.json`, `followup/pressure-result.json` and
`timestamp-followup/pressure-result.json`, including their source-module hashes.
All actual probes sent **zero reports** and made **zero model calls**, without a
sensor override. Browser and loopback HTTP fixture cleanup was confirmed,
including after the final failed nominal qualification.

The closed `source-qualification.json` confirms that final module SHA-256
`3f00a1e3da7943a8aff743e34cca674df32eb790720cada1409619e8d1b9263a`
matches the actual attempt: nominal qualification is false, while bounded
refusal cleanup passed.

The earlier `followup-checks/browser-pressure-followup.json` retains the four-test
startup-only pass, its actual-browser result and frontend build. Final
`timestamp-checks/pressure-timestamp-followup.json` records **nine unit tests
passed, zero failures/skips**, followed by the actual-browser probe's exit 1.
These nine include the earlier four cases, plus stale/future/missing/nonfinite
sample refusal and sample-time expiry/reversed-clock handling; the four are not
added twice. The final-source probe failure prevented the build step from running.
Only that unreached step was then executed:
`remaining-checks/pressure-remaining-build.json` records a passing frontend build.

The initial missing-`esbuild` fixture error in `checks/current-sensor.log`
occurred before any browser launch. `dependency-correction.json` records use of
the already installed TypeScript compiler without changing the product for that
correction. Both reproduced runtime defects remain evidenced: the startup unit
reproduction failed with `false !== true` in
`reproduction/late-realistic-reading.log`, and stale-sample acceptance failed with
`true !== false` in `timestamp-reproduction/stale-sample.log`. Neither expected
failure is erased by the later unit passes.

## Remaining limits

`resource-window-review.json` interprets only the six existing resource
originals. Overlapping first-use windows cannot be summed into causal component
costs. No new resource trial, TLS replacement, allocator replacement or budget
increase was selected. The [scoped-trust resource failure](2026-10-26-telemetry-scoped-trust-results.md)
remains retained; the **2 MiB / 0.5%** gates remain unqualified.

All 66 requirement IDs, texts and states remain unchanged. V08 stays Building
and inactive, with collection unavailable and destination/route null. Native
and web full-app acceptance, installed platforms, provider/privacy and whole-wire
qualification remain open. This sensor result does not establish full browser
delivery or a resource saving.
