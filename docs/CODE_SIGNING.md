# Code signing policy

Updated: **2026-10-10**. Project maintainer: **PERSEUS LEGACY LIMITED**.

## Platform status

The first platform-v1 desktop distribution, **4.0.0**, is published for macOS and
Linux on both architectures. Each platform is published only after its complete installer,
update and native validation gates pass. Windows remains under release validation;
it does not prevent users from receiving ready platforms. Published assets at
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
is on `main` and undergoing native validation. An Ed25519 manifest binds the
exact full NSIS installer, version, architecture, URL, size and hash. Cached
installers are verified again before execution. This is not yet an available
Windows release. An independent signature authenticates updates without providing
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

The repository maintainer reviews changes and approves releases. Provider-required
manual signing approvals apply to each request; previous approval does not replace
them. Signing and source-control accounts must use multi-factor authentication.
Build from an identified commit using pinned actions and dependency lockfiles.
Preserve upstream notices and verify payload inventories, architectures, versions,
platform signatures, archive signatures and update feeds.

Keep `main` current with implementation and documentation. Prepare a draft from
a fixed commit after checks pass. Recheck draft status before changing its assets.
Publish complete platforms listed in `deploy/release-targets.json`; pending
platforms stay unavailable. Never overwrite published assets: later binaries
require a new patch version. Retain update feeds for already-supported platforms
when publishing the next stable release. The website offers only complete,
published platform assets and updates its links after revalidation.

## Privacy and user control

The [privacy policy](service/privacy.md) describes data handling and connections.
Background operation, login startup and stable updates are enabled by default in
supported installations, with visible user and administrator controls. See
[updates and removal](service/updates.md). Signing never grants access to a user's
memories, changes server permissions or authorizes a database upgrade.
