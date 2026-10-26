# Product telemetry report-format preview

**Historical 4.46.12 checkpoint, 26 October 2026.** Format-preview
component checks passed, followed by qualification of five installed native
targets from the frozen 4.46.12 candidate. The controls show a fixed synthetic
example; they do **not** inspect the actual next outgoing packet. Intel Mac and
public-release acceptance remained open for that candidate. V08 remains Building and
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

## Review-clock foundation

**Later source checkpoint, 26 October 2026.** Published
[4.46.13](2026-10-26-44613-native-acceptance.md) subsequently qualified all six
installed control targets and all six public automatic-update targets. The new
clock foundation is **not included in that release**. Actual packet staging,
review UI and approval remain unimplemented; the fixed synthetic preview and
`outbound_state: "not_inspected"` are unchanged.

[Python review clocks](../../mnemion/product_telemetry/review_clock.py), the
[native C/Node-API reader](../../mnemion/product_telemetry/native/network-node.c)
and the [portable lifetime core](../../studio/electron/telemetry-review-lifetime.ts)
validate an original lifetime of at most **15 minutes**, bounded further by
observation expiry. Repeated checks cannot renew it. Missing/changed epochs,
wall or elapsed rollback, malformed values and expiry are refused. Native epoch
values are local control only; ordinary reads cannot initialize the Windows
volatile marker. No epoch is an analytics identity or outbound field.

[BrowserReviewClock](../../studio/frontend/src/workspace/telemetry-review-clock.ts)
shares an epoch only between live same-origin pages, using Web Locks and bounded
BroadcastChannel discovery. Read-only calls cannot open a channel or initialize
state; there is no worker or persistent storage. The last peer's disappearance
prevents a later page from reviving that lifetime.

Focused Linux checks passed **68 Python tests (8.19 s)** and **18 Node tests
(1.543 s)**, including the compiled native clock and existing related coverage.
Six browser-source coordination tests passed **(2.089 s)** using real **Node
BroadcastChannel** instances with injected clocks and Web Locks; they are not an
actual Chromium journey. Electron build and frontend type checking passed.

Subsequent **Windows x64 Python 3.13.11 / Node 25.2.1** component checks found no
epoch on read-only calls, then verified a shared epoch across runtimes after
explicit initialization. **Linux Python 3.12.3 / Electron 44.9.3 / Node 24.22.0**
also verified the shared native clock. The receipts contain availability and
comparison results, not the epoch or raw CPU counters. These probes include the
network/CPU helper and do not isolate the clock's timing or RSS cost.

The original Windows link failure for `QueryInterruptTime` is retained; adding
the required `OneCore.lib` resolved the x64 link. Local ARM64 cross-compilation
stopped because the workstation lacks ARM `LIBCMT.lib`, not because a source
defect was established. Windows ARM64 and macOS runtime checks remain open for
their authoritative runners. Actual browser integration and installed clock
acceptance are also unqualified. These checks do not establish whole-machine
snapshot rollback protection, resource or privacy acceptance. All 66 requirement
states remain unchanged; V08 is Building and collection/destination/route remain
false/null/null.

| Foundation check log | SHA-256 |
| --- | --- |
| Python selection | `b82fb74f1bf0231b2d33b81f22af902592cee8e4f32ebf123bdaf3703b50b761` |
| Node selection | `dc63db98d14ea64f334d1397f7ad65531ee391fc9148f31e91960fb423afff05` |
| Browser-source coordination | `7e68c5597d0073d4ae9f515af2ee1018cbbe5e73880a2fcce644a34e8dfc2a7b` |
| Electron build | `5e8be4ed286ae0fc76d4c1440a631a5664a43b83fa432d25fc79d5a278b966f6` |
| Windows x64 read-only component | `53f4af8ea73faefa2c5deecaa0004642c915483da9dca0c6159e6ff4c2c12a58` |
| Windows x64 initialized component | `b6b9a6ad4ceb7d85be0b3dce15471944d6fd9f98314ae56ae31d84188bb42684` |
| Linux Electron component | `046c5545e388c931b8bc6232309d20b72d9f78fd89cc150e1fe183534063f8f9` |

## Later report-review source

The subsequent [report-review checkpoint](2026-10-26-telemetry-report-review.md)
adds actual staging, review UI and approval in unreleased source. Its own source
tests, Python/Node handoff checks and isolated Chromium controls passed; full
interactive privacy/utility, resources and installed acceptance remain open.
It records later macOS Intel/ARM clock-component qualification and direct
Linux/Windows x64 headless clock comparisons. The new direct macOS Python path
is still pending. The clock-only limitations above describe that earlier stage.
