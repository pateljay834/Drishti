@echo off
chcp 65001 >nul 2>&1
title DRISHTI v5 - India News & Markets Platform

echo.
echo  +----------------------------------------------------------+
echo  ^|   DRISHTI v5 - India News ^& Markets Platform            ^|
echo  ^|   Live Markets . Currency . 103 RSS Feeds . 36 States   ^|
echo  +----------------------------------------------------------+
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python not found in PATH.
    echo  Install Python 3.10+ from https://www.python.org/downloads/
    echo  Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo  Found: %%i

if not exist ".cache" mkdir ".cache"

echo.
echo  [1/3] Installing dependencies...
python -m pip install -r requirements.txt --quiet --disable-pip-version-check
if %errorlevel% neq 0 (
    echo  [ERROR] Failed to install dependencies.
    echo  Try: python -m pip install -r requirements.txt
    pause
    exit /b 1
)
echo  [2/3] Dependencies ready.
echo  [3/3] Starting DRISHTI v5...
echo.
echo  Open browser at: http://127.0.0.1:5050
echo  Markets refresh every 5 min, News every 15 min.
echo  Press Ctrl+C to stop.
echo.

start "" cmd /c "timeout /t 4 /nobreak >nul && start http://127.0.0.1:5050"
python app.py

echo.
echo  DRISHTI stopped.
pause
