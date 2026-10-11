# Desktop background operation and updates

Platform v1 uses the **4.x** package series. Version **4.0.3** adds Windows ARM64;
release targets now cover Windows, macOS and Linux on x64 and ARM64. Download published installers from
[the official product page](https://www.perseusxr.com/mnemion).
See [the patch notes](../releases/4.0.7.md) for current changes and measured limits.

Official Studio installations enable automatic stable updates, background mode
and launch at login by default. Preferences are in the application or tray menu,
under **Background and updates**. The first installed launch registers login
startup. An explicit operating-system startup override is not reset on each launch.
From 4.0.4, an existing Linux login entry follows the AppImage's new versioned
filename during updating and on the first launch after an earlier version's
update. OS disable flags, deleted entries and custom startup commands are
preserved. A manually managed startup command remains the operator's responsibility.

| Installation | Updates | Background access |
| --- | --- | --- |
| macOS application, Intel/Apple silicon | Sparkle verifies independently signed Ed25519 update archives, then installs and relaunches when safe | Menu bar and Dock; launch at login |
| Linux AppImage, x64/ARM64 | Automatic download and replacement of the writable AppImage | Tray where supported; minimized window remains accessible; XDG login entry |
| Linux DEB | Distribution/package-manager updates | Same background and login behavior |
| Windows NSIS, x64/ARM64 | Independently signed Ed25519 manifest, verified full installer, automatic safe restart | System tray and launch at login |
| Web Studio | Served with the deployed service version | Browser behavior; no desktop startup registration |
| Python SDK, CLI, MCP and server | Administrator/package-manager deployment | Service manager or container restart policy |

## First installation

On Windows x64, choose **Intel / AMD (most PCs)**; on a Windows ARM device,
choose **ARM64**. Run the matching NSIS installer.
It supports a user installation without installing models or databases. The
initial installer does not yet carry an OS publisher certificate, so Windows may
show an unknown-publisher message. Verify its official source; company policy may
require an administrator-approved deployment. Independent signatures authenticate
subsequent updates without bypassing SmartScreen or company policy. The ARM64
installer uses native system process checks during installation and updates.

On macOS 13 or later, choose **Apple silicon** for an M-series Mac or **Intel**
for an Intel Mac. Open the disk image, drag **Mnemion Studio** to Applications,
and eject the disk image. Use a writable Applications folder for automatic updates.
The free distribution has an ad-hoc application signature and independently
signed updates. It is not Apple Developer ID signed or notarized. If macOS blocks
the first launch, use **System Settings → Privacy & Security → Open Anyway**
after confirming that the download came from the official page. See
[Apple's instructions](https://support.apple.com/102445). A managed company Mac
may prohibit this exception; its administrator controls that policy. Do not
disable Gatekeeper or system malware protection. Subsequent update archives must
verify against the public key embedded in the installed app.

On Linux, choose the matching AppImage, put it in a stable user-owned folder,
make it executable using your file manager or `chmod +x`, and launch it. The
AppImage and its directory must be writable for automatic replacement. Some
distributions require their FUSE compatibility package. The Debian package is
available with the release assets for administrator-managed installation. Use
only an installer matching your architecture.

Studio connects to a shared memory service; it does not install a large model on
every device. Follow the [deployment guide](deployment.md) to create a workspace,
or use the workspace address and application key supplied by your administrator.

## Update behavior and resource limits

Checks begin 1–2 minutes after startup and repeat approximately every six hours,
with jitter to spread organizational bandwidth. Only the official repository's
stable release feed is used. Architectures have separate feeds; prereleases and
downgrades are excluded. Errors remain visible and are retried without blocking
access to memory. Users can pause updates and administrators can manage them.

Updates install and restart automatically after ten minutes of system inactivity,
provided Studio is not focused, no vault/API transfer is active, and no edited
input remains open. Close a completed editor or navigate away to release its
draft guard. On Mac and Windows, a normal quit cancels a staged update; a later check can
retry it. This prevents a cancelled update from installing after the app exits.
On AppImage, a downloaded update can also install during a normal quit.

The Mac updater limits an archive to 1 GiB and checking/downloading/verifying to
20 minutes. A staged update waiting for safe restart expires after 24 hours.
Quitting waits up to 15 seconds for native cancellation; if cleanup is still
running, Studio reports that and allows another quit attempt. Sparkle owns
signature verification, extraction, replacement and relaunch. The controller
holds installation until the app's restart guards permit it. The signed Mac
archives are published at immutable GitHub release URLs.

Windows verifies a signed manifest of at most 16 KiB and streams a full installer
of at most 1 GiB to its update cache. Downloads have a 20-minute total deadline
and 30-second idle timeout. The app rechecks size and SHA-512 immediately before
execution, expires staged authorization after 24 hours, and removes partial or
superseded downloads. It checks restart guards again before launching NSIS.

Closing the main window keeps the app running when background mode is enabled;
use **Quit Mnemion Studio** to exit. On Linux, close minimizes the window because
some shells do not show tray icons. Machine-wide managed installations may need
the organization's deployment agent to apply updates. `MNEMION_AUTO_UPDATE=0`
disables the built-in updater as an administrator policy;
`MNEMION_START_AT_LOGIN=0` skips default startup registration. Development and
smoke-test runs never register startup or download production updates.

Older releases without this updater need one initial installation. Desktop
updates do not replace a company's database. Use backups, migrations and health
checks from the deployment guide for service updates. Browser clients receive
the deployed service assets on reload.

To receive the 4.0.2 API/MCP fixes, operators must update and restart the separately
deployed **server**, including an installation launched with `uv run`. Updating
Studio alone cannot patch it. Source deployments can use a reviewed release
checkout, `uv sync --locked`, and their existing process supervisor; keep the
previous checkout and deployment backup for rollback. No new database migration
is introduced in 4.0.2. From 4.0.7, the [Supervisor setup](supervision.md) manages
the API and worker on Linux/macOS without systemd, with crash recovery and
cron/launchd startup configuration. It does not install new software. Verified
server update staging, backups and safe rollback remain tracked in issue 11.

Version 4.0.5's source-sync controls require the updated runner and a coordinated
server upgrade with migration `012_connector_sync_requests.sql`. Follow the
backup/migration/restart and rollback sequence in its
[release notes](../releases/4.0.5.md#server-upgrade-and-rollback); an older service
will reject the newer migration set. Desktop updates leave that database untouched.

## Publisher setup

The [code signing policy](../CODE_SIGNING.md) records platform trust and release
roles. Release operations use free services, with no paid enrollment or trials.
`deploy/release-targets.json` identifies the OS/architecture pairs to publish.
Every selected pair requires its complete installer and update assets. A pending
architecture does not prevent publication of another that has passed.

**Prepare signed release** runs product checks, builds the selected native
packages, verifies their payloads and creates a reviewable draft. Publish only
after those checks pass. Use a new patch version for later binaries; never
replace assets of a published release. New stable releases must retain the feeds
for platforms already offered to users.

| Repository Actions secret | Purpose |
| --- | --- |
| `MNEMION_MAC_UPDATE_PRIVATE_KEY` | Base64-encoded 32-byte Ed25519 seed matching the Mac public key committed in `studio/electron/native/sparkle.json` |
| `MNEMION_WINDOWS_UPDATE_PRIVATE_KEY` | Base64 PKCS#8 Ed25519 key matching `studio/electron/native/windows-updates.json`; authenticates full Windows installers independently of an OS certificate |
| `WINDOWS_CSC_LINK` | Optional future Windows publisher PFX; not available from SignPath's non-exportable signing service |
| `WINDOWS_CSC_KEY_PASSWORD` | Password for an approved Windows PFX, when that route is used |

Apple account credentials are not required by the free Mac pipeline. Keep the
Mac private key in encrypted release secrets and a protected offline recovery
copy, outside Git. A lost key cannot authorize updates to installations that
trust it. Rotation requires a documented, tested transition signed by the old
key, or a new manual installation. A suspected compromise requires stopping
publication and a separate recovery decision; changing the public key in source
alone does not repair existing clients.

## Removal

Disable **Start at login** and **Keep running in background**, then quit Studio
before removing it. On macOS, remove Mnemion Studio from Applications and check
**System Settings → General → Login Items**. On Linux, remove the AppImage or
uninstall the DEB with your package manager. If the application was removed
before disabling startup, remove its `com.perseusxr.mnemion-studio.desktop` entry
from your XDG `autostart` directory. On Windows, use
**Settings → Apps → Installed apps → Mnemion Studio → Uninstall**.

Uninstalling the desktop does not delete organization memories, backups or
exported Obsidian vaults. Revoke the device's credentials through the workspace
administrator. Remove local preferences and exports separately when intended;
see the [privacy policy](privacy.md).
