@echo off
:: ── Build Mnemion Studio backend with PyInstaller ─────────────────────────
:: Output: dist-backend/backend/backend.exe
:: Run from the mnemion repo root.

setlocal

set ROOT=%~dp0..\..
set DIST=%ROOT%\dist-backend
set SPEC=%ROOT%\studio\scripts\backend.spec

echo [build-backend] Root: %ROOT%
echo [build-backend] Output: %DIST%

:: Install studio extras if needed
py -m pip install -e "%ROOT%[studio]" --quiet

:: Run PyInstaller
py -m PyInstaller ^
    --name backend ^
    --onedir ^
    --noconfirm ^
    --distpath "%DIST%" ^
    --workpath "%ROOT%\build-tmp" ^
    --hidden-import uvicorn.logging ^
    --hidden-import uvicorn.loops ^
    --hidden-import uvicorn.loops.auto ^
    --hidden-import uvicorn.protocols ^
    --hidden-import uvicorn.protocols.http ^
    --hidden-import uvicorn.protocols.http.auto ^
    --hidden-import uvicorn.protocols.websockets ^
    --hidden-import uvicorn.protocols.websockets.auto ^
    --hidden-import uvicorn.lifespan ^
    --hidden-import uvicorn.lifespan.on ^
    --hidden-import fastapi ^
    --hidden-import mnemion ^
    --hidden-import mnemion.config ^
    --hidden-import mnemion.hybrid_searcher ^
    --hidden-import mnemion.knowledge_graph ^
    --hidden-import mnemion.trust_lifecycle ^
    --hidden-import chromadb ^
    --collect-all chromadb ^
    --collect-all hnswlib ^
    --collect-all tokenizers ^
    "%ROOT%\studio\backend\main.py"

if %ERRORLEVEL% NEQ 0 (
    echo [build-backend] ERROR: PyInstaller failed.
    exit /b %ERRORLEVEL%
)

echo [build-backend] Done. Binary at: %DIST%\backend\backend.exe
endlocal
