# Desktop background operation and updates

Official Studio installations enable automatic stable updates, background mode
and launch at login by default. Preferences are in the application or tray menu,
under **Background and updates**. The first installed launch registers login
startup. An explicit operating-system startup override is not reset on each launch.

| Installation | Updates | Background access |
| --- | --- | --- |
| Windows NSIS, x64/ARM64 | Automatic download and installation | System tray; launch at login |
| macOS signed application, x64/ARM64 | Automatic download and installation; publisher signature required | Menu bar and Dock; launch at login |
| Linux AppImage, x64/ARM64 | Automatic download and replacement of the writable AppImage | Tray where supported; minimized window remains accessible; XDG login entry |
| Linux DEB | Distribution/package-manager updates | Same background and login behavior |
| Web Studio | Served with the deployed service version | Browser behavior; no desktop startup registration |
| Python SDK, CLI, MCP and server | Administrator/package-manager deployment | Service manager or container restart policy |

Checks begin 1–2 minutes after startup and repeat approximately every six hours,
with jitter to spread organizational bandwidth. Only the official repository's
stable release feed is used. Each architecture has a separate feed; prereleases,
downgrades and web installers are disabled. Electron's updater verifies payload
checksums and platform signing requirements. Errors remain visible in the menu
and are retried; they do not prevent access to memory.

Downloaded updates install during a normal quit. They also install and restart
automatically after ten minutes of system inactivity, provided Studio is not
focused, no vault/API transfer is active, and no edited input remains open.
Close a completed editor or navigate away to release its draft guard. An active
draft deliberately postpones an automatic restart. Closing the main window keeps
the app running when background mode is enabled; use **Quit Mnemion Studio** to exit.
On Linux, close minimizes the window because some shells do not show tray icons.

AppImage updates require write access to the installed AppImage and its directory.
Keep that file in a stable user-owned location before enabling login startup.
Machine-wide managed installations may need the organization's deployment agent
to apply updates. `MNEMION_AUTO_UPDATE=0` disables the built-in updater as an
administrator policy; `MNEMION_START_AT_LOGIN=0` skips default startup registration.
Development and smoke-test runs never register startup or download updates.

Old releases without an updater need one initial installation of this release.
An updater cannot retroactively modify an unconnected older installation.
Desktop updates do not grant the app authority to replace a company's database.
Use backups, migrations and health checks from the [deployment guide](deployment.md)
for server updates. Browser clients receive the new service assets on reload.

## Publisher setup

The **Prepare signed release** workflow runs product checks and all six native
builds, verifies signatures and payloads, and creates a draft containing installers,
architecture-specific update feeds, Python/TypeScript packages and SHA-256 checksums.
It does not publish a partially built update. Promote the completed draft after
review; that promotion makes it visible to installed clients automatically.
Never overwrite assets of a published version; issue a new patch version.

Configure these repository Actions secrets through GitHub's encrypted secret store:

| Secret | Purpose |
| --- | --- |
| `WINDOWS_CSC_LINK` | Base64-encoded publisher PFX accepted by electron-builder |
| `WINDOWS_CSC_KEY_PASSWORD` | Its password |
| `MAC_CSC_LINK` | Base64-encoded Apple Developer ID Application certificate and private key |
| `MAC_CSC_KEY_PASSWORD` | Its password |
| `APPLE_ID` | Apple account authorized to notarize |
| `APPLE_APP_SPECIFIC_PASSWORD` | Dedicated notarization password |
| `APPLE_TEAM_ID` | The matching Apple developer team |

Certificates must be valid publisher credentials; self-signed or ad-hoc certificates
do not substitute for trusted Windows signing or Apple's Developer ID/notarization.
Never add a certificate, private key, password or signing export to Git. Unsigned
CI artifacts are labeled **validation-only** and are not public update releases.
