# Live release-catalog source review — 30 October 2026

The v3 collector can adopt new release coordinates without a collector upgrade
or restart. Grok's implementation was adopted with attribution in
[`35cc1e042c9d32bb9d111e82523d0f694ddf06ab`](https://github.com/Perseusxrltd/mnemion/commit/35cc1e042c9d32bb9d111e82523d0f694ddf06ab),
followed by the parser correction in
[`408a56ace3730b544d762d8980204280fc15cc5c`](https://github.com/Perseusxrltd/mnemion/commit/408a56ace3730b544d762d8980204280fc15cc5c).
This report qualifies the reviewed source and local fixtures. Production
collection remains disabled, hosting is undecided and no collector is deployed.

## Behavior

The separate [catalog oneshot](../../deploy/collector/mnemion-telemetry-catalog.service)
and [daily timer](../../deploy/collector/mnemion-telemetry-catalog.timer)
fetch only the fixed public Mnemion GitHub
[`wire-v3.json`](https://raw.githubusercontent.com/Perseusxrltd/mnemion/main/mnemion/product_telemetry/wire-v3.json).
The [sync code](../../mnemion/product_telemetry/release_catalog.py) refuses
redirects, caps the download at 256 KiB, validates at most 32 listed release
coordinates against the running wire contract, and atomically writes
`release-catalog.json`. It stores public release metadata only. The bounded
oneshot has its own outbound connection permission and no collector credentials.
The collector retains its no-connect sandbox and performs no outbound fetch.
The optional v3 drop-in starts the catalog timer; the legacy default remains.
Installation and mode changes are in the
[operator guide](../implementation/anonymous-product-telemetry-collector.md#deployment-template).

The collector reads the local snapshot at process startup and after sealing
the previous week when a new reporting week opens. Within a running process,
refreshing the file preserves the open week's mapping and counters. Closed
reports retain their own domain. A version absent from the snapshot remains
`unlisted` until a later adopted snapshot includes it; prior reports are not
reclassified. Missing, malformed or stale metadata falls back to the last
valid adopted snapshot, or the bundled allowlist when none has been adopted.
An ordinary restart still discards the unsealed in-memory week.

The change adds no identity fields or persistence of raw summaries or open
counters. The 25-byte packet, 19 metrics, release-or-OS choice, publication
noise and eight-week retention remain unchanged. Updating release coordinates
does not update metric definitions or packet layout.

## Retained failure and correction

Astra's review of an uncommitted Windows candidate, recorded by its module hash,
reproduced a `RecursionError` from a 32,001-byte deeply nested JSON file below
the 64 KiB local-file cap. That candidate was not pinned to a Git commit.
The correction bounds reads from the opened handle, normalizes parser failures
and retains the previous or bundled catalog. The regression fixture verifies
fallback at startup and rollover,
continued packet acceptance, and publication of the already sealed week exactly
once. Malformed metadata cannot interrupt that publication path.

The original Windows interpreter lacked Starlette and Uvicorn. A follow-up
using import stubs reported six passes and two Windows private-path failures;
it is not accepted qualification. Those original records remain retained.
The later Linux result below supplies the scoped qualification.

## Recorded validation

On source `408a56ace3730b544d762d8980204280fc15cc5c`, **nine selected tests passed
in 2.25 seconds** in the existing Linux release environment, with real
**Starlette 1.7.0** and **Uvicorn 0.54.0**, and no import stubs. The six source
and test inputs remained unchanged during the run. Ruff found all six Python
files already formatted; lint passed and the parsed AST remained unchanged.

The selection in [v3 tests](../../tests/test_product_telemetry_v3.py) and
[operator tests](../../tests/test_product_telemetry_v3_operator.py) covers:

- Startup and weekly adoption, preservation of open counters and the closed
  report's domain, and mapping unknown versions only after adoption.
- Missing, malformed and stale fallback, including deep JSON and the bounded
  local read; failed synchronization preserves the prior local file.
- Existing release-coordinate meaning, immutable closed-report interpretation,
  observable publication failure without resealing, and quiet-week pruning.
- Separate sync/service wiring, fixed-source validation, and preservation of
  the legacy default and both report stores.

The sync fixtures supply an HTTP response and inspect shipped unit definitions.
They do not perform a live GitHub download or start the catalog systemd service.
These source checks do not qualify deployed hosting, public ingress, provider
privacy, live fleet usefulness or installed resource budgets.

## Remaining acceptance

The [client disclosure](../../mnemion/product_telemetry/disclosure.json) remains
`collection_available: false` with a null destination; the
[release route](../../mnemion/product_telemetry/transport-route.json) has a null
address and an empty CA list. V08 stays Building and all 66 requirement texts
and states are preserved. No public telemetry release or completion email
occurred.

Corrected installed-resource comparison
[41056963518](https://github.com/Perseusxrltd/mnemion/actions/runs/41056963518)
on `aae0f9e02f15110e751dc203df5ef027c9537479` completed with all six resource
jobs failing. Its workload scope and failure causes remain under review;
resource acceptance stays open. Original run
[41039553671](https://github.com/Perseusxrltd/mnemion/actions/runs/41039553671)
remains six preparation failures, zero completed workload cases and 36 rejected
placeholder claims. Earlier scoped delivery passes cover six targets across
four sources. Their evidence and limits remain in the
[installed journey report](2026-10-30-telemetry-installed-driver.md).
