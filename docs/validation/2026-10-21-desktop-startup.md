# Desktop startup and native crypto validation

Recorded 21 October 2026 for **unreleased candidate 4.44.1**, based on accepted
public **4.44.0** source `2d9736649dcee74362b9d9ebe0d73af3ae984305`.
The patch contains the source-startup shutdown drain and native crypto
initialization corrections. It does not include L1 retained conversation capture
or change the [65 product requirements](../PRODUCT_REQUIREMENTS.md) and L1–L7 scope.

## Source corrections

The [desktop source controller](../../studio/electron/desktop-sources.ts)
previously allowed `close()` to return while the initial settings read still
counted as busy. Repeated application quit attempts could starve the helper
completion, and startup could recreate its polling timer after close. Shutdown
now awaits an existing read, startup rechecks the closed state after loading,
and closed controllers refuse new uncached reads. A failed startup read also
drains without restarting source work.

The [native engine entry](../../studio/engine/main.py) sets
`CRYPTOGRAPHY_OPENSSL_NO_LEGACY=1` before worker dispatch and service imports.
The supported encryption, signature and password formats use the default
provider. The source crypto regression exercises this entry and requires empty
stderr.

## Patch validation

The [desktop lifecycle cases](../../studio/electron/scripts/test-desktop-sources.mjs)
cover shutdown during a pending settings read, drained busy state, no timer
recreation, and refusal to restart loading after a failed read and close.
The [crypto subprocess case](../../service_tests/test_native_engine_crypto.py)
starts the actual native entry in a fresh interpreter. It checks that the legacy
cipher is unavailable while AES-GCM, Ed25519, RSA and Argon2id work, with rejection
of changed ciphertext bindings, changed signed data and incorrect passwords.

Against the frozen public 4.44.0 baseline, both startup lifecycle cases failed
(**2 failed, 0 passed**), and the crypto subprocess case failed (**1 failed**).
The original results are retained as `public-startup-baseline-tests.log` and
`public-crypto-baseline-tests.log`. The corrected public patch passed:

- TypeScript build: `public-corrected-build.log`.
- Desktop source, agent and local-workspace cases: **70 passed, 0 failed** in
  `public-corrected-lifecycle-tests.log`.
- Fresh-interpreter native crypto case: **1 passed in 2.16 seconds** in
  `public-corrected-crypto-tests.log`.

Ruff lint and format passed for both Python files, and the installed probe's
JavaScript syntax check passed. Version preparation and export validation also
passed. These are this candidate's source and preparation results; earlier
main-source test totals are not carried over.

## Installed release gate

The [installed-hosting gate](../../studio/electron/scripts/smoke-installed-hosting.mjs)
now launches a fresh installed app profile before creating a workspace. Its
[startup phase](../../studio/electron/local-hosting-probe.ts) confirms that no
workspace configuration exists, then the gate requires the app's normal clean
shutdown before continuing setup and the existing hosting journey. A successful
receipt records `freshProfileShutdownBeforeSetup: true`. At this source
checkpoint, the new phase had not yet been executed natively.

Development run `39628117517` exercises later main/L1 source and was packaging
at this checkpoint. Its results do not validate this
public-source patch. The candidate requires its own exact-source release build,
six installed-platform journeys and required update/relaunch checks. Release
verification, publication and public update results remain separate gates.
No six-platform acceptance or new publication is claimed by this source record;
public **4.44.0** was current at this checkpoint. See the [release notes](../releases/4.44.1.md) and
[release status](../RELEASE_STATUS.md).
