@echo off
title Restream IPTV Server
cd /d "%~dp0"

echo ========================================================
echo        Starting Restream IPTV Server ^& Web Player
echo ========================================================
echo.

:: Check if python is available
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found in PATH!
    echo Please make sure Python 3.8+ is installed.
    pause
    exit /b
)

:: Open browser after a brief delay
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:8080"

:: Start the Python server
python run_server.py

pause
