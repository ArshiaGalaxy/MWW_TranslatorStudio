@echo off
setlocal EnableExtensions
title Vira Translator Studio - Install AI Features
cd /d "%~dp0"

echo.
echo ============================================================
echo   VIRA TRANSLATOR STUDIO - Optional AI Installer
echo ============================================================
echo.
echo This installs PaddleOCR, PaddlePaddle, PyTorch and LaMa.
echo The download can be large and may require several gigabytes
echo of temporary disk space and a stable internet connection.
echo.

if not exist "backend\.venv\Scripts\python.exe" (
    echo [X] Core environment not found.
    echo First run start.bat once to create the virtual environment.
    pause
    exit /b 1
)

echo Installing optional AI dependencies...
"backend\.venv\Scripts\python.exe" -m pip install --prefer-binary -r "backend\requirements-ai.txt"
if errorlevel 1 (
    echo.
    echo [X] AI dependency installation failed.
    echo Check your internet connection and available disk space.
    pause
    exit /b 1
)

echo.
echo [OK] Optional AI dependencies installed.
echo Restart Vira Translator Studio before using OCR or LaMa.
pause
