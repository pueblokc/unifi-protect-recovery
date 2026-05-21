@echo off
title UniFi Protect Recovery Code Backup
cd /d "%~dp0"

REM Run the PowerShell GUI (no Python required)
powershell -ExecutionPolicy Bypass -File "%~dp0UniFi-Protect-Backup.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo If you see a security error, right-click this file
    echo and select "Run as administrator"
    echo.
    pause
)
