# Firefox and WebKit telemetry journeys

30 October 2026. One manual Linux workflow drives the normal built Studio
frontend through a real private memory API and the existing browser delivery
owner. It does not activate production collection, accept a resource budget,
or qualify native Safari.

Dispatch `.github/workflows/telemetry-browser-journeys.yml` with the exact
reviewed source commit. The job checks out that commit, installs the pinned
Playwright package already used by the renderer diagnostic, and installs
Firefox and WebKit on the hosted runner. It does not install browsers on a
workstation or change a running Mnemion host.

## What the journey does

The probe copies the tracked source and writes the reviewed loopback bake into
that copy only: `mnemion/product_telemetry/disclosure.json` and
`mnemion/product_telemetry/transport-route.json`. The checkout copies stay
`false` / `null` / `null` / empty certificate roots. `npm run build` in the
copy compiles that destination into the ordinary frontend. The production
files are hashed before and after.

A TLS collector and the real service stay up while the frontend build and the
browser processes run. The service serves the built app and its company-policy
route. Each engine gets a new empty profile and one pass, not a retry:

1. Save the disclosure from the privacy dialog.
2. Pause reports for manual review before any workspace action.
3. Join the fixture with its real address and key.
4. Save a memory whose content contains `PRIVATE_BROWSER_CANARY`, fetch
   that memory, and run an exact-text search.
5. Inspect the next report, approve those exact bytes, and wait until the
   collector has that one 25-byte v3 body.
6. Turn product telemetry off, reload the same profile, and check that the
   opt-out, manual review, and the spent attempt are still there.

Missing `PressureObserver`, heap memory, and network information are recorded
as `unavailable`. A missing sensor is never stored as zero, and the journey
does not invent a nominal pressure or a network tariff. WebKit's version is
Playwright's WebKit engine on Linux, not Safari on macOS.

Browser `fetch` cannot load the certificate list in the baked route. The
Playwright context accepts the disposable loopback certificate
(`ignoreHTTPSErrors`). The collector still presents that certificate. This is
not a telemetry admission bypass: pressure, heap, network, disclosure, manual
review, and the traffic budget keep their normal decisions.

## Evidence

`output/telemetry-browser-journeys/receipt.json` keeps the source hashes,
phases, per-engine versions and sensor states, API success counts, whether the
reviewed body matched the received body, the original failure text, cleanup,
and `resource_acceptance: false` / `production_collection_available: false`.
The private key and workspace key are not written there. A local source check
does not mean the journey passed. Only this hosted job can say that.

## Limits

Installed apps, whole-wire cost, provider privacy, and resource acceptance
remain separate. The workflow is manual. It does not change release workflows
or published installer feeds.
