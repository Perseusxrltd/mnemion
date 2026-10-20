# Native agent setup acceptance

Recorded 20 October 2026 for source **4.32.0**. Native installer and publication
results remain in [release status](../RELEASE_STATUS.md). Source checks are not
claims of acceptance by each named vendor.

## Focused evidence

The focused run passed **7 service integration cases, 3 runtime process cases,
202 lightweight-client cases and 2 desktop-controller cases**. Eleven client
cases deliberately skip where the tested OS/dependency is unavailable. The
actual source-app flow passed in **44.84 seconds** after the runtime integration.

- Real PostgreSQL/HTTP checks verify dedicated application identity, tenant
  matching, administrator rejection, private key custody, unchanged unrelated
  JSON/TOML settings, exact original backups, concurrent-edit refusal and
  recoverable interrupted installation. Removal preserves externally replaced
  entries and leaves server revocation separate.
- A real stdio MCP client starts the generated command without Studio,
  discovers memory tools and sees exactly its granted reader space. The cached
  launcher path is also exercised after the original runtime directory moves.
- Minimal desktop-client tests retain existing Codex policy preservation and
  add Grok Build, named entries and standalone executable arguments.
- Runtime process checks retain an active engine through two later updates,
  start a new session on the current engine after the source bundle disappears,
  remove exited copies, reject tampered/escaping inventories and recover an
  interrupted launcher lock. Failed copies preserve the working pointer.
- An actual Windows PowerShell process exchanges two separate Unicode messages
  through the launcher and cleans its runtime lease. The child is a synthetic
  byte-stream fixture; native release acceptance exercises the bundled MCP
  engine separately.
- Desktop controller checks cover serialized mutations, shutdown cancellation,
  update suspension/resume and rejection of undeclared private-agent inputs.

The actual Linux Electron source-app flow passed with a disposable profile and
real HTTP/PostgreSQL workspace, without a local database. It selects an application
and Grok Build file, reviews/installs the entry, preserves external edits, revokes
a newly issued unused key after a stale preview, removes the setup while signed
out and verifies update guards. The 500-pixel view had no horizontal overflow;
the browser reported no console errors. Only synthetic data and credentials were
used. Screenshot and execution receipts remain in the private acceptance folder.

## Installed release gate

The existing six-target installed-app exercise now invokes the generated
launcher, verifies the packaged private runtime and its version, discovers MCP
tools with a dedicated reader identity, inspects the app page and removes the
fixture without changing unrelated agent settings. It runs on Windows,
macOS and Linux, x64 and ARM64. Its result must pass before publishing that
target; this report does not pre-announce a passing release.

The installed Grok Build CLI's help and native TOML contract informed its
profile. No real Codex/Grok settings, approval policy, sandbox settings or Argil
harness were edited. Hosted OAuth/ChatGPT remains the separate open issue #18.

The first native candidate was withheld for a Windows ARM backup-status write
failure. The corrected source includes [bounded atomic file-lock handling](2026-10-20-windows-state-locks.md),
with actual Windows reproduction, recovered transient locks and preserved data
under lasting denial. Corrected native acceptance remains a publication gate.
