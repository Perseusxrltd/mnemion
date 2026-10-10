# Free macOS distribution and update investigation

Updated: **2026-10-10**. This records an investigation, not a shipped updater.

Building and distributing a macOS app does not require a paid Apple membership.
Developer ID signing and notarization provide Apple's publisher trust and first
installation experience. Without them, an initial installation may require the
user's explicit approval in Privacy & Security. Managed Macs may prohibit that
exception. Never disable Gatekeeper globally or describe an ad-hoc signature as
an Apple-verified publisher identity.

The current Electron/Squirrel updater requires application signing on macOS.
That requirement is specific to the current updater; it does not establish that
every safe automatic-update design requires Apple enrollment.

[Sparkle](https://sparkle-project.org/documentation/) supports Ed25519 signatures
for update archives and describes Developer ID/notarization as recommended "if
possible." We are evaluating its maintained native installer instead of creating
a custom archive replacement or signature-verification implementation.

## Native experiment

`deploy/macos_update_probe.py` downloads the pinned Sparkle **2.10.0** distribution
and compiles its unmodified command-line driver from commit
`eef1a539a373c1f1a320624b1130fc5de7b2e100`. Every downloaded file is checked against
a pinned SHA-256. The upstream license remains with the private test distribution.
The [native workflow](../../.github/workflows/macos-update-probe.yml) runs on
standard Intel and Apple Silicon macOS runners. No paid service, certificate,
stored signing credential or installer-artifact upload is involved.

The experiment creates two tiny ad-hoc signed Cocoa apps in a new private
directory, and an ephemeral Ed25519 key held in memory and a signing pipe. A
loopback feed first offers an archive with an invalid signature, then the valid
signature. Assertions cover rejection before replacement, preservation of the
running old app, installation at the original path, automatic relaunch and the
new bundle's ad-hoc signature. It changes no Gatekeeper setting and never targets
an installed Mnemion app.

On an isolated native Mac with Xcode Command Line Tools and Python 3.13:

```sh
python deploy/macos_update_probe.py --output /private/tmp/mnemion-sparkle-probe
```

Use a new directory for each run. The result and diagnostic logs contain only
synthetic app data; no production signing key is generated or published.

## Gates before adopting it

- Pass the native experiment on both architectures. A workflow definition alone
  is not evidence that it works.
- Integrate with the actual Electron bundle, visible update preferences, managed
  policy, bounded downloads, safe idle restart and cancellation.
- Validate tampered archives, wrong keys, interrupted downloads/installations,
  downgrade prevention, resource limits, recovery and source/artifact provenance.
- Keep the update public key in the installed bundle, protect its private key in
  the release secret store, and document recovery and key-rotation limits.
- Produce architecture-specific HTTPS feeds and immutable signed update assets;
  update the release verifier, website, installation guide and troubleshooting.
- Test and document the first-install approval experience separately. The probe
  begins with an already-running fixture and cannot certify Gatekeeper approval,
  notarization or installation on a managed company device.

The desktop release remains under validation while these gates are open. This
route could remove the Apple membership dependency for Mnemion's own verified
updates; it cannot manufacture Apple's publisher trust.
