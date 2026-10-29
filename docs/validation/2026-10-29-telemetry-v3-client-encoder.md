# 29 October 2026 — shared v3 client encoder

V08 stays Building. Collection, destination, and the release route stay off.
This note records the client summary encoder on
`grok/telemetry-v3-client-20261029`. It does not install a build, switch a
sender, or accept the fleet. The app version was not changed. 4.46.54 remains
the release already building from `2cd258274e96c9589191bf1a39276ab1e78eead6`.

## What was checked

Pinned interpreter:
`/home/jorqu/.local/state/mnemion-release/2026-10-10/release-venv/bin/python`.
TypeScript 5.9.3 was the copy already installed under
`/home/jorqu/mnemion-telemetry-v3-review-20261029/studio/electron/node_modules`.
Node was 22.22.0. No package install was run.

```text
python -m pytest tests/test_product_telemetry_v3.py -q --tb=short
19 passed in 11.65s

node tests/check_telemetry_v3_client_parity.mjs
v3 client parity 27 cases

python -m ruff check mnemion/product_telemetry/wire_v3.py tests/test_product_telemetry_v3.py tests/check_telemetry_v3_client_packets.py
All checks passed!

wsl -e /home/jorqu/mnemion-telemetry-v3-review-20261029/studio/electron/node_modules/typescript/bin/tsc --noEmit --strict --target ES2022 --module ESNext --moduleResolution bundler --skipLibCheck --types --pretty false studio/electron/telemetry-wire-v3.ts
(exit 0)
```

The 19 pytest results are the previous 16 v3 checks plus the failed-without-reason
regression, the fixed vector matrix, and the coin-before-contents check. The
27 parity cases are the same fixture in Python and TypeScript: clipped latency
counts, disabled groups, missing sensors, release and OS axes, an unlisted
release coordinate, and malformed cells, counts, duplicates, and coordinates.
`success` and `accepted` without a reason cell encode `no_failure`. `failed`
and `deferred` without a reason cell stay `sensor_missing`. A mixed
success-plus-failed queue can select either the supported `no_failure` mass or
`sensor_missing`, and it does not invent a reason. Scripted draws are refused
if they call `secrets.randbelow`.

## Not checked

Sender integration, disclosure and transport version switching, manual review,
installed resource gates, and a live collector were not run. The compiled
Electron bundle was not rebuilt here.
