# 29 October 2026 — shared v3 client encoder

V08 stays Building. Collection stays off (`collection_available` false), the
disclosure destination stays null, and `transport-route.json` stays schema
version 2 with `address` null. The live request path is `POST /v3/report`
with a 25-byte body. The packaged wire resource name is `wire-v3`. The app
version was not changed. 4.46.54 remains the release already published from
`2cd258274e96c9589191bf1a39276ab1e78eead6`.

## Codec receipt (not rerun as a suite)

Pinned interpreter:
`/home/jorqu/.local/state/mnemion-release/2026-10-10/release-venv/bin/python`.
TypeScript 5.9.3 was the copy already installed under
`/home/jorqu/mnemion-telemetry-v3-review-20261029/studio/electron/node_modules`.
Node was 22.22.0. No package install was run.

```text
python -m pytest tests/test_product_telemetry_v3.py -q --tb=short
19 passed in 11.65s
```

That 19 is the encoder receipt from before R3 added two tests to the same
file. It was not rerun after those two tests or after the preview helpers.
`prepare` and `decode` were not edited. The later additions are
`packet_matches_groups`, `groups_remain_permitted`, `preview`, and
`format_example`.

Portable parity command, with no private path inside the script:

```text
node tests/check_telemetry_v3_client_parity.mjs
```

This checkout's run set `MNEMION_TEST_TYPESCRIPT` and `MNEMION_TEST_PYTHON`
to the pinned copies above and printed `v3 client parity 27 cases`.

Earlier, and not rerun: Ruff on `wire_v3.py`, `tests/test_product_telemetry_v3.py`,
and `tests/check_telemetry_v3_client_packets.py` passed, and strict `tsc` of
`studio/electron/telemetry-wire-v3.ts` exited 0.

## Sender, review, and transport checks

Python, still the pinned interpreter. First run of delivery, inspection,
preview, endpoint, and transport: 8 failed, 103 passed in 50.63s. Every
failure was the transport test peer reading 4 bytes while `Content-Length`
was 25. After the peer reads the declared length, transport alone:
39 passed in 27.16s. Ruff on `review.py`, `policy.py`,
`tests/test_product_telemetry_inspection.py`, and
`tests/test_product_telemetry_preview.py` passed.

Electron `tsc` alone does not build `dist/telemetry-network.node`. The first
run of delivery, transport, and owner was 69 passed and 2 failed. Both
failures were native approval seeing `expired` because that helper was
absent and the clock was null. A temporary Linux `systemReviewClock`
fallback then made the same three files 71 passed, 0 failed. That 71 is
the fallback receipt. It does not qualify the production clock. The
fallback was removed. `studio/electron/telemetry-network.ts` matches HEAD:
a missing or invalid helper returns null and does not read the OS clock
in JavaScript.

`node studio/electron/scripts/build.mjs` with `MNEMION_BUILD_PYTHON` set
to the pinned interpreter exited 0. It compiled the current Electron
sources, built `studio/electron/dist/telemetry-network.node`, and copied
the resources. The recovery-kit check did not stop that build. The
temporary `node_modules` link was removed afterward.

```text
node --test --test-name-pattern "holds native delivery|changed full review scope" studio/electron/scripts/test-telemetry-delivery.mjs
```

With `MNEMION_TEST_PYTHON` set to the same interpreter: 2 passed, 0 failed.
The other 69 native checks were not rerun after the fallback was removed.

```text
node --test studio/frontend/scripts/test-telemetry-delivery.mjs studio/frontend/scripts/test-telemetry-inspection.mjs
```

74 passed, 0 failed. The first load failed before any test: Node 22's
`navigator` is getter-only, so `Object.assign` could not set it. The fixtures
now use `Object.defineProperty`. That run includes the corrupted-automatic
salvage regression. Browser delivery imports `wire-v3.json` and `TelemetryWireV3`.

## Still open

`server.py` is still only `/v1/report` and was not edited. Fleet files
(`collector_v3.py`, `maintainer_v3.py`, and the operator docs) and the probe
files from `54044592a104aa227ad0c8b2b4611dfe9f509658` were not edited.
`studio/electron/scripts/test-telemetry-store.mjs` and
`studio/frontend/scripts/test-product-telemetry.mjs` still pass disclosure
version 1 and were not run. `studio/electron/scripts/test-telemetry-wire.mjs`
still reads `dist/telemetry-wire-v2.json`. `native-telemetry-probe.ts` still
expects `AgAHAA==`. No full release matrix, no app resource trial, and no
live collector. All 66 requirements remain.
