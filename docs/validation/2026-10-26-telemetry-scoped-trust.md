# Release-owned telemetry TLS trust — 26 October 2026

This source qualification covers the working patch based on
`d2e55fbf12400004c8e931a8e53a492e46a279c5` (4.46.26), intended for 4.46.27.
It does not establish publication, installed application behavior or resource
acceptance. V08 remains Building; all 66 requirements and their states remain
unchanged.

## Source contract

[Route version 2](../../mnemion/product_telemetry/transport-route.json) adds
`certificate_authorities`: one or two public PEM CA certificates for a usable
native/Python route, each at most 4,096 bytes. The unavailable release retains
`collection_available: false`, `destination: null`, `address: null` and an empty
authority list. Catalog, disclosure, wire format, approved packets and allowances
are unchanged.

The [Python route reader](../../mnemion/product_telemetry/endpoint.py) and
[native reader](../../studio/electron/telemetry-route.ts) bound the metadata to
16 KiB, require the exact version-2 fields, reject duplicate or malformed PEM
envelopes and retain immutable trust. Envelope validation does not load TLS and
is distinct from parsing and checking CA certificates before a connection.

The [Python sender](../../mnemion/product_telemetry/transport.py) supplies explicit
`cadata`; the [native sender](../../studio/electron/telemetry-transport.ts) creates
an explicit secure context. Both use only the release authorities, with no
ambient/system/extra-root fallback. Missing or invalid trust prevents connection.
Certificate-chain and hostname verification and minimum TLS 1.3 remain required.
Connections still use the release-owned literal IP, with the disclosed hostname
as the certificate identity. Browser TLS remains unchanged.

The existing five-second reservation deadline, 32,768 combined charged TLS-byte
limit, 2,048-byte response-header cap, spending limits, current-consent and
generation checks, cancellation and cleanup remain in force. Charged TLS bytes
are not a whole-wire qualification. No retry, timer, daemon or model call is
added. Existing review binding to destination and route address stays intact;
no CA digest or identifier enters the packet or telemetry.

## Completed source checks and retained failures

The private `2026-10-26-telemetry-scoped-trust` evidence set retains the declared
plan, original logs and each resumed receipt:

| Receipt | Recorded result and scope |
| --- | --- |
| `checks/scoped-trust-focused.json` | Formatting passed; Ruff stopped on three F811 imported-fixture name collisions. Functional checks had not run in this attempt. Fixture wrappers were corrected. |
| `checks-r2/scoped-trust-resumed.json` | Ruff passed. Python reported 77 passed and one failed: the synthetic two-authority rotation fixture used the same `localhost` issuer name without key IDs. |
| `checks-r3/scoped-trust-remaining.json` | Only the formerly failing Python case reran and passed after changing the alternate fixture issuer to `other-test-authority`. Electron build passed. The actual local Electron binary ran 54 tests with `ELECTRON_RUN_AS_NODE=1`: all passed, zero skips/failures. |
| `checks-final/independent-issuer-refusal.json` | The negative ambient-trust Python case passed again with the corrected distinct issuer, excluding the original issuer collision as the explanation for that refusal. This repeat is not added to the distinct count. |

The trust selection comprises **78 distinct Python cases and 54 Electron-runtime
cases**. Fixture corrections did not relax the runtime contract. The selected
Python endpoint,
transport, preview and inspection checks and Electron transport, delivery and
owner checks include real local TLS, issuer overlap, ambient-only trust refusal,
hostname verification and existing privacy/cancellation fences. The one-authority
Python delivery context reports exactly
`cert_store_stats() == {"x509": 1, "crl": 0, "x509_ca": 1}`; actual certificate
and hostname verification remain enabled.

These are local source/component checks, including the actual Electron runtime
in Node mode. They are not an installed desktop/UI journey, a six-platform
qualification, a resource measurement or production-ingress/privacy acceptance.
No new browser or model result is credited.

## Windows consent-test deadline correction

The original 4.46.25
[Windows ARM job 121778341345](https://github.com/Perseusxrltd/mnemion/actions/runs/40376743057/job/121778341345),
source `4779cf11fa1b090f8ff7c0430558626c53617d36`, recorded **475 desktop tests
passed, one failed and two skipped**. In `test-telemetry-store.mjs`,
`workspace restoration cannot reuse a result after a real cross-runtime opt-out and reenable`
failed with `0 !== 1` at the original line 173. Packaging was then skipped, so
the missing generated-content scan receipt was downstream of the test failure.
The original job JSON and log remain retained as
`windows-arm64-121778341345.{json,log}` in the same evidence set.

A single local reproducer used the actual Electron binary in Node mode and
delayed completion of the real `store.snapshot()` by 75 ms. It reproduced the
same assertion. `deadline-reproduction/late-real-snapshot.log` and its receipt
retain that expected failure. This establishes a plausible scheduling/admission
mechanism; the original hosted snapshot timings were not captured.

Only the test file changed. Before **each** action it obtains a fresh real
SQLite/permission snapshot and passes that stamp through a one-call test
boundary. Actual `recordMany`, Python opt-out/reenable, generation checks and
one-use result handling remain real. The correction isolates those assertions
from optional 25 ms admission timing; it changes no production code, deadline
or permission check. The unchanged separate
`unavailable and late selection measurements consume their result without retaining a future use`
test still exercises the actual 25 ms deadline and verifies that a late result
cannot authorize later use.

Both selected tests passed together under the same delayed-real-read hook,
with zero failures/skips. Evidence is
`deadline-followup/windows-consent-deadline-followup.json` and
`deadline-followup/consent-and-late-admission.log`. These add **two distinct
Electron-runtime cases**, bringing this batch to **78 distinct Python and 56
local Electron cases**; the earlier 54 trust cases are not counted again.
Hosted Windows ARM and new-release qualification remain pending. This is a
test correction, not a qualified Windows runtime fix. Windows permission-helper
startup cost and resource behavior remain unqualified; no N-API replacement
was selected.

## Rotation and allocation boundaries

Authorities are release metadata, not workspace/user certificates. At most two
allow an old/new issuer overlap to be distributed before a collector changes
issuer. Installed clients use their existing trust until the normal automatic
updater installs and restarts a compatible release. Offline clients or clients
with updates paused can retain older trust. Production rollout must preserve a
compatible chain for supported clients during rotation and must also satisfy
ordinary browser trust. No production authority or destination has been selected.
Destination/address changes retain their existing review-binding behavior;
a CA-only change introduces no new report field or approval payload.

The saved upstream Node 24.22.0 `secure-context.js`, lines 179–185, selects
`addCACerts` when explicit `ca` is supplied and otherwise calls `addRootCerts`.
This supports the first-use allocation hypothesis; it is not an RSS result or
binary proof for every Electron target. The saved `sqlite.cc` calls
`FinalizeStatements` before `sqlite3_close_v2`; no deferred-statement-leak fix
was selected. Immediate return of resident memory is not established by that
ordering. The declared plan retains both upstream files and their hashes.

The [original six-case resource follow-up](2026-10-26-telemetry-allocation-followup.md),
run `40372901181`, still fails the unchanged 2 MiB gate: enabled main matched
maxima were **3,145,728 / 3,186,688 bytes**, with endings of
**2,768,896 / 2,428,928 bytes**. Both opted-out comparisons, all process roles and
earlier rejected SQLite results remain retained. The 0.5% CPU limit also remains
unchanged. One fixed six-case resource follow-up on the integrated changed
source is planned; no result, causal saving or acceptance is claimed here.

Resource, whole-wire, actual provider/ingress privacy, production certificate
selection and rotation, installed-platform behavior and full V08 acceptance
remain open. Current availability belongs to [release status](../RELEASE_STATUS.md).
