# Windows client release

Updated 2026-10-10. **Windows desktop publication is pending.** Mac and Linux
release independently. Windows users can use browser Studio with their memory
service now; see [the product page](https://www.perseusxr.com/mnemion).

Mnemion Studio 4 connects to the shared service and adds native Obsidian vault
refresh. The default package includes the frontend, sandboxed Electron bridge,
and a small local vault client. It does not start the v3 Chroma backend.

## Reproducible native build

Use native Windows Node.js 22 and Python 3.13. From the checkout root:

```powershell
uv.exe sync --project studio/client --locked --python 3.13
$env:MNEMION_BUILD_PYTHON = Join-Path (Get-Location) "studio/client/.venv/Scripts/python.exe"
npm.cmd --prefix packages/client ci
npm.cmd --prefix studio/frontend ci
npm.cmd --prefix studio/electron ci
npm.cmd --prefix studio/electron run dist
npm.cmd --prefix studio/electron run smoke:packaged
```

The resource build compiles the SDK/frontend and packages `studio/bridge/main.py`
with PyInstaller. `MNEMION_BUILD_PYTHON` can select an existing locked environment.
Use a separate checkout for Windows if the working checkout has Linux
`node_modules` or a Linux virtual environment.

Required artifacts:

- `dist-electron/win-unpacked/Mnemion Studio.exe`
- `dist-electron/win-unpacked/resources/client/mnemion-client.exe`
- `dist-electron/Mnemion-Studio-<version>-windows-<arch>.exe`
- `dist-electron/Mnemion-Studio-<version>-windows-<arch>.exe.blockmap`

`verify:resources` checks local-client and frontend inputs. `verify:installer`
opens the installer with the current builder's 7-Zip tooling and checks its real
payload, including the local client, HTML, and Windows tray icons. It also checks
Authenticode status. `dist:prepackaged` builds an installer from an existing,
verified `win-unpacked` directory.

## Native launch checks

`smoke:packaged` starts the actual packaged window with an isolated profile. It
requires the workspace to render, the sandboxed service/vault preload to load,
Node to remain unavailable to the renderer, a functioning local-client version
probe, and a loaded Windows tray icon. It cleans up its process tree and temporary
profile on success and failure.

Before publishing, exercise authenticated save/search/review and Obsidian refresh
against a real service. Verify personal notes/settings survive a repeated refresh,
closing hides to tray, and a second launch focuses the existing instance. Check
renderer errors and local resource loads. Sign-out/reload must clear the API key;
only the last service address is stored between sessions.

The 9 October 2026 native build produced a 116 MB installer on Windows
10.0.26200. Installer payload validation and the real-window/preload/tray/local
client smoke check passed. Authenticated workspace loading also passed against
the isolated PostgreSQL-backed service. The implementation ledger records later
acceptance checks and any outstanding release requirements.

## Publisher signing

The local artifact is **NotSigned**. It is suitable for controlled development
validation; its installer and authenticated update path must pass before public distribution.
To require signing during release validation:

```powershell
$env:MNEMION_REQUIRE_CODE_SIGNATURE = "1"
npm.cmd --prefix studio/electron run verify:installer
```

That check must fail for an unsigned installer. Builder log lines mentioning a
signing step do not establish that a certificate was applied. The free SignPath
application is submitted, with approval and integration pending. Windows x64
ships an independently signed Ed25519 update manifest from 4.0.1; 4.0.3 adds
native ARM64. Both pass real NSIS installation, signed upgrade and relaunch.
The ARM installer selects native system PowerShell for the upstream running-app
check, retaining normal shutdown protection. The public x64 4.0.1 → 4.0.2
automatic upgrade also passed with unmodified packages and the official feed.
See the [current signing policy](CODE_SIGNING.md) and
[update validation](validation/2026-10-11.md). These independent update signatures
do not confer Windows publisher reputation or bypass organization policy.

The package still contains historical frontend views for v3 development. An
explicit `MNEMION_LEGACY_STUDIO=1` launch additionally requires the separately
built legacy backend; it is not the supported default v4 experience.
