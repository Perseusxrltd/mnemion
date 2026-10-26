# Product telemetry report-format preview

**Source validation, 26 October 2026.** Read-only format-preview component checks
passed. The app/native/browser controls now show a fixed synthetic example;
they do **not** inspect the actual next outgoing packet. V08 remains Building,
production collection/destination/route stay false/null/null, and the latest
published release remains 4.46.6. These source changes do not establish release
or installed-platform acceptance.

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
notification and discards late responses. These are source behavior changes;
the installed UI journey below remains pending.

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

## Planned installed acceptance and remaining boundary

The source [native telemetry probe](../../studio/electron/native-telemetry-probe.ts)
is wired into the [existing installed gate](../../studio/electron/scripts/smoke-installed-hosting.mjs).
It is intended to exercise the real Privacy page, native/app choice visibility,
an example shown before disclosure without spending an attempt, preview clearing
after an agent preference change, and opt-out persistence through restart.
**It has not yet executed on the native target matrix.** The earlier renderer
CI journeys do not qualify this newer source change.

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
