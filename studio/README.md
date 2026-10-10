# Mnemion Studio

The desktop and web workspace for the shared-memory service. Published downloads
are on [the product page](https://www.perseusxr.com/mnemion). Version 4.0.3 adds
native Windows ARM64, with automatic installation and relaunch verified on a
Windows ARM runner. All three operating systems have x64 and ARM64 targets. Studio supports
organizations, scoped spaces, memory editing and review, evidence, search,
source connections, agents, Obsidian, operations and visual insights/evaluations.

The desktop client includes a sandboxed Electron shell and a small local vault
refresh executable. It connects to a local or remote service; it does not bundle
PostgreSQL or silently start a model on every employee's laptop.
Remote-agent fixes in 4.0.2 and lower model RAM in 4.0.3 require upgrading the memory server;
the desktop updater cannot replace a separately deployed service. See the
[patch notes](../docs/releases/4.0.4.md). Version 4.0.4 adds server-side agent
administration and keeps Linux AppImage login entries current after an update,
while preserving OS startup disable flags and custom commands.

Use the [service deployment guide](../docs/service/deployment.md) first, then
connect with the service URL and a personal or application credential. Credentials
remain scoped to the spaces granted to that identity.

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

Create native installers with `npm --prefix studio/electron run dist` on the target
OS and architecture. The separate locked desktop environment installs no database
driver or embedding runtime, including on Intel Macs and Windows ARM64. Packaging validates the local client, license inventory and
payload. `npm --prefix studio/electron run smoke:packaged` opens the real installed
payload with an isolated profile; Linux CI uses Xvfb. CI validation artifacts are
unsigned and are not sent to the automatic update feed.

The [historical v3 Studio guide](../docs/legacy/v3-studio.md) documents the retired
bundled legacy backend and older UI routes.
