# Mnemion Studio

The desktop and web workspace for the shared-memory service. Published downloads
are on [the product page](https://www.perseusxr.com/mnemion). Version 4.0.3 adds
native Windows ARM64, with automatic installation and relaunch verified on a
Windows ARM runner. All three operating systems have x64 and ARM64 targets. Studio supports
organizations, scoped spaces, memory editing and review, evidence, search,
source connections, agents, Obsidian, operations and visual insights/evaluations.

The desktop includes a sandboxed Electron shell and a small local vault-refresh
executable. From 4.0.11, it also bundles the private engine, PostgreSQL and CPU
model drivers for guided **Create on this computer** setup. Model weights download
when local setup is selected. Joining an existing company workspace does not
start a local database or download a model on every employee's laptop.
Source 4.11.0 adds **Setup & this device → Company sign-in setup** for a local
host: a copied HTTPS callback, OIDC discovery, client/certificate settings,
session limits, removal/repair and matching private agent controls. See the
[company guide](../docs/service/company-sign-in.md); publication is tracked in
[release status](../docs/RELEASE_STATUS.md).
Source 4.12.0 adds **Secrets** and **Encrypted credentials vault** setup, with
scoped person/key grants, timed value reveal, audit records and encrypted
import/export. [The vault guide](../docs/service/secrets-vault.md) explains the
separate host key, backup recovery and opt-in MCP tools.
Remote-agent fixes in 4.0.2 and lower model RAM in 4.0.3 require upgrading the memory server;
the desktop updater cannot replace a separately deployed service. See the
[patch notes](../docs/releases/4.0.12.md). Version 4.0.12 also fixes native ngrok
API access and stale cached offline responses. Version 4.0.5 adds **Sync now**, pending
requests and scan results to Sources. Upgrade the server and runner for these
controls. It retains 4.0.4's agent administration and Linux AppImage login-path
repair, including preservation of OS startup disable flags and custom commands.

From 4.0.6, official Python release archives include the web Studio and offline
documentation. The API serves them automatically. Git installations can run
`uv run --no-sync mnemion-service studio build` once, then restart the API. Node.js
22+ is needed only for this source build. See the
[web setup and overrides](../docs/service/README.md#studio).
Version 4.0.7 adds a [background service manager](../docs/service/supervision.md)
for Linux/macOS hosts without systemd. It manages the API and worker; the desktop
continues to connect to the service chosen by its user or organization.

Version 4.0.9 adds [OS-protected workspace connections](../docs/service/workspaces.md):
reopen a verified workspace after restart, disconnect durably, or forget a device
bookmark. Locked/unavailable keyrings use a session-only connection and never
save a plaintext key. Version 4.0.11 adds native local creation, RAM controls and
occupied API-port recovery. Organization provisioning and full backup recovery
remain on the [onboarding plan](../docs/implementation/app-onboarding.md).

The next source release adds [encrypted desktop backups and independent
recovery](../docs/service/native-backups.md): protected schedules, manual copies,
current deletion ledgers and restoration into a separate local workspace.
Installed acceptance remains pending; use the public release status for availability.

Version 4.0.8 unifies the interface with Perseus XR, including locally bundled
Inter/Outfit fonts, gold accents, grouped navigation, responsive charts and offline
help. The [design guide](../docs/STUDIO_DESIGN.md) documents the shared tokens.
Its [managed server updater](../docs/service/managed-updates.md) is an independent
host adoption, with signed patches, verified backups and runtime rollback.

Create a local workspace in the app, or connect to an existing workspace with its
URL and your personal or application credential. Independently hosted teams use
the [service deployment guide](../docs/service/deployment.md). Credentials remain
scoped to the spaces granted to that identity.

[Background and update behavior](../docs/service/updates.md) covers login startup,
tray/dock access, automatic stable updates and safe restarts. Windows NSIS, macOS
DMG/ZIP and Linux AppImage/DEB are built natively for x64 and ARM64. Release signing
and each native validation result must pass before promoting desktop artifacts.

For development:

```sh
uv sync --project studio/client --locked
npm --prefix packages/client ci
npm --prefix packages/client run build
npm --prefix studio/frontend ci
npm --prefix studio/frontend run dev
```

In a second terminal, install/build the Electron shell and run it:

```sh
npm --prefix studio/electron ci
npm --prefix studio/electron test
npm --prefix studio/electron run dev
```

Prepare the locked client and engine environments and verified database archive
using the [native packaging guide](../docs/implementation/native-desktop-packaging.md),
then create installers with `npm --prefix studio/electron run dist` on the target
OS and architecture. Windows ARM uses a native client and a separately built x64
engine/database. Packaging validates both components, licenses and inventories.
`npm --prefix studio/electron run smoke:installed-hosting` exercises real local
creation, model save/search, restart, address recovery and encrypted backup/restore
with the platform's actual credential store.
`npm --prefix studio/electron run smoke:packaged` opens the real installed
payload with an isolated profile; Linux CI uses Xvfb. CI validation artifacts are
unsigned and are not sent to the automatic update feed.

The [historical v3 Studio guide](../docs/legacy/v3-studio.md) documents the retired
bundled legacy backend and older UI routes.

Version 4.0.10 adds the [live 3D memory map](../docs/service/memory-map.md),
real reviewer-scoped activity, stable geometry and a lightweight 2D/list view.
The [connection diagnostic](../docs/service/connection-diagnostics.md) distinguishes
offline hosts from credential, space-access and MCP failures.
