# Next staged build step

The signer, freeze, and parent A/B assembly are not implemented here. The
compile-only lane stays non-executing. `fixture_owner.c` is the external
disposable owner for an injected API boundary and real private files. That
owner has not been executed. The guard below is source only: sealed
configuration, the file-Keychain interaction bracket, and the one-time
creation marker.

Do this later, in order, on a disposable Mac runner:

1. Create one ephemeral fixture signing identity in an owned throwaway signing
   keychain. Do not change trust settings or the default search list. Do not
   use a Developer ID or an Apple identity.
2. Write `generated/caller_pin.h` from that leaf certificate's actual DER
   SHA-1 and SHA-256. Class `fixture`. Metadata must not say `compile_only`.
   Leave helper cdhash, manifest, identifier, and designated requirement out
   of this header.
3. Create the private run before signing. Directory mode 0700, no symlink
   component (`/tmp` and `/var` do not pass). Inside it: `throwaway.keychain`
   mode 0600, `fixture-run.txt` mode 0600, empty `ciphertext` mode 0700, and
   `fixture.lock` mode 0600. Measure the canonical absolute path, nonce,
   effective uid, and the run and store device/inode. Write
   `generated/fixture_store_config.h` with class `fixture`, the fixed
   prefixes `mnemion-disposable-service-` and `mnemion-disposable-account-`,
   the exact service and account, and those measured values. Do this before
   the helper is built. A `ProtectedCloudStorage` name is rejected.
4. Build and sign the helper once per architecture. Freeze the complete signed
   bundle, including `HelperInfo.plist`, `IdentityEpoch`, resources, and the
   signature.
5. Measure that frozen artifact: cdhash, `bundle_manifest_digest`, identifier,
   and designated requirement. Write those into `generated/parent_pin.h`.
   Compare the certificate pins to the certificate DER, not to their text shape.
6. Build parents A and B from the existing generation resources and the same
   fixture certificate and identifier. Copy the exact signed helper into both.
   Sign only the outer parents. Do not deep-sign the helper again. Record
   different parent cdhashes. Check helper tree equality, manifest, designated
   requirement, cdhash, and certificate hashes in both bundles.

`fixture_owner.c` is the controller source for one owned run directory, the
throwaway store file, the external deadline, and the injected cases. Building
or starting it is a separate manual step in `FIXTURE_OWNER.md`. It is inactive
until Astra reviews that source. Compile-only placeholders still refuse
process start. Real store creation, an ephemeral signing identity and its DER
measurement, frozen-helper A/B builds, actual approval retention, and
independent Chromium or Electron interoperability remain unproved.

The guard already requires all of this:

- Launchd starts the helper with no extra argument. The sealed header is the
  run. Extra argv is refused. An environment value or an XPC field cannot
  select a path. Parent direct lookup binds that same header. A supplied path
  is accepted only when it is byte-for-byte the sealed directory.
- The directory is absolute, mode 0700, owned by the sealed uid, and has no
  symlink component. `/tmp` and `/var` are symlinks on macOS, so they do not pass.
  The live device and inode must match the sealed run and store identities.
- `fixture-run.txt` is mode 0600 and contains exactly three newline-terminated
  lines: `nonce=<32 lowercase hex>`, `service=<service prefix><nonce>`,
  `account=<account prefix><nonce>`. Those values must equal the sealed header.
- `throwaway.keychain` already exists at mode 0600 before any lookup. This
  guard does not create it and does not call `SecKeychainCreate`.
- Lookup is `SecItemCopyMatching` with a nonempty one-store
  `kSecMatchSearchList`. Add passes that store as `kSecUseKeychain`. The fixed
  synthetic names do not enter Apple's `ProtectedCloudStorage` default-store
  exception. This guard does not call `SecKeychainSetSearchList` or change the
  default keychain. A hit whose keychain path is not the owned store is refused.
- Each file-Keychain call, including open and direct lookup, saves
  `SecKeychainGetUserInteractionAllowed`, sets it false, checks the read-back,
  and restores the previous value on every return. Setup or restore failure
  fails the case. `LAContext` is not the control for this file-Keychain route.
  Permission and locked errors stay as results. The external deadline is still
  required. This does not change another process's keychain settings.
- The first add takes a nonblocking exclusive lock on `fixture.lock`, requires
  `ciphertext` to be an empty private directory and `creation-attempted` to be
  absent, checks the item is absent, then creates that marker with `O_EXCL` and
  `O_NOFOLLOW` and fsyncs it before `SecItemAdd`. The marker is not removed
  after an error. A later missing key with ciphertext or that marker is not
  replaced. An existing key remains readable. Seal publication uses the same
  lock and `ciphertext` directory. `empty_profile` does not prove any of this.
