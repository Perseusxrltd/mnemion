# Ad-hoc Mac launch compatibility

Recorded 29 October 2026 for **4.46.53 source**, addressing
[issue 49](https://github.com/Perseusxrltd/mnemion/issues/49).

The reporter's Apple M5 Mac on macOS 27.2 rejected Studio 4.46.49 at launch with
dyld's “different Team IDs” error for Electron Framework. Studio 4.46.38 had
failed the same way. The reported official ARM disk image matched its published
SHA-256, the deep strict bundle-signature check passed, and the app failed even
when opened directly from the disk image. The separate CLI worked. These are
reporter observations, not a local reproduction on that Mac.

The reported main executable had only `com.apple.security.cs.allow-jit`, with
an ad-hoc signature and hardened runtime. The source confirms that entitlement
set. [Electron Builder's signing guidance](https://www.electron.build/v26/docs/features/code-signing/code-signing-mac.html)
documents this exact failure: ad-hoc executables have no Team ID, so hardened
runtime library validation requires the explicit
`com.apple.security.cs.disable-library-validation` exception. See also
[Apple's entitlement reference](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.cs.disable-library-validation).

The corrected entitlement file retains hardened runtime and adds that exception
to the main executable and Electron helpers. The installer verifier now inspects
the signatures and actual entitlement dictionaries of all five executables.
It requires ad-hoc identity, hardened runtime and exactly the two reviewed
boolean entitlements. Existing deep strict signature verification, signed
updates, hashes, fuses and installed-app launch checks remain required.

Two focused policy tests pass on Linux and in the Windows native Node suite.
They reject the original one-entitlement policy, disabled hardened runtime,
unexpected signing identity, extra entitlements and malformed values. They
establish the verifier's policy behavior; they do not establish Mac launch.

The following acceptance remains open:

1. Both native Mac release jobs must inspect the actual corrected bundles,
   install them, open a real local workspace and pass the signed update checks.
2. The corrected public installer must open on the reporter's affected Mac.
3. Its ordinary update path must retain the same verified package and startup
   behavior. An app that cannot launch cannot run its updater and requires a
   replacement download first.

No published artifact was overwritten, no local re-sign was applied to the
reported installation, and no Gatekeeper setting was disabled. Apple Developer
ID signing and notarization remain unavailable in the free pipeline. This
exception does not supply Apple publisher identity or override managed policies.
Issue 49 remains open until its actual acceptance passes.

Retained upstream signing-guide capture SHA-256:
`f53d38e9b6a3c8e35bba96af0b3faa03d0cdc9105ecfd1edb7e380d53d0971dc`.
