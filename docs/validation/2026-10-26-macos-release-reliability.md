# Intel Mac packaging and managed-update validation

**Source follow-up, 26 October 2026.** Two Intel Mac jobs failed in the frozen
4.46.12 [release run 40258369359](https://github.com/Perseusxrltd/mnemion/actions/runs/40258369359),
source `bd3b212567d878c8b28c1d4c3eb8c86c47bb5311`. The source changes below are
subsequent work, not part of that frozen candidate. Other platform jobs were
still running at this checkpoint; this report does not assign a terminal result
to the whole run. See [release status](../RELEASE_STATUS.md) for availability.

## Original failures

The [Intel packaging job 121368345735](https://github.com/Perseusxrltd/mnemion/actions/runs/40258369359/job/121368345735)
failed while `dmgbuild` detached its temporary installer volume. The recorded
error was `Unable to detach device cleanly: hdiutil: couldn't eject "disk2" - Resource busy`.
The log does not identify which process held the device busy.

The [Intel supervision job 121367072884](https://github.com/Perseusxrltd/mnemion/actions/runs/40258369359/job/121367072884)
failed in
`test_signed_locked_install_and_failed_update_preserve_real_accepted_memories[False]`
at the `/openapi.json` read, with `httpx.ReadError: [Errno 54] Connection reset by peer`.
The preceding update, connector handoff, service readiness and process-identity
assertions had completed. The job recorded **107 passed, one failed and one
skipped**. Its failure prevents claiming the full journey passed; the log does
not establish the underlying TCP-reset cause.

## Scoped source changes

The [pinned Intel vendor archive](https://github.com/electron-userland/electron-builder-binaries/releases/download/dmg-builder%401.2.5/dmgbuild-bundle-x86_64-75c8a6c.tar.gz)
was downloaded and hash-verified, then its actual packaged Python entry point
and core were inspected without executing them. The CLI defaults
`--detach-retries` to **five** and passes that value explicitly to the core,
overriding the core's **twelve** default attempts.

The new [dmgbuild wrapper](../../studio/electron/scripts/dmgbuild.mjs), selected
through the supported `CUSTOM_DMGBUILD_PATH` in
[builder configuration](../../studio/electron/builder.config.cjs), retains the
pinned, checksum-verified vendor tool and explicitly supplies
`--detach-retries 12`. It uses the vendor's existing detach backoff and propagates
nonzero exit status and cancellation. Native
packaging must still show whether this change addresses the observed failure;
it does not establish what held the original volume busy.

Only the affected [managed-update test](../../service_tests/test_managed_service.py)
now uses `httpx.Limits(max_keepalive_connections=0)` so its assertions across
listener replacements and connector handoffs use fresh connections. It retains
the five-second request timeout, readiness/process checks, connector checks,
backup/rollback assertions and exact retained-memory assertions. It adds no
request retry and changes no production HTTP client. Avoiding pool reuse is a
fixture refinement, not proof that a stale pooled connection caused the original
reset.

## Validation boundary

Wrapper and builder-configuration syntax checks passed. The exact packaged
Python CLI accepted the explicit twelve-attempt argument and forwarded it with
unchanged settings, volume and output arguments to an isolated stub; no native
Mac binary or disk command ran in that compatibility check.

The focused `legacy_previous=False` managed-runtime test passed on Linux with
real PostgreSQL, locked runtime installation, connector handoff, a successful
update and an intentionally failed following update. The test retained its
accepted-memory and rollback assertions. The check command took **82.501 seconds**.
This local result is separate from Intel Mac execution. No corrected native
packaging or Intel managed-update pass is claimed. The original failed logs
remain preserved.

All **66 requirement texts and states** remain unchanged. V08 stays **Building**;
production telemetry collection is `false`, with destination and route `null`.

## SHA-256 provenance

Original logs remain private. Public tool URLs and these hashes identify the
inspected evidence without publishing raw logs or runner paths.

| Evidence | SHA-256 |
| --- | --- |
| Original Intel packaging log | `ff26a4fb39c99d7ad0ee3f170d93323802134e0305acb6ebe41de2b6d5b91b30` |
| Original Intel supervision log | `732e8c63fc3c36567cefd0c21e52b4e6a13d565c5f0b32e0d298de67b13a9565` |
| Pinned vendor source receipt | `d75664f043f9f9b0c095b28cf3017c55fe80de94441839e569a36bf810210a5a` |
| Pinned Intel tool archive | `1664972f9cc2d6e8fce3b63e42cd30078aff602669c5856939c4519921200433` |
| Packaged CLI source | `a0425f0d2cee9b1c8768e20e4bb0a92c82d2fbc46aaaa9c278cbcd02e88830d5` |
| Packaged core source | `f1c36db50b758f895a8c48ff2bd18938d76859bf35d648986a9b22ca489bd624` |
