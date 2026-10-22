# Native local runtime in desktop installers

The desktop packages the frozen `mnemion-engine`, PostgreSQL, pgvector and their
licenses alongside the existing vault client and UI. The installed application
uses `resources/engine` and `resources/postgresql`; its private workspace remains
in the existing separate user-data location. Packaging never initializes or
replaces a user's database. Model weights remain a first-run download through
the app's setup flow. No Python, PostgreSQL, Docker, account or paid API setup is
required on the user's computer.

## Targets and build inputs

The engine and CPU inference runtime use native Python 3.13 on Linux and macOS,
for both x64 and ARM64, and on Windows x64. Windows ARM packages keep the desktop
and vault client native ARM64 but run the **x64 service, model and PostgreSQL**
through Windows x64 compatibility. The locked `psycopg-binary` 3.3.6 distribution
has no Windows ARM wheel, so claiming a native ARM service would be inaccurate.
No other architecture mismatch is accepted. The `native-runtime.json` resource
records both component architectures and explicitly marks emulation. Installed
model inference on a Windows ARM runner is required before that target passes.

`.github/workflows/desktop.yml` calls the reusable native database workflow for
exactly the database targets it needs. Windows x64 and ARM64 share one compiled
x64 database archive from the same workflow run. Before packaging, the workflow
checks native database operation, including the Windows ARM emulation gate.
It installs the repository's locked service dependencies with the
`native-build` group and freezes the engine from that same checkout. Both Windows
desktops also share one x64 service archive built on an x64 Windows runner.
Freezing an emulated interpreter on ARM can collect ARM system runtime DLLs;
building the complete x64 backend once avoids that mixed-architecture package.
Every executable and DLL is still checked before either desktop consumes it.

Release assembly can reuse the Intel cryptography runtime wheel from a completed
full Product checks run on `main` at the exact release source. The
[release evidence rules](release-automation.md#reusing-complete-main-ci-for-a-release)
require the complete successful CI matrix and its matching, unexpired artifact;
the transfer verifies GitHub's archive digest before extracting the wheel.
The six native desktop builds and installed application gates still run for
the release. Reusing this service wheel does not reuse an old desktop installer
or replace independent publication verification.

For a local build on a target OS/architecture:

```sh
uv sync --project studio/client --locked --python 3.13 --no-managed-python
uv sync --locked --no-default-groups --group native-build --python 3.13 --no-managed-python
# Supply the verified native PostgreSQL zip in build-tmp/native-postgres.
npm --prefix packages/client ci
npm --prefix studio/frontend ci
npm --prefix studio/electron ci
npm --prefix studio/electron run dist
npm --prefix studio/electron run smoke:installed-hosting
```

`MNEMION_BUILD_PYTHON` selects the client build interpreter;
`MNEMION_ENGINE_PYTHON` selects the service build interpreter.
`MNEMION_POSTGRES_ARCHIVES` can select another directory containing the verified
PostgreSQL archive. `MNEMION_ENGINE_ARCHIVES` selects a directory with exactly one
matching service ZIP from the same source/version/lock. Windows ARM requires
that service to have been built on Windows x64; it does not freeze the service
again on the ARM host. The service interpreter is x64 on Windows, including an ARM desktop build;
the client interpreter matches Node. Use ordinary
CPython, or a standalone Python build with its exact native-library licenses
reviewed in `deploy/license-overrides/native-python.json`.

## Package gates

`deploy/native_resources.py` assembles bounded archives into new build output
and checks every file against its SHA-256 inventory. It rejects extra files,
links, missing executable/license files, stale service source or dependency
locks, and incompatible native binary headers. PostgreSQL sources must match
the reviewed PostgreSQL, pgvector, OpenSSL and zlib source manifest. macOS
universal libraries must contain the requested slice. The verifier runs before
packaging, against the packaged resources, and against installed resources.

The engine carries its complete Python notice inventory and CycloneDX SBOM in
`engine/licenses`. PostgreSQL carries the four upstream licenses in
`postgresql/licenses`; its runtime manifest includes the pinned source records.
The desktop's existing license inventory remains in `licenses`.

On macOS, the native engine and database retain the ad-hoc signatures created by
their builders. Electron packaging excludes these inventoried files from a
second signing pass that would otherwise change their hashes. The outer app
signature seals the resources, and installer validation still performs a deep,
strict code-signature check. No paid signing identity is required.

## Installed application proof

`smoke:installed-hosting` creates a new private profile and installation path
with spaces and Unicode. It installs the actual NSIS payload on a disposable
Windows CI runner, copies the app from the DMG on macOS, or performs a user-owned
portable installation of the AppImage payload on Linux. Windows refuses to run
outside a disposable CI runner or when an existing Mnemion installation is
registered. Linux CI runs this probe under `xvfb-run`.

The [installed-hosting driver](../../studio/electron/scripts/smoke-installed-hosting.mjs)
defines the ordered launches and required receipt fields. Its sandboxed renderer
uses real app controls, installed engine/database resources and authenticated
workspace operations. The ordinary quit path must stop PostgreSQL. Follow the
[capture implementation checkpoint](../research/2026-10-21-durable-capture-implementation.md)
for development gate scope, exact-source evidence and remaining acceptance;
new source or headless policy-migration checks do not qualify a packaged target.
Maintain the phase inventory in the driver.

CI retains `build-tmp/installed-hosting-evidence.json`, a bounded report containing
no credentials, and successful phase screenshots under
`build-tmp/installed-hosting-*.png`. The driver defines the screenshot inventory.
Raw failure diagnostics and the generated private workspace remain in the
disposable runner temporary directory. Successful fixtures clean up their own
installation and profile.

These checks apply to the locally built installer. Successful source tests or a
local Linux run do not establish acceptance of public downloads, other native
platforms, or upgrade migrations. Those require their own recorded native runs.
