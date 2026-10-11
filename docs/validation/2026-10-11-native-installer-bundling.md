# Native installer integration — 2026-10-11

The isolated installer branch based on `a703e41` now bundles the frozen service,
CPU inference dependencies, PostgreSQL/pgvector, file inventories and licenses
into desktop installers. No version, release, tag, or main-branch change was
made. The complete pipeline is described in
[Native desktop packaging](../implementation/native-desktop-packaging.md).

## Measured locally

- Frozen Linux x64 engine 4.0.10 built with locked PyInstaller 6.22.3 and
  fastembed 0.9.0; 57 Python license components.
- Staged and packaged inventories verified 384 engine files and 784 database
  files, totaling approximately 341 MiB of native resources.
- Linux AppImage and Debian artifacts built and passed installer/resource
  verification. Exact hashes and sizes are in the
  [machine-readable evidence](2026-10-11-native-installer-bundling.json).
- The actual AppImage payload was installed in a new user-owned directory with
  spaces and Unicode, using a new private app profile. The renderer clicked the
  real setup controls, created a workspace and downloaded the real model.
- Authenticated semantic save/search passed. An anonymous API request returned
  401. Ordinary app quit stopped PostgreSQL cleanly.
- A second process launch automatically reopened the same workspace. The saved
  memory, credentials, endpoint and configured RAM policy were preserved, and
  semantic retrieval passed again. The resulting workspace screenshot was
  inspected and showed the saved validation memory.
- 44 focused archive, architecture, resource, manifest and target-selection tests
  passed. Electron TypeScript/build, Python lint, JavaScript syntax and workflow
  YAML parsing passed. The actual pinned PyInstaller manifest also round-tripped
  UTF-8, long-path support and `asInvoker` in a build-tool check.

Heavy local build/test commands ran in scopes limited to 2 GiB RAM, no swap and
200% CPU. The first installed test used a 1.5 GiB cooperative policy; after a
successful create/search/restart, its semantic restart check paused because
reported desktop memory pushed the model requirement just over that policy.
The fixture now selects a 2 GiB cooperative policy and passed its complete
create/restart cycle. This does not change the product's default RAM policy.

## Windows ARM dependency finding

The reviewed lock contains native ARM ONNX Runtime and PyInstaller wheels, but
`psycopg-binary` 3.3.6 publishes Windows AMD64 wheels only. The packaging contract
therefore keeps the Windows ARM desktop and vault client native, and explicitly
uses x64 compatibility for the service, model and PostgreSQL. The build selects
the service interpreter independently, checks Python's PE architecture rather
than WMI's physical CPU report, and inventories the emulated components. Setup
must disclose that combination. A Windows ARM installed-model probe is mandatory
before the target passes.

The frozen Windows engine now preserves PyInstaller's default manifest and adds
UTF-8, so its bundled native PostgreSQL client library can open certificate and
other file paths containing Unicode. Native Windows execution of that engine
manifest remains a CI gate.

## Limits

The local runtime test ran under WSL on Linux x64. The Windows-only compatibility
and manifest changes were covered by source checks and still require native CI.
There was no macOS, Windows, Linux ARM, public-download or upgrade-migration
acceptance claim from this run. The updated desktop workflow builds the required
same-commit database artifacts and records fresh installed UI/model checks on
all selected native runners. No workflow, release or package was published by
this task.
