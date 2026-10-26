# Product telemetry report-format preview

**Source and installed-control validation, 26 October 2026.** Format-preview
component checks passed, followed by qualification of five installed native
targets from the frozen 4.46.12 candidate. The controls show a fixed synthetic
example; they do **not** inspect the actual next outgoing packet. Intel Mac,
public-release and full V08 acceptance remain open. V08 remains Building and
production collection/destination/route stay false/null/null. See
[release status](../RELEASE_STATUS.md) for public availability.

## Implemented source behavior

The [Python preview](../../mnemion/product_telemetry/policy.py) and
[browser preview](../../studio/frontend/src/workspace/telemetry-policy.ts) expose
`illustrative_packet.kind: "synthetic_example"`, with Base64 **`AQAHAA==`**
representing the fixed four bytes **`01 00 07 00`**. The
[Python](../../mnemion/product_telemetry/wire.py) and
[TypeScript](../../studio/electron/telemetry-wire.ts) helpers describe those
supplied bytes without sampling the user's queue or drawing new randomness.
The [shared types](../../studio/shared/product-telemetry.d.ts) distinguish the
format example from actual-body fields, which remain null/zero with
`outbound_state: "not_inspected"`. Four is the report-body size, not the total
network cost.

Viewing the example neither reserves an attempt nor changes queue contents,
spent allowance, consent or network state. Local aggregate counts remain
separately labeled snapshots. The [Privacy page](../../studio/frontend/src/workspace/Privacy.tsx)
uses “Inspect the report format” and “Show report format”; it clears a previous
preview on choice changes, status refresh, window focus or a cross-tab choice
notification and discards late responses. The component checks below preceded
the later five-target installed-control qualification.

`transport_available` now describes valid configured release-route capability,
independently of consent or a current send. Python status and sending share a
[pure endpoint validator](../../mnemion/product_telemetry/endpoint.py), with a
bounded cached read of the immutable packaged route. Browser status and sending
share the same [HTTPS destination validator](../../studio/frontend/src/workspace/telemetry-capability.ts).
Neither validation performs network I/O. Capability remains false in the
production configuration and does not replace actual-attempt policy, resource
or delivery checks.

## Completed component checks

| Selection | Result | Duration |
| --- | --- | --- |
| Python preview/policy and related telemetry checks | 106 passed | 12.73 s |
| Browser source checks | 82 passed, zero failures/skips | 8,132.606559 ms |
| Native-control/wire source checks | 9 passed, zero failures/skips | 991.806298 ms |

The [Python preview cases](../../tests/test_product_telemetry_preview.py) cover
new, enabled, disabled, company-restricted, damaged, in-flight and cooldown
states. They prohibit preparation/reservation/socket creation during preview,
compare private files before and after repeated reads, preserve an existing
reserved packet and leave an absent store uncreated. They also check that
status, schema and preview agree about valid and rejected route configurations.
The [browser cases](../../studio/frontend/scripts/test-product-telemetry.mjs)
check fixed bytes, unchanged storage and configured capability independent of
opt-out. The [wire cases](../../studio/electron/scripts/test-telemetry-wire.mjs)
compare the Python and TypeScript example fields and exact decoded bytes.
These selections include existing related coverage; their totals are not a
count of newly added preview tests or installed-platform passes.

## Five installed native targets qualified

The original source checkpoint left this journey unexecuted. Later,
[release run 40258369359](https://github.com/Perseusxrltd/mnemion/actions/runs/40258369359)
completed with **failure at 03:16:24 UTC**, on frozen source
`bd3b212567d878c8b28c1d4c3eb8c86c47bb5311`. A read-only qualification at
**03:27:54 UTC** verified the five successful targets' retained installed-hosting
artifacts against that source's **64 required true fields**. It bound workflow
attempt 1, job and artifact timing, archive/evidence hashes and the frozen
receipt contract. No app, test or release journey was replayed.

| Installed target | Successful original job | Required true fields |
| --- | --- | ---: |
| Linux x64 | [121368345759](https://github.com/Perseusxrltd/mnemion/actions/runs/40258369359/job/121368345759) | 64 |
| Linux ARM64 | [121368345611](https://github.com/Perseusxrltd/mnemion/actions/runs/40258369359/job/121368345611) | 64 |
| Windows x64 | [121368345684](https://github.com/Perseusxrltd/mnemion/actions/runs/40258369359/job/121368345684) | 64 |
| Windows ARM64 | [121368345683](https://github.com/Perseusxrltd/mnemion/actions/runs/40258369359/job/121368345683) | 64 |
| macOS ARM64 | [121368345666](https://github.com/Perseusxrltd/mnemion/actions/runs/40258369359/job/121368345666) | 64 |

Windows ARM64 used an ARM64 desktop with **x64 engine and database components
under emulation**. The other four targets' desktop, engine and database
architectures matched natively. These installations used disposable profiles;
public downloads and live update acceptance are separate gates.

The frozen [native telemetry probe](https://github.com/Perseusxrltd/mnemion/blob/bd3b212567d878c8b28c1d4c3eb8c86c47bb5311/studio/electron/native-telemetry-probe.ts)
and installed gate require all five new fields:

- `nativeTelemetryDisclosurePreview`: the actual Privacy page shows the fixed
  format example before acknowledgement, retaining a new undisclosed store.
- `nativeTelemetryAppAgentChoice`: app opt-out is visible through native controls.
- `nativeTelemetryPreviewClearedOnRefresh`: a native preference change refreshes
  the app and clears the displayed example without acknowledging disclosure.
- `nativeTelemetryNoAttemptDuringInspection`: inspection leaves no pending
  telemetry or spent attempt.
- `nativeTelemetryOptOutSurvivesRestart`: the installed app retains opt-out
  through its restart journey.

The [Intel Mac packaging job](https://github.com/Perseusxrltd/mnemion/actions/runs/40258369359/job/121368345735)
failed at volume detach; its installed-hosting step was **skipped**. The separate
[Intel supervision job](https://github.com/Perseusxrltd/mnemion/actions/runs/40258369359/job/121367072884)
also failed. These were the run's two failed jobs; their original evidence and
unproven causes remain in the [Mac reliability report](2026-10-26-macos-release-reliability.md).
The qualification therefore records `all_six_targets_in_this_receipt: false`,
`public_release_acceptance: false` and `l1_complete: false`. The candidate is
unpublished. This receipt provides **no 4.46.13 acceptance**.

## Remaining boundary

The [exact-packet requirement](../implementation/anonymous-product-telemetry.md#proposed-outbound-schema-and-payload-preview)
remains open. A deterministic format example does not establish inspection of
the actual reserved packet or its eventual guarded handoff. Full wire/resource,
production ingress/privacy and all-platform acceptance also remain open. No
requirement text or state changed; the full scope remains **66**.

| Original source-check log | SHA-256 |
| --- | --- |
| Python | `d7b3625b27dfeaa9c71a31f0e7a1a73ebf0bbef617815ee29ffc9607370d5627` |
| Browser | `a0654503d2e6afef0c6ef0d2c34a4312bd20eb9c61cd9f05fdca1cbb8e5f40d8` |
| Native control/wire | `f998fe02b384b42484080c0445fe73820b81c9689d3612fd2e7a3328bd990c8e` |

| Retained installed qualification evidence | SHA-256 |
| --- | --- |
| Five-target qualification receipt | `339174733a66eec15637309e9a12ba96520596f090c3bd2cd6eb5efa53c01617` |
| Linux x64 installed-hosting JSON | `cc76ef21efcba2441f12feea14d1fddc3bb39dbb407309e07a1173da3113b42a` |
| Linux ARM64 installed-hosting JSON | `d239020ae6cc4bac759cfa1097c442a60ddbfbb069e258bb7d6cd985ec357e84` |
| Windows x64 installed-hosting JSON | `b4377326b43de0120b4cce5bf35a1e1d881ee122561943e3407b960b21e63492` |
| Windows ARM64 installed-hosting JSON | `1606c6ac4497da79ff4c4e82da69124806f28752db4c2d6f6be7e477c8ea6728` |
| macOS ARM64 installed-hosting JSON | `c3397afa7ece9f86f486b6e72acff16b01ebb7eed1fbf275de5d3c76df0563d0` |
