# UniFi Protect Recovery Codes - Download Latest Backup
# This script downloads the most recent recovery codes CSV from your NVR
#
# Author:  KCCS <info@kccsonline.com> (https://kccsonline.com)
# License: MIT
# Copyright (c) 2026 KCCS - kccsonline.com

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "UniFi Protect Recovery Codes Backup Updater" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# Configuration - EDIT THESE VALUES FOR YOUR SETUP
$ServerIP = "YOUR_NVR_IP"          # Example: 192.168.1.100
$Username = "root"
$Password = "YOUR_PASSWORD"        # Your NVR SSH password
$RemotePath = "/root/unifi_protect_recovery_backups/recovery_codes_latest.csv"
$LocalPath = "$PSScriptRoot\recovery_codes_backup.csv"

# Check if pscp is available
$pscpPath = Get-Command pscp -ErrorAction SilentlyContinue

if (-not $pscpPath) {
    Write-Host "ERROR: pscp not found in PATH!" -ForegroundColor Red
    Write-Host "Please install PuTTY or add pscp.exe to your PATH" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Download PuTTY from: https://www.putty.org/" -ForegroundColor Yellow
    exit 1
}

Write-Host "Connecting to UniFi Protect NVR at $ServerIP..." -ForegroundColor Green
Write-Host ""

# Download the latest CSV
try {
    $result = & pscp -batch -l $Username -pw $Password "${ServerIP}:${RemotePath}" $LocalPath 2>&1

    if ($LASTEXITCODE -eq 0) {
        Write-Host "SUCCESS! Recovery codes updated." -ForegroundColor Green
        Write-Host ""
        Write-Host "File saved to: $LocalPath" -ForegroundColor Cyan

        # Count devices
        $lineCount = (Get-Content $LocalPath | Measure-Object -Line).Lines - 1
        Write-Host "Total devices in backup: $lineCount" -ForegroundColor Cyan

        # Show timestamp
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Write-Host "Updated: $timestamp" -ForegroundColor Cyan

        Write-Host ""
        Write-Host "You can now open recovery_codes_backup.csv in Excel" -ForegroundColor Yellow
    } else {
        Write-Host "ERROR: Failed to download file" -ForegroundColor Red
        Write-Host $result -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
