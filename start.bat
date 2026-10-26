@echo off
setlocal EnableDelayedExpansion
title MWW Translator Studio - Launcher
cd /d "%~dp0"
cls

REM =====================================================================
REM  MWW Translator Studio - one-click launcher for Windows
REM
REM  First run : downloads and installs everything needed
REM              (Python venv + packages, database, npm packages),
REM              then starts both servers and opens the browser.
REM  Later runs: no downloads - just starts the servers in seconds
REM              and opens the browser.
REM
REM  Ports used : backend  http://127.0.0.1:8000   frontend http://localhost:3000
REM =====================================================================

echo.
echo  ============================================================
echo      MWW  TRANSLATOR  STUDIO   -   Launcher
echo  ============================================================
echo.

REM ------------------------------------------------------------
REM  [1/4] Check prerequisites (Python + Node.js)
REM ------------------------------------------------------------
echo  [1/4] Checking prerequisites...

set "PYCMD="
set "PYVER="
for /f "tokens=*" %%v in ('python -c "import sys; print(sys.version.split()[0])" 2^>nul') do (set "PYVER=%%v" & set "PYCMD=python")
if not defined PYCMD for /f "tokens=*" %%v in ('py -3 -c "import sys; print(sys.version.split()[0])" 2^>nul') do (set "PYVER=%%v" & set "PYCMD=py -3")

if not defined PYCMD (
    echo        [X] Python not found.
    goto fail_python
)
!PYCMD! -c "import sys; sys.exit(0 if sys.version_info[0]==3 and 10<=sys.version_info[1]<=12 else 1)" >nul 2>nul
if errorlevel 1 (
    echo        [X] Found Python !PYVER! - this needs Python 3.10, 3.11 or 3.12.
    goto fail_python_badversion
)
echo        [OK] Python !PYVER!   !PYCMD!

set "NODEVER="
for /f "tokens=*" %%v in ('node -v 2^>nul') do set "NODEVER=%%v"
if not defined NODEVER (
    echo        [X] Node.js not found.
    goto fail_node
)
node -e "const p=process.versions.node.split('.');const ok=+p[0]>18||(+p[0]==18&&+p[1]>=18);process.exit(ok?0:1)" >nul 2>nul
if errorlevel 1 (
    echo        [X] Node.js %NODEVER% is too old - need 18.18 or newer.
    goto fail_node_old
)
where npm >nul 2>nul
if errorlevel 1 (
    echo        [X] npm not found - Node.js installed without npm.
    goto fail_node
)
echo        [OK] Node.js %NODEVER%
echo.

REM ------------------------------------------------------------
REM  [2/4] Backend : Python environment + database
REM ------------------------------------------------------------
set "NEEDSETUP=0"
if not exist "backend\.venv\Scripts\python.exe" set "NEEDSETUP=1"

echo  [2/4] Backend ^(Django^)...
if "%NEEDSETUP%"=="1" (
    echo        First run: creating Python environment and downloading
    echo        packages ^(Django, Pillow, numpy...^) - this happens once.
    !PYCMD! -m venv backend\.venv
    if errorlevel 1 (
        echo        [X] Could not create the Python environment. See message above.
        pause
        exit /b 1
    )
    backend\.venv\Scripts\python.exe -m pip install -q --upgrade pip
    backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-core.txt
    if errorlevel 1 (
        echo.
        echo        [X] Downloading packages failed.
        echo            Check your internet connection and run start.bat again.
        echo            ^(Everything downloaded so far is reused - nothing starts over.^)
        pause
        exit /b 1
    )
) else (
    echo        [OK] Python environment ready.
)

pushd backend
.venv\Scripts\python.exe manage.py migrate --noinput >nul 2>&1
if errorlevel 1 (
    popd
    echo        [X] Database setup failed. Running again with output to show why:
    echo.
    cd /d "%~dp0backend"
    .venv\Scripts\python.exe manage.py migrate --noinput
    echo.
    pause
    exit /b 1
)
popd
echo        [OK] Database ready.
echo.

REM ------------------------------------------------------------
REM  [3/4] Frontend : Node packages
REM ------------------------------------------------------------
set "NEEDNPM=0"
if not exist "frontend\node_modules\next\package.json" set "NEEDNPM=1"

echo  [3/4] Frontend ^(Next.js^)...
if "%NEEDNPM%"=="1" (
    echo        First run: downloading frontend packages - can take a few minutes.
    cd /d "%~dp0frontend"
    call npm install
    if errorlevel 1 (
        echo.
        echo        [X] npm install failed.
        echo            Check that Node.js 18+ is installed and your internet works,
        echo            then run start.bat again. Already-downloaded packages are reused.
        pause
        exit /b 1
    )
    cd /d "%~dp0"
) else (
    echo        [OK] Frontend packages ready.
)
echo.

REM ------------------------------------------------------------
REM  [4/4] Start servers in their own windows + open the browser
REM ------------------------------------------------------------
echo  [4/4] Starting servers...

set "BACKEND_UP=0"
for /f %%a in ('netstat -ano 2^>nul ^| findstr /r /c:":8000 .*LISTENING"') do set "BACKEND_UP=1"
set "FRONTEND_UP=0"
for /f %%a in ('netstat -ano 2^>nul ^| findstr /r /c:":3000 .*LISTENING"') do set "FRONTEND_UP=1"

if "%BACKEND_UP%"=="1" (
    echo        Backend  : already running   -  http://127.0.0.1:8000
) else (
    echo        Backend  : Django API        -  starting in a new window...
    start "MWW Backend (Django :8000)" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe manage.py recover_jobs && .venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000"
)

if "%FRONTEND_UP%"=="1" (
    echo        Frontend : already running   -  http://localhost:3000
) else (
    echo        Frontend : Next.js site      -  starting in a new window...
    start "MWW Frontend (Next :3000)" cmd /k "cd /d %~dp0frontend && call npm run dev"
)
echo.

if "%FRONTEND_UP%"=="1" goto openit

echo        Waiting for the site to come up  ^(a few seconds; longer after setup^)...
set /a WAITTRIES=0
:waitloop
powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing -Uri http://localhost:3000 -TimeoutSec 2 | Out-Null; exit 0}catch{exit 1}" >nul 2>nul
if not errorlevel 1 goto openit
set /a WAITTRIES+=1
if !WAITTRIES! GEQ 60 goto openanyway
<nul set /p "WAITDOT=."
timeout /t 2 /nobreak >nul
goto waitloop

:openanyway
echo.
echo        Frontend did not respond yet - opening the browser anyway.
:openit
echo.
start "" "http://localhost:3000"

echo  ============================================================
echo   DONE  -  the app is open at   http://localhost:3000
echo.
echo   - Keep the two server windows open while using the app.
echo   - To stop: close those two windows.
echo   - Next time: double-click start.bat again - no downloads,
echo     it starts in seconds.
echo  ============================================================
echo.
ping -n 16 127.0.0.1 >nul
exit /b 0

REM ------------------------------------------------------------
REM  Friendly error messages
REM ------------------------------------------------------------
:fail_python
echo        [X] Python 3.10, 3.11 or 3.12 was not found on this computer.
echo            Install it from  https://www.python.org/downloads/
echo            IMPORTANT: tick "Add python.exe to PATH" on the first
echo            installer screen, then run start.bat again.
echo.
pause
exit /b 1

:fail_python_badversion
echo        [X] This project needs Python 3.10, 3.11 or 3.12.
echo            ^(Python 3.13 is too new for some of the AI packages.^)
echo            Install a supported version from  https://www.python.org/downloads/
echo            Tip: tick "Add python.exe to PATH" during install.
echo.
pause
exit /b 1

:fail_node
echo        [X] Node.js was not found on this computer.
echo            Install the LTS version from  https://nodejs.org/
echo            then close this window and run start.bat again.
echo.
pause
exit /b 1

:fail_node_old
echo        [X] Node.js %NODEVER% is too old - this project needs 18.18 or newer.
echo            Install the current LTS version from  https://nodejs.org/
echo            then close this window and run start.bat again.
echo.
pause
exit /b 1
