@echo off
title OTP Share - Live Receiver
cd /d "%~dp0"

echo ========================================================
echo               OTP SHARE - LIVE RECEIVER
echo ========================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python from https://www.python.org/
    pause
    exit /b 1
)

echo [1/2] Checking dependencies...
pip install -r requirements.txt --quiet --disable-pip-version-check

echo [2/2] Starting server at http://localhost:8000 ...
start "" "http://localhost:8000"

python main.py
pause
