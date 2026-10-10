@echo off
:: Full Mnemion Studio build pipeline.
:: Produces dist-electron with the unpacked Windows app and installer.
:: Run from the mnemion repo root.

setlocal
set ROOT=%~dp0..\..

echo.
echo ==============================================
echo   Mnemion Studio - Full Build
echo ==============================================
echo.

echo [1/5] Building frontend assets
pushd "%ROOT%\studio\frontend"
if not exist "node_modules" (
    call npm ci
    if %ERRORLEVEL% NEQ 0 ( echo ERROR: frontend npm ci failed && exit /b 1 )
)
call npm run build:electron
if %ERRORLEVEL% NEQ 0 ( echo ERROR: frontend build failed && exit /b 1 )
popd
echo [1/5] Frontend OK

echo.
echo [2/5] Building memory service
call "%ROOT%\studio\scripts\build-backend.bat"
if %ERRORLEVEL% NEQ 0 ( echo ERROR: memory service build failed && exit /b 1 )
echo [2/5] Memory service OK

echo.
echo [3/5] Building Electron shell
pushd "%ROOT%\studio\electron"
if not exist "node_modules" (
    call npm ci
    if %ERRORLEVEL% NEQ 0 ( echo ERROR: Electron npm ci failed && exit /b 1 )
)
call npm run build
if %ERRORLEVEL% NEQ 0 ( echo ERROR: Electron TypeScript build failed && exit /b 1 )
popd
echo [3/5] Electron shell OK

echo.
echo [4/5] Verifying resources and building unpacked app
pushd "%ROOT%\studio\electron"
call npm run verify:resources
if %ERRORLEVEL% NEQ 0 ( echo ERROR: packaged resources missing && exit /b 1 )
call npx electron-builder --dir
if %ERRORLEVEL% NEQ 0 ( echo ERROR: unpacked app build failed && exit /b 1 )
popd
echo [4/5] Unpacked app OK

echo.
echo [5/5] Packaging Windows installer
pushd "%ROOT%\studio\electron"
call npm run dist:prepackaged
if %ERRORLEVEL% NEQ 0 ( echo ERROR: installer build failed && exit /b 1 )
popd
echo [5/5] Installer OK

echo.
echo ==============================================
echo   Build complete
echo   Output: %ROOT%\dist-electron
echo ==============================================

endlocal
