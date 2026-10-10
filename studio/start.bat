@echo off
:: Mnemion Studio - start memory service and frontend in parallel
:: Run from the repo root: studio\start.bat

setlocal

echo.
echo  Mnemion Studio
echo  -------------------------------------
echo  Memory service: http://127.0.0.1:7891
echo  App frontend:   http://127.0.0.1:5173  (Vite may choose another port)
echo  Diagnostics:    http://127.0.0.1:7891/api/docs
echo  -------------------------------------
echo.

:: Install Python deps only when the local package is not importable.
py -c "import studio.backend.main" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    py -m pip install -e ".[studio]" -q
    if %ERRORLEVEL% NEQ 0 ( echo ERROR: Python dependency install failed && exit /b 1 )
)

:: Start the memory service in the background.
start "Mnemion Memory Service" cmd /c "py -m uvicorn studio.backend.main:app --host 127.0.0.1 --port 7891 --reload"

:: Install npm deps if needed
if not exist "studio\frontend\node_modules" (
    echo Installing frontend dependencies...
    cd studio\frontend
    npm install
    if %ERRORLEVEL% NEQ 0 ( echo ERROR: frontend dependency install failed && exit /b 1 )
    cd ..\..
)

:: Start Vite dev server
cd studio\frontend
npm run dev

endlocal
