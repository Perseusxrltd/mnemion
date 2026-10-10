@echo off
:: Build Mnemion Studio backend with PyInstaller
:: Output: dist-backend/backend/backend.exe
:: Run from the mnemion repo root.

setlocal

set ROOT=%~dp0..\..
set DIST=%ROOT%\dist-backend
set SPEC=%ROOT%\studio\scripts\backend.spec
set BUILD_TMP=%ROOT%\build-tmp
set UV_CACHE_DIR=%BUILD_TMP%\uv-cache
set PYINSTALLER_CONFIG_DIR=%BUILD_TMP%\pyinstaller-config
set PYTHON_CMD=%ROOT%\.venv\Scripts\python.exe
if not exist "%PYTHON_CMD%" set PYTHON_CMD=py

if not exist "%BUILD_TMP%" mkdir "%BUILD_TMP%"
if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%"
if not exist "%PYINSTALLER_CONFIG_DIR%" mkdir "%PYINSTALLER_CONFIG_DIR%"

echo [build-backend] Root: %ROOT%
echo [build-backend] Output: %DIST%
echo [build-backend] Python: %PYTHON_CMD%

:: Install studio extras if needed
"%PYTHON_CMD%" -c "import PyInstaller, fastapi, uvicorn, chromadb" >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [build-backend] Studio Python extras already available.
) else (
    where uv >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        uv pip install --python "%PYTHON_CMD%" -e "%ROOT%[studio,legacy]" --quiet
    ) else (
        "%PYTHON_CMD%" -m ensurepip --upgrade
        if %ERRORLEVEL% NEQ 0 (
            echo [build-backend] ERROR: failed to bootstrap pip.
            exit /b %ERRORLEVEL%
        )
        "%PYTHON_CMD%" -m pip install -e "%ROOT%[studio,legacy]" --quiet
    )
    if %ERRORLEVEL% NEQ 0 (
        echo [build-backend] ERROR: failed to install studio Python extras.
        exit /b %ERRORLEVEL%
    )
)

:: Run PyInstaller
"%PYTHON_CMD%" -m PyInstaller ^
    --name backend ^
    --onedir ^
    --noconfirm ^
    --distpath "%DIST%" ^
    --workpath "%BUILD_TMP%" ^
    --specpath "%BUILD_TMP%" ^
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
    --exclude-module chromadb.test ^
    --exclude-module pytest ^
    "%ROOT%\studio\backend\main.py"

if %ERRORLEVEL% NEQ 0 (
    echo [build-backend] ERROR: PyInstaller failed.
    exit /b %ERRORLEVEL%
)

if exist "%DIST%\backend\_internal\chromadb\test" (
    echo [build-backend] Removing packaged Chroma test data.
    rmdir /s /q "%DIST%\backend\_internal\chromadb\test"
)

if not exist "%DIST%\backend\backend.exe" (
    echo [build-backend] ERROR: backend.exe was not created at %DIST%\backend\backend.exe
    exit /b 1
)

echo [build-backend] Done. Binary at: %DIST%\backend\backend.exe
endlocal
