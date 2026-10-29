# Code signing policy

Updated: **2026-10-30**. Project maintainer: **PERSEUS LEGACY LIMITED**.

## Platform status

The first platform-v1 desktop distribution, **4.0.0**, introduced macOS and Linux.
Version **4.0.1** adds Windows x64; **4.0.3** adds Windows ARM64 after its native
installation, authenticated upgrade and relaunch passed. Each OS/architecture
pair is published only after its release validation gates pass. Published assets at
[the product page](https://www.perseusxr.com/mnemion) determine availability.

Mac applications use intact ad-hoc signatures and pinned Sparkle with independent
Ed25519 signatures over update archives. Both real packaged Electron architectures
passed signed replacement/relaunch and safe-restart guards. Native checks also
passed invalid signatures, interruption recovery, oversized/older releases and
cancellation. See [the implementation evidence](implementation/free-macos-updates.md).
The build is not Apple Developer ID signed or notarized. First launch may require
explicit Privacy & Security approval, which a managed Mac may prohibit. Apple
publisher trust is separate from verification of subsequent signed archives.
Never disable Gatekeeper or describe an ad-hoc signature as Apple-verified identity.

The 4.46.53 source corrects the launch failure in
[issue 49](https://github.com/Perseusxrltd/mnemion/issues/49). Ad-hoc executables
have no Apple Team ID; hardened runtime's library validation can therefore
reject the app's own Electron Framework even when every bundle seal verifies.
The free build retains hardened runtime and explicitly grants only
`com.apple.security.cs.allow-jit` and
`com.apple.security.cs.disable-library-validation` to the main executable and
Electron helpers. This is the [Electron Builder documented policy](https://www.electron.build/v26/docs/features/code-signing/code-signing-mac.html)
for ad-hoc builds, not a publisher certificate. The native installer verifier
checks these actual executable entitlements as well as bundle integrity, and
the installed-app launch and update tests remain required. See the
[qualification and remaining Mac acceptance](validation/2026-10-29-macos-adhoc-launch.md).
A future Developer ID signing integration must review this exception again.
If an affected app cannot start, its updater cannot run either: install the
corrected published package once it is available. Do not locally re-sign an
old release or disable system security as a substitute.

The same ad-hoc identity controls the macOS login-keychain prompt for saved
connections, tracked in [issue 50](https://github.com/Perseusxrltd/mnemion/issues/50).
Electron `safeStorage` keeps one keychain item. After successful access, a
healthy running helper of the same executable reuses its encryptor for later
saved connections. That child can be discarded and replaced after an
unavailable result, denial, timeout, or pipe failure. A helper restart, a
failed approval, a locked keychain, or a changed OS access policy can require
another prompt. **Allow** covers the successful retrieval in the running
helper, so the next launch asks again. **Always Allow** normally permits the
unchanged binary while that permission remains valid. For this free build,
`codesign` reports `Signature=adhoc` and `TeamIdentifier=not set`, and the
designated requirement is the cdhash of that exact binary. The next update or
any re-sign changes the cdhash, so macOS asks once for the new file. Always
Allow does not survive that change. This implementation's current ad-hoc app
identity changes across builds and does not preserve that exact-binary trust.
This batch adds no cross-update credential migration. This is the behavior
Electron documents for `safeStorage`, and the reason
electron/electron#43233 was closed as not a bug.
Do not grant every app access to the item, store a login password, or replace
existing ciphertext to hide the prompt. See
[saved connections](service/workspaces.md#remember-a-connection-using-a-key).

Linux AppImage updates use the established Electron updater with HTTPS release
feeds and payload hashes. Debian packages use administrator-managed upgrades.
Checksums establish payload integrity; they are not an OS publisher certificate.

The free [SignPath Foundation application](https://signpath.org/apply) has been
submitted under its [code of conduct](https://signpath.org/terms). Approval,
provisioning and CI integration remain pending. Do not resubmit the application
or claim approval in advance. If accepted, credit will be: “Free code signing
provided by [SignPath.io](https://signpath.io), certificate by
[SignPath Foundation](https://signpath.org).” A Foundation certificate identifies
SignPath Foundation. Bind any Authenticode publisher check to the actual approved
identity, not an assumed company certificate. SignPath's service does not export
a PFX; its integration must use the approved project and signing policy.

A free [Windows update implementation](implementation/free-windows-updates.md)
authenticates Windows x64 and ARM64 delivery. An Ed25519 manifest binds the
exact full NSIS installer, version, architecture, URL, size and hash. Cached
installers are verified again before execution. An independent signature authenticates updates without providing
Windows publisher reputation or bypassing company policies.

Only free services are authorized. Do not purchase certificates, Apple membership,
paid runners or trials that turn into paid subscriptions.

## Keys and release controls

The Mac public key is in `studio/electron/native/sparkle.json`; its matching
private seed is supplied only to the release signing step through
`MNEMION_MAC_UPDATE_PRIVATE_KEY`. The private recovery copy stays outside the
repository. Never print, commit or upload private keys or account credentials.
Document and test rotation before changing a shipped trust key. Loss or compromise
requires an explicit recovery plan for already-installed clients.

The Windows public key is in `studio/electron/native/windows-updates.json`.
Its separate Ed25519 private key is provided only to the signing step as
`MNEMION_WINDOWS_UPDATE_PRIVATE_KEY` (base64 PKCS#8). The same recovery, rotation
and non-disclosure rules apply. The manifest must verify against this embedded
key even when no OS publisher certificate is available.

From 4.0.8, managed service releases use a third, separate Ed25519 key. Its
public key is embedded in `mnemion/service/update_trust.py`; the release signing
step receives `MNEMION_SERVICE_UPDATE_PRIVATE_KEY` (a base64 raw 32-byte seed).
The signed `service-update.json` binds exact Python archives, the Intel Mac native
dependency wheel, source commit, lockfile and migration hashes. The native wheel
contains static OpenSSL, licenses and source provenance, built and tested on a
native runner before the separate signing step. Installation and handoff recheck
application and supplied native dependency bytes. No signing key is sent to an installed service. Retain the private recovery
copy outside Git and plan a tested trust-key transition before any rotation.
The initial manifest establishes a public baseline; it cannot retroactively add
an updater to an older server. See [host adoption](service/managed-updates.md).

The repository maintainer reviews changes and approves releases. Provider-required
manual signing approvals apply to each request; previous approval does not replace
them. Signing and source-control accounts must use multi-factor authentication.
Build from an identified commit using pinned actions and dependency lockfiles.
Preserve upstream notices and verify payload inventories, architectures, versions,
platform signatures, archive signatures and update feeds.

Keep `main` current with implementation and documentation. Prepare a draft from
a fixed commit after checks pass. Recheck draft status before changing its assets.
Publish complete OS/architecture pairs listed in `deploy/release-targets.json`;
pending architectures stay unavailable. Never overwrite published assets: later binaries
require a new patch version. Retain update feeds for already-supported platforms
when publishing the next stable release. The website offers only complete,
published platform assets and updates its links after revalidation.

## Privacy and user control

The [privacy policy](service/privacy.md) describes data handling and connections.
Background operation, login startup and stable updates are enabled by default in
supported installations, with visible user and administrator controls. See
[updates and removal](service/updates.md). Signing never grants access to a user's
memories, changes server permissions or authorizes a database upgrade.
