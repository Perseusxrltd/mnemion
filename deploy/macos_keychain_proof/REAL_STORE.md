# Owned real-store stage

This stage is source only. It has not been compiled or executed here. It stays
inactive until Astra reviews it and dispatches
`.github/workflows/macos-keychain-real-store.yml`. The default dispatch is
compile-only and executes none of the produced binaries. Runtime selection is
the explicit `run_fixture=true` input.

`fixture_owner.c` remains the injected owner. Its symbol denylist is unchanged.
The injected successes 41366681263 and 41367070289 are not evidence for this
lane. Failed run 41363656552 remains failed.

## What a future success proves

On that runner, the signed helper is frozen, both parents carry that unchanged
helper, and parent A performs one real empty-store direct lookup. It does not
prove publisher signing, notarization, production helper adoption, XPC
authentication, item ACL retention, ciphertext migration, Electron
interoperability, or reporter-hardware acceptance.

## Fixed stage

`signed_artifact_and_empty_lookup`. Signing class `fixture`.

The public command is `real-store-owner arm64|x86_64 absolute-private-parent`.
Internal commands are only `--owner` and `--stall-child`. There is no remote
command and no arbitrary action input.

Success-path recorded children, in order, 23:

1. `git rev-parse HEAD`
2. `clang` the provisioner
3. `create-stores`
4. `openssl genrsa`
5. `openssl req`
6. `openssl pkcs12`
7. `import-identity`
8. `clang` the measurement tool
9. `clang` the helper
10. `unlock-signing`
11. `codesign` the helper, without `--deep`
12. `measure freeze`
13. `clang` parent A
14. `codesign` parent A, outer only
15. `clang` parent B
16. `codesign` parent B, outer only
17. `lock-signing`
18. `measure compare`
19. parent A `check-helper`
20. `unlock-data`
21. parent A `direct-lookup`
22. `lock-data`
23. `delete-owned`

Bundle copies and header writes are in-process. They are not extra children.
Parent pins are written after step 12 and before step 13. The caller header is
written after step 7 and before step 9. The store header is written after step
3 and before the helper exists. A failure may spawn one extra `delete-owned`
(`log-delete-retry`). The spawn cap is 24.

`check-helper` must exit 0 with stdout `result=ok` and `keychain_calls=0`, and
empty stderr. `direct-lookup` must exit 1 with stdout `result=missing_key` and
`keychain_calls=1`, and stderr exactly `direct_lookup=interaction_bracket`.
Any other exit, including `unavailable`, is a mismatch. Direct lookup bypasses
the check-helper branch, so both children stay. No availability, seal, open, or
drop command is used. Those would start the embedded XPC service. No other
process seeds an item.

## Budgets and custody

Stage 300000 ms. Each child 45000 ms. The child wait does not extend the stage
deadline. Cleanup grace 10000 ms. Stall normal 400 ms, stall grace 200 ms,
hygiene 100 ms. Custody record bound 32. The success path uses one owner plus
23 children, which fits. These numbers are not the injected 60000/10000/10000
budgets. The injected budgets stay where they are.

Every compiler, provisioner, signer, and checker is spawned with
`POSIX_SPAWN_SETPGROUP` and process group 0, so the recorded pgid is the child
pid. The record pipe is fd 3. Lines are `C`, `X`, `R`, `Y`, and `P`. An empty
`kill(-pgid, 0)` observation is not a wait and is not a later signal target.
`kernel_stuck_reaped` stays 0. A deadline, a shell elapsed time, SIGKILL, or
disposal of the runner is not reaping proof. There is no PID rediscovery and
no broad kill. External Security processes are not given an untracked worker.
The helper's `xpc_main` lifetime is outside this record, which is why this
stage does not call it.

Exit 0 is success after complete cleanup. Exit 1 is a stage failure after
complete cleanup. Exit 2 is incomplete cleanup. Exit 3 is cancelled. Exit 4 is
usage or preflight.

## Stores and identity

The owned parent is outside the checkout, mode 0700, with no symlink component.
`/tmp` and `/var` do not pass. The run uses fixed names: data store
`throwaway.keychain` mode 0600, signing store `fixture-signing.keychain` mode
0600, `fixture-run.txt` mode 0600, `fixture.lock` mode 0600, and an empty
`ciphertext` directory mode 0700. The record is exactly three lines,
`nonce=`, `service=`, and `account=`, using the fixed disposable prefixes.
Existing or replaced paths are refused. The measured `SecKeychainGetPath` must
equal the requested path. A `.keychain-db` alias or any other basename is
`store_basename_contract` and stops the stage. The sealed guard is not widened
to admit it.

Passwords are 32 varied hex characters in mode 0600 files. They are not
arguments, receipts, or logs. The signing store and the data store are created
with explicit non-null references and `SecKeychainCreate`. Login and System
stores are not created. The default store and the search list are copied before
and after creation and compared. They are not set, and they are not restored
by mutation. A difference fails and is retained. Preference domains are not
changed.

One ephemeral fixture leaf is generated locally and imported only into the
owned signing store. There is no Developer ID, Apple account, paid certificate,
trust installation, or notarization. The ACL names only `/usr/bin/codesign`.
Signing uses that leaf's uppercase SHA-1, `--keychain` pointed at the signing
store, and `--timestamp=none`. It does not use `--deep`, `--force`, or a
certificate name. If codesign exits non-zero, the category is `signing_refused`.
If it does not finish inside the child budget, the category is `deadline`.
The UI interaction flag is saved, set false, read back, and restored around
file-Keychain calls. A setup or restore failure fails. This is not a search-list
restore.

Leaf pins are the measured DER SHA-1 and SHA-256 from `SecCertificateCopyData`.
Certificate-name text and the compile-only placeholder strings are refused.
Caller pins and helper pins stay in different headers. The manifest pin is
`bundle_manifest_digest()` of the frozen helper. It is not a ZIP hash. Mutable
helper pins are not copied into the helper bundle.

## API allowlist

Owned-store create, open, unlock, lock, and owned delete. Scoped fixture
identity generation, import, signing, and measurement. The existing guarded
direct lookup and `check-helper`.

Not called: login or default-store creation, search-list or default setters,
trust-settings changes, `SecKeychainLockAll`, a null keychain argument, and
global authorization changes.

Provisioner commands are only `create-stores`, `import-identity`,
`unlock-signing`, `lock-signing`, `unlock-data`, `lock-data`, and
`delete-owned`. Measurement commands are only `freeze` and `compare`.
`identity_dump` keeps its original one-argument bundle form and adds `der`.
Manifest and tree walks live in `real_store_measure` so the existing
compile-only identity link does not gain a `bundle_manifest` symbol.

## Receipt and privacy

The receipt is version 1, `lane=real_store`, `native_operations=real`. It does
not claim `native_security_calls=0`. Instrumented calls are counted only inside
the provisioner. External tool calls are `unavailable`. Device, inode, paths,
nonce, designated requirement text, and OSStatus values stay in mode 0600
files inside the run. The public receipt uses booleans, fixed categories, the
expected command outcome, and, only after full success, the public leaf hashes.

The workflow uploads compile logs and the public stdout plus a short status.
It does not upload private keys, PKCS#12, passwords, Keychain databases,
companion files, generated headers, signed fixture binaries, owner stderr, or
the custody file.

A stage may be `unsupported` or `signing_refused`. It does not adopt
compile-only pins or turn a check off in order to continue.
