@echo off
:: ── Full Mnemion Studio build pipeline ────────────────────────────────────
:: Produces:  dist-electron/  (Windows NSIS installer + unpacked app)
::
:: Prerequisites:
::   - Python 3.11+ with mnemion installed editable
::   - Node 20+ in PATH
::   - PyInstaller: py -m pip install pyinstaller
::
:: Run from the mnemion repo root.

setlocal
set ROOT=%~dp0..\..

echo.
echo ╔══════════════════════════════════════════════╗
echo ║        Mnemion Studio — Full Build           ║
echo ╚══════════════════════════════════════════════╝
echo.

:: ── Step 1: Build frontend ────────────────────────────────────────────────
echo [1/4] Building React frontend…
pushd "%ROOT%\studio\frontend"
call npm install --silent
if %ERRORLEVEL% NEQ 0 ( echo ERROR: npm install failed && exit /b 1 )
call npm run build:electron
if %ERRORLEVEL% NEQ 0 ( echo ERROR: npm build failed && exit /b 1 )
popd
echo [1/4] Frontend OK → studio/frontend/dist/

:: ── Step 2: Build Python backend ─────────────────────────────────────────
echo.
echo [2/4] Building Python backend…
call "%ROOT%\studio\scripts\build-backend.bat"
if %ERRORLEVEL% NEQ 0 ( echo ERROR: backend build failed && exit /b 1 )
echo [2/4] Backend OK → dist-backend/backend/

:: ── Step 3: Build Electron main process ───────────────────────────────────
echo.
echo [3/4] Building Electron main process…
pushd "%ROOT%\studio\electron"
call npm install --silent
if %ERRORLEVEL% NEQ 0 ( echo ERROR: npm install failed && exit /b 1 )
call npm run build
if %ERRORLEVEL% NEQ 0 ( echo ERROR: tsc failed && exit /b 1 )
popd
echo [3/4] Electron TS compiled → studio/electron/dist/

:: ── Step 4: Package with electron-builder ────────────────────────────────
echo.
echo [4/4] Packaging installer…
pushd "%ROOT%\studio\electron"
call npx electron-builder --win --x64
if %ERRORLEVEL% NEQ 0 ( echo ERROR: electron-builder failed && exit /b 1 )
popd
echo [4/4] Installer OK → dist-electron/

echo.
echo ══════════════════════════════════════════════
echo  Build complete!
echo  Installer: %ROOT%\dist-electron\
echo ══════════════════════════════════════════════
endlocal
