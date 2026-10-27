# Desktop request cancellation — 27 October 2026

This operational source hotfix is prepared on
`ed69de9abe0185b9def4923daf406b3cca2c1e21`. It addresses desktop requests that
remained pending after their SDK deadline or caller cancellation. Focused source
and actual Electron bridge checks passed. Installed release qualification remains
pending; no installed or full telemetry acceptance is claimed.

## Retained failures

Two original regression checks reproduced the defect: an SDK deadline during
a stalled native request, and a caller `AbortSignal` while waiting for the
native reply. Both observed `still_waiting` where `rejected` was required.
The original `checks/cancellation-before.log` remains in the private
`2026-10-27-desktop-request-cancellation` evidence; these are two expected
regression failures, not passing acceptance checks.

## Current source correction

- The [frontend adapter](../../studio/frontend/src/workspace/native.ts)
  settles the caller once when cancellation fires and asks the native bridge
  to cancel the request. It retains handlers for late native success/failure,
  so neither can replace the cancellation or become an unhandled rejection.
- [Native request ownership](../../studio/electron/service-requests.ts)
  associates each local token with its renderer owner. It bounds active requests
  to 128, rejects duplicate active tokens and retains a 60-second native abort
  timer. Cancellation does not free a slot before that request actually settles.
  Tokens remain local IPC metadata: they are never server fields, telemetry
  values, workspace identities or idempotency keys.
- The [service bridge](../../studio/electron/service-bridge.ts) passes the
  owned signal to native networking and response-body reads. Main-frame
  document navigation, renderer destruction/crash and accepted application
  shutdown cancel the corresponding outstanding requests.

Existing session rotation may finish its credential lookup after cancellation;
the bridge checks cancellation before sending subsequent memory work. Session
rotation and retry/idempotency rules remain unchanged. Cancelling local work
cannot reverse a mutation already performed by the server.

## Qualification and scope

All **32 focused checks** passed: six frontend cancellation checks, 11 native
request-lifetime/network checks and 15 telemetry-coverage checks. The Node checks
had no skips. They cover prompt SDK deadlines and caller cancellation, preserved
abort reasons, late replies, listener cleanup, unsafe mutation retry behavior,
renderer ownership, duplicate tokens, bounded outstanding work, terminal shutdown
and actual HTTP connection closure. Existing session-rotation/redirect behavior
also passed. SDK, frontend and Electron builds passed.

The [installed probe](../../studio/electron/native-service-request-probe.ts) was
also exercised through the real compiled renderer/preload/main bridge and
Electron networking on Linux x64 (Electron 44.9.3 / Node 24.22.0). Its three
results passed: cancellation before headers, cancellation during the response
body, and local cancellation tokens absent from server traffic. All 94 compiled
inputs remained unchanged; the disposable profile was removed after success.
The existing six-platform installed release gate now requires these same results
within its existing capture-preview launch. Local source-app success does not
substitute for the pending installed-platform results.

The first local probe launcher timed out during startup without a product result.
The private launcher used a top-level readiness await; switching that launcher to
a readiness callback let Electron finish module loading. The corrected launch
passed with the same 94 compiled inputs and binary. Both observations remain in
the private evidence (`native-bridge/qualification.json`,
`native-bridge-callback-start/qualification.json` and
`native-bootstrap-correction.json`); neither the initial timeout nor the two
original regression failures was overwritten.

Generated coverage contains 94 mapped categories and 637 action rows: 364 mapped,
265 excluded, eight delegated and zero unmeasured. `service:cancel` is a delegated
transport alias; it creates no extra telemetry action and collects no request
token. This declaration is not full runtime coverage acceptance.

The selected 4.46.37 release also carries the already-main
[Python action-timing correction](2026-10-27-telemetry-agent-timing.md), which
includes optional contribution/policy reads in action latency while preserving
the original privacy snapshot and completion rules. Its earlier evidence remains
separate from cancellation qualification.

All 66 requirements and their states remain unchanged. V08 remains **Building**;
production collection/destination/route stay **false/null/null**, with release
CAs empty. The strict **2 MiB added RSS / 0.5% of one core** ceilings, prior
failed evidence and requirement scope remain unchanged. Installed, resource,
provider and privacy acceptance remain open.
No resource saving is established and no new resource measurement is selected.
