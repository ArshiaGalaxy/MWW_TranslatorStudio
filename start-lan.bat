@echo off
setlocal EnableDelayedExpansion
title Vira Translator Studio - LAN Launcher
cd /d "%~dp0"
cls

REM =====================================================================
REM  Vira Translator Studio - LAN launcher
REM
REM  Same as start.bat, but the site is also reachable from other
REM  devices on your WiFi (phone, tablet, another PC).
REM
REM  First time : run start.bat once - it installs everything
REM               (Python venv + packages, database, npm packages).
REM  This script: starts the servers, opens port 3000 in the firewall
REM               (one time) and prints the URL to open on your phone.
REM
REM  Ports : frontend  http://<LAN-IP>:3000   <- shared on the LAN
REM          backend   http://127.0.0.1:8000  <- stays local; the Next.js
REM              proxy on the laptop forwards /api and /media to it,
REM              so the phone does not (and should not) reach Django.
REM =====================================================================

echo.
echo  ============================================================
echo      Vira  TRANSLATOR  STUDIO   -   LAN  Launcher
echo  ============================================================
echo.

REM ------------------------------------------------------------
REM  [1/4] Installed? (this script does not install anything)
REM ------------------------------------------------------------
echo  [1/4] Checking installation...

if not exist "backend\.venv\Scripts\python.exe" (
    echo        [X] Python environment not found.
    goto notinstalled
)
if not exist "frontend\node_modules\next\package.json" (
    echo        [X] Frontend packages not found.
    goto notinstalled
)
echo        [OK] Backend and frontend are installed.
echo.

REM Quick safety net: apply pending migrations just like start.bat does.
pushd backend
.venv\Scripts\python.exe manage.py migrate --noinput >nul 2>nul
popd

REM ------------------------------------------------------------
REM  [2/4] Firewall : allow incoming TCP 3000 (one-time)
REM ------------------------------------------------------------
echo  [2/4] Firewall rule for port 3000...

set "FWRULE=Vira Translator Studio LAN (TCP 3000)"
netsh advfirewall firewall show rule name="%FWRULE%" >nul 2>nul
if errorlevel 1 (
    netsh advfirewall firewall add rule name="%FWRULE%" dir=in action=allow protocol=TCP localport=3000 profile=private,domain >nul 2>nul
    if errorlevel 1 (
        echo        [!] Could not add the firewall rule ^(needs admin rights^).
        echo            If Windows asks about allowing Node.js - click "Allow".
        echo            If it still does not work: right-click start-lan.bat
        echo            and "Run as administrator" once, or add the rule manually.
    ) else (
        echo        [OK] Port 3000 opened for private networks.
    )
) else (
    echo        [OK] Rule already present.
)
echo.

REM ------------------------------------------------------------
REM  [3/4] Find this computer's WiFi/LAN (IPv4) address
REM ------------------------------------------------------------
echo  [3/4] Finding this computer's WiFi/LAN address...

set "LANIP="
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254)' } | Sort-Object PrefixOrigin, IPAddress | Select-Object -First 1).IPAddress"`) do set "LANIP=%%i"

if not defined LANIP for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /i "IPv4"') do if not defined LANIP set "LANIP=%%i"

if defined LANIP (
    echo        [OK] LAN address   :  !LANIP!
) else (
    echo        [!] No LAN address found - run 'ipconfig' and use the
    echo            IPv4 Address of your WiFi adapter instead.
)
echo.

REM ------------------------------------------------------------
REM  [4/4] Start servers (backend stays local, frontend shared)
REM ------------------------------------------------------------
echo  [4/4] Starting servers...

set "BACKEND_UP=0"
for /f %%a in ('netstat -ano 2^>nul ^| findstr /r /c:":8000 .*LISTENING"') do set "BACKEND_UP=1"
set "FRONTEND_UP=0"
for /f %%a in ('netstat -ano 2^>nul ^| findstr /r /c:":3000 .*LISTENING"') do set "FRONTEND_UP=1"

if "%BACKEND_UP%"=="1" (
    echo        Backend  : already running   -  http://127.0.0.1:8000  ^(local only^)
) else (
    echo        Backend  : Django API        -  starting in a new window...
    start "Vira Backend (Django :8000)" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe manage.py recover_jobs && .venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000"
)

if "%FRONTEND_UP%"=="1" (
    echo        Frontend : already running   -  http://localhost:3000
    echo                    ^(if it was started with start.bat it already
    echo                     accepts LAN connections - the Next start server
    echo                     listens on all interfaces by default^)
) else (
    echo        Frontend : Next.js site      -  starting in a new window...
    start "Vira Frontend (Next :3000 LAN)" cmd /k "cd /d %~dp0frontend && call npm run start -- -H 0.0.0.0"
)
echo.

if "%FRONTEND_UP%"=="1" goto showit

echo        Waiting for the site to come up  ^(a few seconds; longer after setup^)...
set /a WAITTRIES=0
:waitloop
powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing -Uri http://localhost:3000 -TimeoutSec 2 | Out-Null; exit 0}catch{exit 1}" >nul 2>nul
if not errorlevel 1 goto showit
set /a WAITTRIES+=1
if !WAITTRIES! GEQ 60 goto showit
<nul set /p "WAITDOT=."
timeout /t 2 /nobreak >nul
goto waitloop

:showit
echo.
start "" "http://localhost:3000"

echo  ============================================================
echo   DONE  -  the app is now also available on the network
echo.
echo     On this laptop   :  http://localhost:3000
if defined LANIP (
    echo     On phone/tablet  :  http://!LANIP!:3000
) else (
    echo     On phone/tablet  :  http://YOUR-LAN-IP:3000   ^(run 'ipconfig'^)
)
echo.
echo   - Keep the two server windows open while using the app.
echo   - There is no login: everyone on this WiFi can open the studio.
echo   - To stop: close those two windows.
echo  ============================================================
echo.
ping -n 16 127.0.0.1 >nul
exit /b 0

REM ------------------------------------------------------------
REM  Not installed yet - friendly hint
REM ------------------------------------------------------------
:notinstalled
echo.
echo        Run start.bat first - it installs everything on the first
echo        run ^(Python venv, packages, database, npm packages^).
echo        After that, start-lan.bat works immediately.
echo.
pause
exit /b 1
