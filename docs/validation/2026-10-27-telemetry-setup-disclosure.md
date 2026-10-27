# First-time telemetry disclosure — 27 October 2026

The app now presents **Your privacy choice** during setup when a
collection-capable build needs the current disclosure. Previously, users had
to find the separate privacy page. The source change is based on
`05a9d8d19637a11f0aca9480e2ef928c18574424`.

**29 browser policy checks and ten compiled-browser UI checks passed.** The
current SDK and frontend built successfully. These results qualify the recorded
source controls and browser fixture, not installed native delivery, resources,
production ingress or full telemetry. V08 remains **Building**; production
collection/destination/route remain **false/null/null**, with release CAs empty.

## Behavior

[App entry](../../studio/frontend/src/App.tsx) loads the
[setup dialog](../../studio/frontend/src/workspace/TelemetrySetup.tsx) only when
the release enables collection and declares its destination. Privacy, standalone
help and OAuth-consent routes are excluded. The unavailable production build
does not load this setup chunk or start its status request.

The dialog shows the release disclosure's purpose, included and excluded data,
destination, bandwidth limit and choice scope. The default checkbox is checked;
**Save and continue** explicitly saves it. Unchecking before saving or selecting
**Disable product telemetry** saves an opt-out. The
[choice boundary](../../studio/frontend/src/workspace/telemetry-setup.ts) carries
the displayed revision/generation and acknowledges only the displayed disclosure
version. The existing policy transaction rejects a stale enable.

**Not now**, Escape and the details link do not save a choice or acknowledge
disclosure. Workspace setup remains usable. A saved choice or dismissal removes
the setup listeners for that app load; an unacknowledged disclosure can appear
after a later reload. Existing opt-outs, company restrictions and browser privacy
signals do not reopen the opt-in flow. While the notice is open, coalesced
focus/storage refreshes preserve an unsaved checkbox choice. No polling timer or
telemetry observation was added for these privacy actions.

## Recorded checks

The policy selection passed **29 tests**, including four new cases using the
actual browser policy store: explicit acknowledgement, persistent opt-out,
rejection after a newer opt-out, and refusal for unavailable/restricted/unreadable
or mismatched disclosure state.

One controlled UI journey used **Chrome 144.0.7559.96 on Linux**, the compiled
source app, an isolated browser session and two loopback static servers. Only
the private fixture copy changed `collection_available` and a synthetic
`.invalid` destination. The production configuration and transport route were
unchanged; no report delivery was requested. The ten completed checks were:

| Check | Observed result |
| --- | --- |
| Fresh disclosure | Visible default; initial focus on the explanation; no telemetry state created. |
| Pending choice and mobile bounds | An unsaved unchecked choice survived focus refresh. At a 390 × 844 viewport, the scrolling dialog was 356 × 812 at x=17/y=16. |
| Explicit save | The acknowledged default survived reload; eight subsequent focus events caused no setup choice reads. |
| Direct disable | Opt-out survived reload with disclosure version zero. |
| Deferral and Escape | Neither acknowledged disclosure or created telemetry state; workspace fields remained usable. |
| Details navigation | Reading privacy controls and returning to setup preserved session deferral and empty state. |
| Concurrent opt-out | A valid older-client opt-out arriving without a UI storage event defeated a stale displayed enable; its revision and disabled choice remained intact. |
| Company policy | A served restrictive policy suppressed the opt-in dialog and created no telemetry state. |
| Browser privacy | A browser privacy signal suppressed the dialog and created no telemetry state. |
| Inactive release | The actual unchanged release configuration loaded no setup chunk and created no telemetry state. |

The journey observed **370 GET requests, zero external requests, zero network
write requests and zero page errors**. The browser closed and both owned static
servers stopped. Geometry and accessibility-tree observations are not a physical
mobile-device or complete visual-accessibility qualification.

The first frontend build failed because a reused local SDK `dist` did not match
the current SDK source. The original failure is retained. Isolating that local
dependency and building the unchanged current SDK resolved the build without
an SDK source change; the earlier 29 successful policy tests were not repeated.

The existing compiled Electron review journey now checks and explicitly defers
this initial notice before continuing its original approval/delivery steps.
Its acceptance list requires that new check. This harness adaptation is
syntax-checked; that separate native source-app journey was not replayed for
this UI batch and is not included in the ten browser results above.

## Evidence and remaining work

The private `2026-10-27-telemetry-setup-disclosure` evidence set retains the
original plan, source-input hashes, build failure and correction, executed
browser script, complete result and cleanup receipts.

| Receipt | SHA-256 |
| --- | --- |
| Source qualification | `b68a39b1afec45ec7bda341b8070ca53983b299f30667a06dc82538256af1599` |
| Browser journey | `5bc562e0da3e464e054cbfa81fa871a0ae3406652a401b174f6ff9745f2b511a` |
| Browser/source comparison | `4a6201f09f0107069fa69e810069bac7353eab4c640a683bab7be2af0380c3e3` |
| Policy checks | `e879c0467074e924e92b9af8e780751f6ce070f3fe8615dc08df8b00a52c7e49` |
| Current SDK/frontend build | `a2bf6a1af62f10e68dad0abe2a5d67470117582d84e711c478840e3e44f6c06d` |

All 66 requirements, earlier failures and the unchanged **2 MiB / 0.5%** resource
ceilings remain retained. Final native/agent/headless journeys, real update
persistence, complete wire and resource costs, deployed/provider privacy and
aggregate utility/attack acceptance remain open in the
[acceptance ledger](2026-10-27-telemetry-acceptance-ledger.md). This source/UI
follow-up requests no separate native release and does not enable collection.
