@echo off
title Restream IPTV - Interactive Menu
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found in PATH!
    pause
    exit /b
)

python main.py

pause
