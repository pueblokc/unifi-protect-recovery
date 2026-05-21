@echo off
title UniFi Protect Recovery Code Backup
cd /d "%~dp0"

REM Check if Python is available
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python is not installed or not in PATH
    echo.
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

REM Check if paramiko is installed
python -c "import paramiko" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Installing required dependency: paramiko...
    echo.
    python -m pip install paramiko
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo ERROR: Failed to install paramiko
        echo Please run: python -m pip install paramiko
        echo.
        pause
        exit /b 1
    )
    echo.
    echo Dependency installed successfully!
    echo.
)

REM Run the GUI application
python "%~dp0unifi_protect_backup_gui.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Application exited with an error.
    pause
)
