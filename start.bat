@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Vira Translator Studio - Launcher
cd /d "%~dp0"
cls

REM ============================================================
REM Vira Translator Studio - Windows Launcher
REM Python + Django + Next.js
REM Automatic retries for package installation
REM ============================================================

set "MAX_RETRIES=5"

echo.
echo ============================================================
echo     VIRA TRANSLATOR STUDIO - Launcher
echo ============================================================
echo.

REM ------------------------------------------------------------
REM [1/4] Check prerequisites
REM ------------------------------------------------------------

echo [1/4] Checking prerequisites...

set "PYCMD="
set "PYVER="

for /f "delims=" %%v in ('python -c "import sys; print(sys.version.split()[0])" 2^>nul') do (
    set "PYVER=%%v"
    set "PYCMD=python"
)

if not defined PYCMD (
    for /f "delims=" %%v in ('py -3 -c "import sys; print(sys.version.split()[0])" 2^>nul') do (
        set "PYVER=%%v"
        set "PYCMD=py -3"
    )
)

if not defined PYCMD goto fail_python

%PYCMD% -c "import sys; sys.exit(0 if sys.version_info[0]==3 and 10<=sys.version_info[1]<=12 else 1)" >nul 2>&1
if errorlevel 1 goto fail_python_badversion

echo [OK] Python %PYVER%

set "NODEVER="
for /f "delims=" %%v in ('node -v 2^>nul') do set "NODEVER=%%v"

if not defined NODEVER goto fail_node

set "NODE_STR=%NODEVER:v=%"
for /f "tokens=1,2 delims=." %%a in ("%NODE_STR%") do (
    set "NODE_MAJOR=%%a"
    set "NODE_MINOR=%%b"
)

if not defined NODE_MAJOR goto fail_node
if not defined NODE_MINOR goto fail_node

if !NODE_MAJOR! GTR 18 goto node_ok
if !NODE_MAJOR! EQU 18 (
    if !NODE_MINOR! GEQ 18 goto node_ok
)
goto fail_node_old

:node_ok
where npm >nul 2>&1
if errorlevel 1 goto fail_node

echo [OK] Node.js %NODEVER%
echo.

REM ------------------------------------------------------------
REM [2/4] Backend: virtual environment + dependencies + database
REM ------------------------------------------------------------

echo [2/4] Preparing Django backend...

if not exist "backend\requirements-core.txt" (
    echo [X] backend\requirements-core.txt not found.
    goto fail
)

if not exist "backend\.venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    %PYCMD% -m venv backend\.venv
    if errorlevel 1 (
        echo [X] Virtual environment creation failed.
        goto fail
    )
)

set "VENV_PY=%~dp0backend\.venv\Scripts\python.exe"

call :retry_core_requirements
if errorlevel 1 goto fail_python_packages

pushd backend

echo Checking database migrations...
.venv\Scripts\python.exe manage.py migrate --noinput
if errorlevel 1 (
    echo [X] Database migration failed.
    popd
    goto fail
)

popd
echo [OK] Core backend dependencies and database ready.
echo OCR and LaMa are optional; run install-ai.bat to add them.
echo.

REM ------------------------------------------------------------
REM [3/4] Frontend: Node dependencies
REM ------------------------------------------------------------

echo [3/4] Preparing Next.js frontend...

if not exist "frontend\package.json" (
    echo [X] frontend\package.json not found.
    goto fail
)

if not exist "frontend\node_modules\next\package.json" (
    pushd frontend
    call :retry_npm_install
    if errorlevel 1 (
        popd
        goto fail_npm
    )
    popd
) else (
    echo [OK] Next.js package already exists.
)

echo [OK] Frontend dependencies ready.
echo.

REM ------------------------------------------------------------
REM [4/4] Start servers
REM ------------------------------------------------------------

echo [4/4] Starting servers...

set "BACKEND_UP=0"
set "FRONTEND_UP=0"

for /f "delims=" %%a in ('powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { 'YES' }" 2^>nul') do set "BACKEND_UP=1"

for /f "delims=" %%a in ('powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue) { 'YES' }" 2^>nul') do set "FRONTEND_UP=1"

if "%BACKEND_UP%"=="1" (
    echo Backend already running on port 8000.
) else (
    echo [START] Launching Django backend...
    start "Vira Backend" /D "%~dp0backend" cmd /k ".venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000"
    echo [START] Backend launch command issued.
    call :wait_backend
    if errorlevel 1 goto fail
)

if "%FRONTEND_UP%"=="1" (
    echo Frontend already running on port 3000.
) else (
    echo [START] Launching Next.js frontend...
    start "Vira Frontend" /D "%~dp0frontend" cmd /k "npm run dev"
    echo [START] Frontend launch command issued.
    call :wait_frontend
)

start "" "http://localhost:3000"

echo.
echo ============================================================
echo  Vira Translator Studio launched.
echo  Frontend: http://localhost:3000
echo  Backend : http://127.0.0.1:8000
echo.
echo  Keep the server windows open while using the application.
echo ============================================================
echo.
ping -n 6 127.0.0.1 >nul
exit /b 0

REM ============================================================
REM Wait helpers
REM ============================================================

:wait_backend
echo Waiting for backend to respond...
set /a BTRIES=0

:wait_backend_loop
powershell -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/api/' -TimeoutSec 2; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo [OK] Backend responding on 8000.
    exit /b 0
)
set /a BTRIES+=1
if !BTRIES! GEQ 30 (
    echo [X] Backend did not become ready. Check the backend window for errors.
    exit /b 1
)
ping -n 3 127.0.0.1 >nul
goto wait_backend_loop

:wait_frontend
echo Waiting for frontend to respond...
set /a WAITTRIES=0

:wait_frontend_loop
powershell -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:3000' -TimeoutSec 3; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 exit /b 0
set /a WAITTRIES+=1
if !WAITTRIES! GEQ 60 (
    echo Frontend has not responded yet. Opening browser anyway.
    exit /b 0
)
ping -n 3 127.0.0.1 >nul
goto wait_frontend_loop

REM ============================================================
REM Retry functions
REM ============================================================

:retry_core_requirements
set "RETRY_COUNT=0"

:requirements_loop
set /a RETRY_COUNT+=1
echo.
echo [pip] Core requirements attempt !RETRY_COUNT!/%MAX_RETRIES%...

"%VENV_PY%" -m pip install --prefer-binary -r "%~dp0backend\requirements-core.txt"
if not errorlevel 1 exit /b 0

if !RETRY_COUNT! GEQ %MAX_RETRIES% exit /b 1

set /a RETRY_DELAY=!RETRY_COUNT!*3
echo Installation failed. Retrying in !RETRY_DELAY! seconds...
timeout /t !RETRY_DELAY! /nobreak >nul
goto requirements_loop

:retry_npm_install
set "RETRY_COUNT=0"

:npm_install_loop
set /a RETRY_COUNT+=1
echo.
echo [npm] Install attempt !RETRY_COUNT!/%MAX_RETRIES%...

call npm install
if not errorlevel 1 exit /b 0

if !RETRY_COUNT! GEQ %MAX_RETRIES% exit /b 1

set /a RETRY_DELAY=!RETRY_COUNT!*3
echo Installation failed. Retrying in !RETRY_DELAY! seconds...
timeout /t !RETRY_DELAY! /nobreak >nul
goto npm_install_loop

REM ============================================================
REM Friendly errors
REM ============================================================

:fail_python
echo.
echo [X] Python 3.10, 3.11 or 3.12 was not found.
echo Install Python from https://www.python.org/downloads/
echo Enable "Add Python to PATH" during installation.
goto fail

:fail_python_badversion
echo.
echo [X] Unsupported Python version: %PYVER%
echo Required: Python 3.10, 3.11 or 3.12.
goto fail

:fail_node
echo.
echo [X] Node.js or npm was not found.
echo Install Node.js from https://nodejs.org/
goto fail

:fail_node_old
echo.
echo [X] Node.js %NODEVER% is too old.
echo Required: Node.js 18.18 or newer.
goto fail

:fail_python_packages
echo.
echo [X] Python package installation failed after retries.
echo Check your internet connection and backend\requirements-core.txt.
echo Run start.bat again to retry.
goto fail

:fail_npm
echo.
echo [X] npm installation failed after retries.
echo Check your internet connection and package.json.
echo Run start.bat again to retry.
goto fail

:fail
echo.
echo ============================================================
echo  Launcher stopped because an error occurred.
echo  Review the error messages above.
echo ============================================================
echo.
pause
exit /b 1