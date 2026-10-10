# Code signing policy

Updated: **2026-10-10**. Project maintainer: **PERSEUS LEGACY LIMITED**.

## Current status

Trusted Windows and macOS signing is not yet available for the rebuilt platform.
All six native platform/architecture validation jobs passed at the checkpoint in
the [validation report](validation/2026-10-10.md), but unsigned or ad-hoc signed
test builds are not approved production updates. The platform-v1 release remains
a draft. Do not interpret a checksum or a successful build as a trusted signature.

The application to the free [SignPath Foundation program](https://signpath.org/apply)
has been submitted under its [code of conduct](https://signpath.org/terms).
Acceptance, certificate provisioning and CI integration remain pending. If accepted, the required credit
will be: “Free code signing provided by [SignPath.io](https://signpath.io),
certificate by [SignPath Foundation](https://signpath.org).” This conditional
statement does not claim an existing endorsement or certificate.

A Foundation certificate identifies **SignPath Foundation**, not our company.
Before the first signed release, bind the updater to the actual approved signing
identity and verify the installed executable and installer. Do not pin an assumed
publisher or disable signature checks to accommodate an unsigned build.

Only free services are authorized for project release operations. Do not buy
certificates or enroll in paid programs or automatically converting trials.
Apple's standard Developer ID program requires paid membership. Its fee waiver
is limited to eligible nonprofits, accredited educational institutions and
government entities; no such eligibility has been established for this company.
Apple-trusted macOS signing and notarization remain unavailable. Mac compatibility
itself does not require Apple membership. We are now testing
[Sparkle's independent Ed25519 update signatures](implementation/free-macos-updates.md)
as a free distribution option. The native experiment and actual Electron
integration must pass before changing the production updater. This route retains
an initial user approval requirement and may be restricted by company device
policy; it cannot provide Apple's publisher trust. Never disable Gatekeeper
globally or mislabel ad-hoc builds as notarized.

## Roles and release controls

- **Authors and reviewers:** the [repository maintainer](https://github.com/Perseusxrltd).
  External contributions require maintainer review, including build scripts and
  dependency changes.
- **Release approver:** the same repository maintainer. A provider requiring manual
  approval must receive that approval for every signing request; an automated
  draft or a previous release's approval does not replace it.
- **Account security:** signing and source-control users must enable multi-factor
  authentication before production signing access is provisioned.

Build from a reviewed, identified commit with pinned CI actions and lockfiles.
Verify product names/versions, upstream license notices, inventories, platform
signatures and update payloads. Sign only this project's eligible binaries;
preserve upstream components and their signatures rather than claiming authorship.
Keep keys and signing service credentials in protected stores outside the repository.

Prepare a draft only after product and native checks pass. Recheck that a release
is still a draft before replacing its assets. Never overwrite a published version:
issue a new patch. Publish only after the complete artifact set, signing identity
and signed upgrade rehearsal have been reviewed. Installed clients can then
receive that approved update under the [automatic update policy](service/updates.md).

## Privacy and system changes

The [privacy policy](service/privacy.md) describes data handling and third-party
connections. Studio enables background operation, launch at login and stable
update checks by default in supported installations. These settings are visible
in **Background and updates** and can be disabled by users or deployment policy.
See [background operation, updates and removal](service/updates.md) for controls
and uninstallation. Signing approval does not grant access to any user's memories.
