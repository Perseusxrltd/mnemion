@echo off
:: Mnemion Studio — start backend + frontend in parallel
:: Run from the repo root: studio\start.bat

setlocal

echo.
echo  🏛️  Mnemion Studio
echo  ─────────────────────────────────────
echo  Backend :  http://127.0.0.1:7891
echo  Frontend:  http://localhost:5173  (Vite will bump if busy — check terminal)
echo  API docs:  http://127.0.0.1:7891/api/docs
echo  ─────────────────────────────────────
echo.

:: Install Python deps if needed
py -m pip install -e ".[studio]" -q

:: Start FastAPI backend in background
start "Mnemion Backend" cmd /c "py -m uvicorn studio.backend.main:app --host 127.0.0.1 --port 7891 --reload"

:: Install npm deps if needed
if not exist "studio\frontend\node_modules" (
    echo Installing frontend dependencies...
    cd studio\frontend
    npm install
    cd ..\..
)

:: Start Vite dev server
cd studio\frontend
npm run dev

endlocal
