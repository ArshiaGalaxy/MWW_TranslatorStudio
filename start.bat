@echo off
setlocal EnableDelayedExpansion
title MWW Translator Studio - Launcher
cd /d "%~dp0"

echo ==================================================
echo   MWW Translator Studio  -  /  مترجم استودیو
echo ==================================================
echo.

REM -------------------------------------------------
REM 1) Backend: Python venv (create on first run)
REM -------------------------------------------------
if not exist "backend\.venv\Scripts\python.exe" (
    echo [Setup] Virtual environment not found - creating it (first run only)...
    python -m venv backend\.venv || (echo [Error] Python was not found. Install Python 3.10+ from python.org and try again. & pause & exit /b 1)
    echo [Setup] Installing core packages...
    backend\.venv\Scripts\python.exe -m pip install --upgrade pip -q
    backend\.venv\Scripts\python.exe -m pip install -q -r backend\requirements-core.txt || (echo [Error] pip install failed. Check your internet connection. & pause & exit /b 1)
)

REM -------------------------------------------------
REM 2) Backend: database (create on first run)
REM -------------------------------------------------
if not exist "backend\db.sqlite3" (
    echo [Setup] Database not found - running migrations (first run only)...
    backend\.venv\Scripts\python.exe backend\manage.py migrate
)

REM -------------------------------------------------
REM 3) Frontend: node_modules (install on first run)
REM -------------------------------------------------
if not exist "frontend\node_modules\next\package.json" (
    echo [Setup] Installing frontend packages - this can take a few minutes on first run...
    cd /d "%~dp0frontend"
    call npm install || (echo [Error] npm install failed. Check that Node.js 18+ is installed. & pause & exit /b 1)
    cd /d "%~dp0"
)

REM -------------------------------------------------
REM 4) Start both servers in their own windows
REM -------------------------------------------------
echo [Start] Launching backend  (Django  -  http://127.0.0.1:8000)
start "MWW Backend (Django :8000)" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe manage.py recover_jobs && .venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000"

echo [Start] Launching frontend (Next.js -  http://localhost:3000)
start "MWW Frontend (Next :3000)" cmd /k "cd /d %~dp0frontend && npm run dev"

REM -------------------------------------------------
REM 5) Wait for the frontend, then open default browser
REM -------------------------------------------------
echo [Start] Waiting for the frontend to come up...
set /a tries=0
:waitloop
curl -s -o nul --max-time 2 http://localhost:3000
if not errorlevel 1 goto openit
set /a tries+=1
if !tries! GEQ 150 (
    echo [Warn] Frontend did not respond in time - opening the browser anyway...
    goto openit
)
timeout /t 2 /nobreak >nul
goto waitloop

:openit
start "" "http://localhost:3000"
echo.
echo [Done] Browser opened at http://localhost:3000
echo        Close the "MWW Backend" and "MWW Frontend" windows to stop the servers.
echo        (This launcher window can be closed now.)
timeout /t 8 >nul
