# Capture display scheduling and service bootstrap

The reviewed source stops a display timer while its page is hidden and corrects
the supervised-host setup instructions. Whole-product resource acceptance
remains open under the [runtime efficiency contract](../implementation/runtime-efficiency.md).
Production telemetry remains disabled.

## Capture age display

Actual Windows Grok Build produced commit
`60ceededd3545664e21056fa4becc7c63c35c8de`, adopted unchanged as
`2af0b8172b625dd61df45f8c751206f8133e7971`. It changes
[`CaptureStatus.tsx`](../../studio/frontend/src/workspace/CaptureStatus.tsx).

When coverage is absent, the effect creates neither a timer nor a visibility
listener. With coverage present, a visible page has one 60-second interval;
a hidden page keeps only its listener. Hiding clears the interval. Returning
to the page refreshes the age immediately and arms one interval. Cleanup first
marks the closure inactive, then clears the interval and removes the listener,
so a late tick or visibility callback cannot update or rearm it. React's
setup-cleanup-setup cycle uses a fresh closure.

Age formatting, capture, delivery and queue data are unchanged. Coverage first
appearing while the page is already visible still uses the existing one-minute
cadence. No new dependency, sampler or shared scheduler was added.

The original Windows frontend typecheck executed once and exited with code 1:
the existing dependency cache lacked `@mnemion/client`'s generated
`dist/index.d.ts`, producing missing-module and downstream type errors.
That result is preserved. Its temporary dependency junction was removed.

Astra then checked the adopted source once with the existing complete WSL
frontend dependencies and the project's strict configuration:

```sh
node studio/frontend/node_modules/typescript/bin/tsc \
  -p studio/frontend/tsconfig.json --noEmit
```

It passed in 24.462 seconds. No dependency installation, repeated successful
check or new implementation-mirroring test was needed. This source/type check
does not measure CPU, RAM, battery use or installed-app behavior.

## Supervised-host installation

The [host recovery](../service/host-recovery.md),
[supervision](../service/supervision.md) and
[managed update](../service/managed-updates.md#initial-installation) guides now
share the [locked uv setup](../../README.md#run-the-service). The older
standalone `pip install` examples could fail dependency resolution:
FastEmbed 0.9.0 declares Pillow below 13, while Mnemion deliberately retains
the reviewed Pillow 13 security pin through uv's lock override.

The correction retains both dependency pins and the existing managed staging
behavior. Initial source installation uses the locked environment with the
`supervision` extra, then builds Studio. Intel Macs retain the separately
verified native cryptography wheel step after locked dependency setup. The
guides no longer point to stale 4.0.8 or 4.13.0 installation examples.

The existing managed updater already prepares locked dependencies before
installing the verified application wheel. This is a documentation correction;
it adds no new runtime compatibility claim, host migration or user-app restart.
