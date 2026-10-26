
@echo off
setlocal EnableExtensions EnableDelayedExpansion
title MWW Translator Studio - Launcher
cd /d "%~dp0"
cls

REM ============================================================
REM MWW Translator Studio - Windows Launcher
REM Python + Django + Next.js
REM Automatic retries for package installation
REM ============================================================

set "MAX_RETRIES=5"

echo.
echo ============================================================
echo     MWW TRANSLATOR STUDIO - Launcher
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

node -e "const p=process.versions.node.split('.');process.exit(+p[0]>18||(+p[0]==18&&+p[1]>=18)?0:1)" >nul 2>&1
if errorlevel 1 goto fail_node_old

where npm >nul 2>&1
if errorlevel 1 goto fail_node

echo [OK] Node.js %NODEVER%
echo.

REM ------------------------------------------------------------
REM [2/4] Backend: virtual environment + dependencies + database
REM ------------------------------------------------------------

echo [2/4] Preparing Django backend...

if not exist "backend\requirements.txt" (
    echo [X] backend\requirements.txt not found.
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

call :retry_pip_upgrade
if errorlevel 1 goto fail_python_packages

call :retry_requirements
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
echo [OK] Backend dependencies and database ready.
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
    echo Starting Django backend...
    start "MWW Backend - Django" cmd /k "cd /d ""%~dp0backend"" && ""%~dp0backend\.venv\Scripts\python.exe"" manage.py recover_jobs && ""%~dp0backend\.venv\Scripts\python.exe"" manage.py runserver 127.0.0.1:8000"
)

if "%FRONTEND_UP%"=="1" (
    echo Frontend already running on port 3000.
) else (
    echo Starting Next.js frontend...
    start "MWW Frontend - Next.js" cmd /k "cd /d ""%~dp0frontend"" && npm run dev"
)

echo.
echo Waiting for frontend to respond...

set "WAITTRIES=0"

:waitloop
powershell -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:3000' -TimeoutSec 3; exit 0 } catch { exit 1 }" >nul 2>&1

if not errorlevel 1 goto open_browser

set /a WAITTRIES+=1
if !WAITTRIES! GEQ 60 goto open_anyway

timeout /t 2 /nobreak >nul
goto waitloop

:open_anyway
echo Frontend has not responded yet. Opening browser anyway.

:open_browser
start "" "http://localhost:3000"

echo.
echo ============================================================
echo  MWW Translator Studio launched.
echo  Frontend: http://localhost:3000
echo  Backend : http://127.0.0.1:8000
echo.
echo  Keep the server windows open while using the application.
echo ============================================================
echo.
timeout /t 5 /nobreak >nul
exit /b 0

REM ============================================================
REM Retry functions
REM ============================================================

:retry_pip_upgrade
set "RETRY_COUNT=0"

:pip_upgrade_loop
set /a RETRY_COUNT+=1
echo.
echo [pip] Upgrade attempt !RETRY_COUNT!/%MAX_RETRIES%...

"%VENV_PY%" -m pip install --upgrade pip
if not errorlevel 1 exit /b 0

if !RETRY_COUNT! GEQ %MAX_RETRIES% exit /b 1

set /a RETRY_DELAY=RETRY_COUNT*3
echo Installation failed. Retrying in !RETRY_DELAY! seconds...
timeout /t !RETRY_DELAY! /nobreak >nul
goto pip_upgrade_loop

:retry_requirements
set "RETRY_COUNT=0"

:requirements_loop
set /a RETRY_COUNT+=1
echo.
echo [pip] Requirements attempt !RETRY_COUNT!/%MAX_RETRIES%...

"%VENV_PY%" -m pip install --prefer-binary -r "%~dp0backend\requirements.txt"
if not errorlevel 1 exit /b 0

if !RETRY_COUNT! GEQ %MAX_RETRIES% exit /b 1

set /a RETRY_DELAY=RETRY_COUNT*3
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

set /a RETRY_DELAY=RETRY_COUNT*3
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
echo Check your internet connection and requirements.txt.
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
