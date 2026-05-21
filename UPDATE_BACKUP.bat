@echo off
REM UniFi Protect Recovery Codes - Quick Update Script
REM Double-click this file to download the latest backup from your NVR

echo =============================================
echo UniFi Protect Recovery Codes - Quick Update
echo =============================================
echo.

REM Check if pscp exists
where pscp >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: pscp not found!
    echo Please install PuTTY from https://www.putty.org/
    echo.
    pause
    exit /b 1
)

echo Downloading latest recovery codes from NVR...
echo.

REM Download the file
REM IMPORTANT: Edit the line below with YOUR NVR IP and password before using!
pscp -batch -l root -pw "YOUR_PASSWORD" YOUR_NVR_IP:/root/unifi_protect_recovery_backups/recovery_codes_latest.csv "%~dp0recovery_codes_backup.csv"

if %errorlevel% equ 0 (
    echo.
    echo SUCCESS! Recovery codes updated.
    echo.
    echo File saved to: %~dp0recovery_codes_backup.csv
    echo.
    echo You can now open recovery_codes_backup.csv in Excel
    echo.
) else (
    echo.
    echo ERROR: Failed to download file
    echo Please check your network connection and server status
    echo.
)

echo =============================================
echo.
pause
