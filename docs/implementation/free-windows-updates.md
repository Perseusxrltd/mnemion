# Free Windows updates

Status on 2026-10-10: implemented on `main`, undergoing native installation and
upgrade validation. Windows is not part of the published 4.0.0 release. The
existing Mac/Linux downloads remain available while these checks run.

## Delivery and trust

Windows packages use the full Electron Builder NSIS installer. The running app
fetches a small independently signed Ed25519 manifest before downloading an
installer. The signed payload binds the application, stable version, processor
architecture, exact immutable GitHub URL, filename, byte length and SHA-512.
Unsigned YAML, local cache metadata and arbitrary redirect destinations cannot
authorize execution. The public key is embedded in the application's ASAR.

The manifest has a 16 KiB limit. A full installer is limited to 1 GiB; the download
has a 20-minute deadline and a 30-second idle timeout. Transfers stream to disk
and hash incrementally. One dedicated cache holds the current full installer;
partial and superseded installer files are cleaned up. Both existing cache hits
and ready installers are rehashed before use. A ready authorization expires
after 24 hours. Check scheduling is shared with the Mac/Linux controller.

The controller waits for ten minutes of system inactivity, an unfocused window,
no edited fields and no active vault/API operation. It checks these conditions
again before launching NSIS. A failed launch keeps the running app available;
a valid launch replaces the installation and requests a relaunch. Pausing or
ordinary quitting cancels pending work and clears the staged installer. Machine
installations can require Windows elevation or an organization's deployment
agent. Service credentials and loader overrides are not inherited by NSIS.

An independent signature authenticates an update; it does not create a Windows
publisher certificate or SmartScreen reputation. The first installer remains
subject to Windows and company security policy. SignPath enrollment is pending.
When an OS certificate becomes available, configure the actual certificate
identity in `publisherNames` and validate the additional Authenticode path.
Do not assume SignPath's certificate uses the company's name. See the
[signing policy](../CODE_SIGNING.md).

This protects the update transport and detects corrupted or modified cached
payloads. It does not claim to protect a machine from an attacker who already
controls the installed app, its executable, or its user's processes. TLS and
GitHub availability still affect discovery. Old signed metadata cannot downgrade
an installation, but replay can delay discovery of a newer release.

## Reproducible validation

`npm --prefix studio/electron test` covers signature and metadata tampering,
architecture/version/URL boundaries, redirects, byte limits, truncation,
timeouts, cancellation, corrupted caches, expiry and recovery after launch
failure. It also retains the Mac protocol and common restart-policy tests.

The native Windows job builds both x64 and ARM64. After its normal packaged UI,
tray, local-client and Obsidian checks, it runs:

```powershell
node studio/electron/scripts/windows-update-probe.mjs --output "$env:RUNNER_TEMP/mnemion-windows-update"
```

The rehearsal creates unique, disposable NSIS packages from the production
bundle. Only those copies receive an ephemeral public key, local HTTP endpoint
and test entry point. ASAR integrity metadata is updated in the copied PE file;
production packages have no fixture endpoint or environment switch. The
rehearsal performs a real first installation, failure/recovery cases, focus and
draft guards, replacement and a new target-version process. Synthetic inputs
represent system inactivity and in-flight work. A successful run records its
scope in `result.json`; job failure prints bounded diagnostics. Do not infer
native results from passing unit tests.

## Release maintenance

The public configuration is `studio/electron/native/windows-updates.json`.
`MNEMION_WINDOWS_UPDATE_PRIVATE_KEY` is the base64 PKCS#8 Ed25519 private key in
GitHub Actions secrets; its recovery copy stays outside the repository. A
release-only step runs `node deploy/windows_updates.mjs sign`. Assembly verifies
each architecture's manifest against its actual installer and the embedded
public key. A separate dispatch can test the signing key without uploading
release artifacts.

Keep both `latest-x64-windows.json` and `latest-arm64-windows.json` with their
immutable installers and checksums. Never replace a published asset. The next
Windows delivery requires a new patch version and the Mac/Linux feeds needed by
existing users. Key rotation needs an explicit, tested transition for installed
clients; changing a source file alone does not rotate their trust.
