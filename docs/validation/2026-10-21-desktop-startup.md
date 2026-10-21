# Desktop startup and native crypto validation

Recorded 21 October 2026 for **unreleased candidate 4.44.1**, based on accepted
public **4.44.0** source `2d9736649dcee74362b9d9ebe0d73af3ae984305`.
The first candidate was frozen at `e45e2b1bf4d9a85bc12a07fb4687cc6cfede4ade`.
The revised candidate adds bounded Windows atomic-replacement retries to its
source-startup shutdown drain and native crypto initialization corrections.
It does not include L1 retained conversation capture or change the
[65 product requirements](../PRODUCT_REQUIREMENTS.md) and L1–L7 scope.

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

## First candidate source validation

These results apply to the first candidate and precede its installed Windows
failure recorded below.

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
passed. These are the first candidate's source and preparation results; earlier
main-source test totals are not carried over.

## Installed release gate

The [installed-hosting gate](../../studio/electron/scripts/smoke-installed-hosting.mjs)
now launches a fresh installed app profile before creating a workspace. Its
[startup phase](../../studio/electron/local-hosting-probe.ts) confirms that no
workspace configuration exists, then the gate requires the app's normal clean
shutdown before continuing setup and the existing hosting journey. A successful
receipt records `freshProfileShutdownBeforeSetup: true`. At the first
candidate's source validation checkpoint, this phase had not yet executed
natively.

## First candidate Windows failure, 21 October 2026

The first 4.44.1 release run `39631942686` failed Windows x64 installed hosting,
job `119335274370`, during `backup-resume`. The native retention UI received
`EPERM` when atomically renaming a temporary policy file to `backup-policy.json`.
The verified original artifact `12360857308` and job log remain retained as
evidence of this first-candidate failure.

## Windows replacement correction

The revised candidate adds bounded retries for Windows sharing-lock failures
when replacing [backup settings](../../studio/electron/local-backups.ts) and
[saved workspace connections](../../studio/electron/workspace-store.ts).
The [replacement helper](../../studio/electron/atomic-file.ts) retries only
Windows `EPERM`, `EACCES` and `EBUSY`, with ten waits totaling 1.5 seconds; other
errors fail immediately. It never unlinks the target or partially overwrites it.
Where the caller supplies a cancellation signal, it is checked before each
rename attempt and interrupts the wait. Exhausted retries or cancellation before
the rename leave the previous target intact.

The r2 TypeScript build passed (`r2-electron-build.log`). Final focused atomic-file,
local-backups and workspace-store results are:

- Actual Windows Node **25.2.1**: **46 passed, 0 failed and 2 skipped** in
  **2.19 seconds** (`r2-windows-final-components.log`). Both skips are existing
  POSIX-permission-only cases. The real Windows reader handle denying delete
  sharing was exercised and its regression passed.
- Linux: **47 passed, 0 failed and 1 skipped** in **1.82 seconds**
  (`r2-linux-final-components.log`). The Windows-only handle case was skipped.

`r2-final-component-inputs.json` records the matched source bytes used by these
runs. The synthetic NTFS fixture was removed afterward; production configuration
and credentials were untouched. Earlier Windows launch attempts stopped before
tests because of UNC Node file matching and an unsigned UNC PowerShell script;
their logs remain retained. These are source component checks. Installed
application validation for the revised candidate remains pending.

## Remaining release acceptance

The separate main/L1 Intel run `39628117517` succeeded; its exact installed
artifact qualified all **59** required true fields at source `64326de1`.
That result does not validate this public-source patch. The revised candidate
requires its own exact-source release build, six installed-platform journeys
and required update/relaunch checks. Release
verification, publication and public update results remain separate gates.
No six-platform acceptance or new publication is claimed by this source record;
public **4.44.0** remains current, and L1 remains unfinished. See the [release notes](../releases/4.44.1.md) and
[release status](../RELEASE_STATUS.md).
