# UniFi Protect Recovery Code Backup Tool
# Standalone PowerShell GUI - No Python required
# Works on any Windows PC with PowerShell 5.1+ (built into Windows 10/11)
#
# Author:  KCCS <info@kccsonline.com> (https://kccsonline.com)
# License: MIT
# Copyright (c) 2026 KCCS - kccsonline.com

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# Check for plink/pscp (PuTTY tools)
$plinkPath = Get-Command plink -ErrorAction SilentlyContinue
$pscpPath = Get-Command pscp -ErrorAction SilentlyContinue

# Configuration file
$configFile = Join-Path $PSScriptRoot "config.json"

# Every adoptable UniFi Protect device keeps its recovery code in the "password"
# field of its per-type JSON file inside the backup ZIP. Keep this list complete
# or those devices' recovery codes get silently dropped.
$script:DeviceTypes = @('cameras', 'bridges', 'lights', 'speakers', 'aiports', 'sirens', 'viewers')

# Load saved config
function Load-Config {
    if (Test-Path $configFile) {
        try {
            return Get-Content $configFile | ConvertFrom-Json
        } catch {
            return $null
        }
    }
    return $null
}

# Save config (no password)
function Save-Config {
    param($ip, $user, $backupPath, $savePath)
    $config = @{
        nvr_ip = $ip
        username = $user
        backup_path = $backupPath
        save_location = $savePath
    }
    $config | ConvertTo-Json | Set-Content $configFile
}

# Extract recovery codes from ZIP
function Extract-RecoveryCodes {
    param($zipPath)

    $devices = @{}
    foreach ($t in $script:DeviceTypes) { $devices[$t] = @() }
    $validNames = $script:DeviceTypes | ForEach-Object { "$_" + ".json" }

    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = [System.IO.Compression.ZipFile]::OpenRead($zipPath)

        foreach ($entry in $zip.Entries) {
            if ($entry.Name -in $validNames) {
                $stream = $entry.Open()
                $reader = New-Object System.IO.StreamReader($stream)
                $json = $reader.ReadToEnd()
                $reader.Close()
                $stream.Close()

                $data = $json | ConvertFrom-Json
                $type = $entry.Name -replace '\.json$', ''

                foreach ($item in $data) {
                    $devices[$type] += @{
                        name = if ($item.name) { $item.name } else { "Unknown" }
                        model = if ($item.type) { $item.type } else { "Unknown" }
                        mac = if ($item.mac) { $item.mac } else { "N/A" }
                        ip = if ($item.host) { $item.host } else { "N/A" }
                        recovery_code = if ($item.password) { $item.password } else { "N/A" }
                    }
                }
            }
        }
        $zip.Dispose()
    } catch {
        throw "Failed to read ZIP file: $_"
    }

    return $devices
}

# Save to CSV
function Save-ToCSV {
    param($devices, $outputPath)

    $rows = @()
    $rows += "Type,Name,Model,MAC,IP,Recovery Code"

    foreach ($type in $script:DeviceTypes) {
        foreach ($device in $devices[$type]) {
            $typeName = $type.TrimEnd('s')
            $typeName = $typeName.Substring(0,1).ToUpper() + $typeName.Substring(1)
            $row = "`"$typeName`",`"$($device.name)`",`"$($device.model)`",`"$($device.mac)`",`"$($device.ip)`",`"$($device.recovery_code)`""
            $rows += $row
        }
    }

    $rows | Set-Content -Path $outputPath -Encoding UTF8
}

# Create the main form
$form = New-Object System.Windows.Forms.Form
$form.Text = "UniFi Protect Recovery Code Backup"
$form.Size = New-Object System.Drawing.Size(550, 555)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false

# Title
$titleLabel = New-Object System.Windows.Forms.Label
$titleLabel.Text = "UniFi Protect Recovery Code Backup"
$titleLabel.Font = New-Object System.Drawing.Font("Segoe UI", 14, [System.Drawing.FontStyle]::Bold)
$titleLabel.Location = New-Object System.Drawing.Point(20, 15)
$titleLabel.Size = New-Object System.Drawing.Size(500, 30)
$form.Controls.Add($titleLabel)

# Connection Group
$connGroup = New-Object System.Windows.Forms.GroupBox
$connGroup.Text = "NVR Connection"
$connGroup.Location = New-Object System.Drawing.Point(20, 50)
$connGroup.Size = New-Object System.Drawing.Size(495, 150)
$form.Controls.Add($connGroup)

# NVR IP
$ipLabel = New-Object System.Windows.Forms.Label
$ipLabel.Text = "NVR IP Address:"
$ipLabel.Location = New-Object System.Drawing.Point(15, 25)
$ipLabel.Size = New-Object System.Drawing.Size(100, 20)
$connGroup.Controls.Add($ipLabel)

$ipTextBox = New-Object System.Windows.Forms.TextBox
$ipTextBox.Location = New-Object System.Drawing.Point(130, 22)
$ipTextBox.Size = New-Object System.Drawing.Size(200, 20)
$connGroup.Controls.Add($ipTextBox)

# Username
$userLabel = New-Object System.Windows.Forms.Label
$userLabel.Text = "Username:"
$userLabel.Location = New-Object System.Drawing.Point(15, 55)
$userLabel.Size = New-Object System.Drawing.Size(100, 20)
$connGroup.Controls.Add($userLabel)

$userTextBox = New-Object System.Windows.Forms.TextBox
$userTextBox.Location = New-Object System.Drawing.Point(130, 52)
$userTextBox.Size = New-Object System.Drawing.Size(200, 20)
$userTextBox.Text = "root"
$connGroup.Controls.Add($userTextBox)

# Password
$passLabel = New-Object System.Windows.Forms.Label
$passLabel.Text = "Password:"
$passLabel.Location = New-Object System.Drawing.Point(15, 85)
$passLabel.Size = New-Object System.Drawing.Size(100, 20)
$connGroup.Controls.Add($passLabel)

$passTextBox = New-Object System.Windows.Forms.TextBox
$passTextBox.Location = New-Object System.Drawing.Point(130, 82)
$passTextBox.Size = New-Object System.Drawing.Size(200, 20)
$passTextBox.UseSystemPasswordChar = $true
$connGroup.Controls.Add($passTextBox)

$showPassCheck = New-Object System.Windows.Forms.CheckBox
$showPassCheck.Text = "Show"
$showPassCheck.Location = New-Object System.Drawing.Point(340, 82)
$showPassCheck.Size = New-Object System.Drawing.Size(60, 20)
$showPassCheck.Add_CheckedChanged({
    $passTextBox.UseSystemPasswordChar = -not $showPassCheck.Checked
})
$connGroup.Controls.Add($showPassCheck)

# Backup Path
$pathLabel = New-Object System.Windows.Forms.Label
$pathLabel.Text = "Backup Path:"
$pathLabel.Location = New-Object System.Drawing.Point(15, 115)
$pathLabel.Size = New-Object System.Drawing.Size(100, 20)
$connGroup.Controls.Add($pathLabel)

$pathTextBox = New-Object System.Windows.Forms.TextBox
$pathTextBox.Location = New-Object System.Drawing.Point(130, 112)
$pathTextBox.Size = New-Object System.Drawing.Size(345, 20)
$pathTextBox.Text = "/srv/unifi-protect/backups"
$connGroup.Controls.Add($pathTextBox)

# Output Group
$outGroup = New-Object System.Windows.Forms.GroupBox
$outGroup.Text = "Output Settings"
$outGroup.Location = New-Object System.Drawing.Point(20, 205)
$outGroup.Size = New-Object System.Drawing.Size(495, 60)
$form.Controls.Add($outGroup)

# Save Location
$saveLabel = New-Object System.Windows.Forms.Label
$saveLabel.Text = "Save To:"
$saveLabel.Location = New-Object System.Drawing.Point(15, 25)
$saveLabel.Size = New-Object System.Drawing.Size(60, 20)
$outGroup.Controls.Add($saveLabel)

$saveTextBox = New-Object System.Windows.Forms.TextBox
$saveTextBox.Location = New-Object System.Drawing.Point(80, 22)
$saveTextBox.Size = New-Object System.Drawing.Size(310, 20)
$saveTextBox.Text = [Environment]::GetFolderPath("MyDocuments")
$outGroup.Controls.Add($saveTextBox)

$browseBtn = New-Object System.Windows.Forms.Button
$browseBtn.Text = "Browse..."
$browseBtn.Location = New-Object System.Drawing.Point(400, 20)
$browseBtn.Size = New-Object System.Drawing.Size(75, 25)
$browseBtn.Add_Click({
    $folderBrowser = New-Object System.Windows.Forms.FolderBrowserDialog
    $folderBrowser.SelectedPath = $saveTextBox.Text
    if ($folderBrowser.ShowDialog() -eq "OK") {
        $saveTextBox.Text = $folderBrowser.SelectedPath
    }
})
$outGroup.Controls.Add($browseBtn)

# Buttons
$testBtn = New-Object System.Windows.Forms.Button
$testBtn.Text = "Test Connection"
$testBtn.Location = New-Object System.Drawing.Point(130, 275)
$testBtn.Size = New-Object System.Drawing.Size(120, 30)
$form.Controls.Add($testBtn)

$backupBtn = New-Object System.Windows.Forms.Button
$backupBtn.Text = "Backup Recovery Codes"
$backupBtn.Location = New-Object System.Drawing.Point(260, 275)
$backupBtn.Size = New-Object System.Drawing.Size(150, 30)
$backupBtn.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($backupBtn)

# Status
$statusLabel = New-Object System.Windows.Forms.Label
$statusLabel.Text = "Ready"
$statusLabel.Location = New-Object System.Drawing.Point(20, 315)
$statusLabel.Size = New-Object System.Drawing.Size(495, 20)
$statusLabel.ForeColor = [System.Drawing.Color]::Gray
$form.Controls.Add($statusLabel)

# Results
$resultsGroup = New-Object System.Windows.Forms.GroupBox
$resultsGroup.Text = "Results"
$resultsGroup.Location = New-Object System.Drawing.Point(20, 335)
$resultsGroup.Size = New-Object System.Drawing.Size(495, 130)
$form.Controls.Add($resultsGroup)

$resultsTextBox = New-Object System.Windows.Forms.TextBox
$resultsTextBox.Location = New-Object System.Drawing.Point(10, 20)
$resultsTextBox.Size = New-Object System.Drawing.Size(475, 100)
$resultsTextBox.Multiline = $true
$resultsTextBox.ScrollBars = "Vertical"
$resultsTextBox.ReadOnly = $true
$resultsTextBox.Font = New-Object System.Drawing.Font("Consolas", 9)
$resultsGroup.Controls.Add($resultsTextBox)

# Footer (KCCS branding)
$footerLabel = New-Object System.Windows.Forms.Label
$footerLabel.Text = [char]0x25A0 + "  (c) 2026 KCCS  -  kccsonline.com"
$footerLabel.Location = New-Object System.Drawing.Point(20, 472)
$footerLabel.Size = New-Object System.Drawing.Size(495, 20)
$footerLabel.ForeColor = [System.Drawing.Color]::Gray
$footerLabel.TextAlign = "MiddleCenter"
$form.Controls.Add($footerLabel)

# Load saved config (save_location is NOT loaded - always use current user's Documents)
$savedConfig = Load-Config
if ($savedConfig) {
    if ($savedConfig.nvr_ip) { $ipTextBox.Text = $savedConfig.nvr_ip }
    if ($savedConfig.username) { $userTextBox.Text = $savedConfig.username }
    if ($savedConfig.backup_path) { $pathTextBox.Text = $savedConfig.backup_path }
    # Don't load save_location - keep it dynamic per user
}

# Helper to log
function Log-Message {
    param($msg)
    $resultsTextBox.AppendText("$msg`r`n")
}

# Helper to update status
function Update-Status {
    param($msg, $color)
    $statusLabel.Text = $msg
    $statusLabel.ForeColor = $color
    $form.Refresh()
}

# Test Connection
$testBtn.Add_Click({
    $resultsTextBox.Clear()

    if (-not $ipTextBox.Text -or -not $userTextBox.Text -or -not $passTextBox.Text) {
        [System.Windows.Forms.MessageBox]::Show("Please fill in all connection fields.", "Error", "OK", "Error")
        return
    }

    if (-not $pscpPath) {
        [System.Windows.Forms.MessageBox]::Show(
            "PuTTY tools (plink/pscp) not found in PATH.`n`nPlease install PuTTY from:`nhttps://www.putty.org/`n`nMake sure to add it to your PATH.",
            "Missing Dependency", "OK", "Warning")
        return
    }

    Update-Status "Testing connection..." ([System.Drawing.Color]::Blue)
    $testBtn.Enabled = $false
    $backupBtn.Enabled = $false

    try {
        Log-Message "Connecting to $($ipTextBox.Text)..."

        # Test SSH connection and list backup files - check multiple common paths
        $backupPaths = @(
            $pathTextBox.Text,
            "/srv/unifi-protect/backups",
            "/etc/unifi-protect/backups",
            "/data/unifi-core/backups",
            "/data/unifi-protect/backups"
        ) | Select-Object -Unique

        $foundPath = $null
        $zipFiles = @()

        foreach ($testPath in $backupPaths) {
            Log-Message "Checking $testPath..."
            $cmd = "ls -1 '$testPath'/*.zip 2>/dev/null | tail -10"
            $result = echo y | plink -batch -ssh -l $userTextBox.Text -pw $passTextBox.Text $ipTextBox.Text $cmd 2>&1

            $files = $result | Where-Object { $_ -match '\.zip$' -and $_ -notmatch 'keyboard-interactive|plink' }
            if ($files) {
                $foundPath = $testPath
                $zipFiles = $files
                Log-Message "Found backups in: $testPath"
                break
            }
        }

        if ($zipFiles.Count -gt 0) {
            $count = ($zipFiles | Measure-Object).Count
            Log-Message ""
            Log-Message "Connection successful!"
            Log-Message "Found $count backup file(s)"

            $latest = $zipFiles | Select-Object -Last 1
            Log-Message "Latest: $(Split-Path $latest -Leaf)"

            # Update the path field if we found backups in a different location
            if ($foundPath -ne $pathTextBox.Text) {
                $pathTextBox.Text = $foundPath
                Log-Message ""
                Log-Message "Updated backup path to: $foundPath"
            }

            Update-Status "Connection successful!" ([System.Drawing.Color]::Green)
            [System.Windows.Forms.MessageBox]::Show("Connection successful!`n`nFound $count backup file(s) in:`n$foundPath", "Success", "OK", "Information")
        } else {
            Update-Status "Connected, but no backups found" ([System.Drawing.Color]::Orange)
            Log-Message ""
            Log-Message "No backup files found in any common location."
            $triedList = ($backupPaths | ForEach-Object { "- $_" }) -join "`n"
            [System.Windows.Forms.MessageBox]::Show("Connected, but no backup ZIP files were found.`n`nPaths checked:`n$triedList`n`nMost likely automatic backups are not enabled yet. In the UniFi Protect web UI go to:`n  Settings -> System -> Backups`nenable Automatic Backups, then wait for the nightly run (~midnight). If your console stores backups elsewhere, enter that path above and test again.", "No backups found", "OK", "Warning")
        }
    } catch {
        Log-Message "ERROR: $_"
        Update-Status "Connection failed" ([System.Drawing.Color]::Red)
        [System.Windows.Forms.MessageBox]::Show("Connection failed:`n`n$_", "Error", "OK", "Error")
    } finally {
        $testBtn.Enabled = $true
        $backupBtn.Enabled = $true
    }
})

# Backup
$backupBtn.Add_Click({
    $resultsTextBox.Clear()

    if (-not $ipTextBox.Text -or -not $userTextBox.Text -or -not $passTextBox.Text) {
        [System.Windows.Forms.MessageBox]::Show("Please fill in all connection fields.", "Error", "OK", "Error")
        return
    }

    if (-not $pscpPath) {
        [System.Windows.Forms.MessageBox]::Show(
            "PuTTY tools (plink/pscp) not found in PATH.`n`nPlease install PuTTY from:`nhttps://www.putty.org/`n`nMake sure to add it to your PATH.",
            "Missing Dependency", "OK", "Warning")
        return
    }

    # Save config
    Save-Config $ipTextBox.Text $userTextBox.Text $pathTextBox.Text $saveTextBox.Text

    Update-Status "Starting backup..." ([System.Drawing.Color]::Blue)
    $testBtn.Enabled = $false
    $backupBtn.Enabled = $false

    try {
        Log-Message "Connecting to $($ipTextBox.Text)..."

        # Find latest backup - check multiple common paths
        $backupPaths = @(
            $pathTextBox.Text,
            "/srv/unifi-protect/backups",
            "/etc/unifi-protect/backups",
            "/data/unifi-core/backups",
            "/data/unifi-protect/backups"
        ) | Select-Object -Unique

        $latestBackup = $null
        foreach ($testPath in $backupPaths) {
            Log-Message "Checking $testPath..."
            $cmd = "ls -t '$testPath'/*.zip 2>/dev/null | head -1"
            $result = echo y | plink -batch -ssh -l $userTextBox.Text -pw $passTextBox.Text $ipTextBox.Text $cmd 2>&1

            # Filter out plink messages and get just the zip path
            $zipPath = $result | Where-Object { $_ -match '\.zip$' -and $_ -notmatch 'keyboard-interactive|plink' } | Select-Object -First 1

            if ($zipPath) {
                $latestBackup = $zipPath.Trim()
                $pathTextBox.Text = $testPath
                Log-Message "Found backups in: $testPath"
                break
            }
        }

        if (-not $latestBackup) {
            throw "No backup files found on server in any common location"
        }

        # Clean the path - remove any whitespace or control characters
        $latestBackup = ($latestBackup -replace '[\r\n]', '').Trim()

        Log-Message "Latest: $(Split-Path $latestBackup -Leaf)"

        Update-Status "Downloading backup file..." ([System.Drawing.Color]::Blue)
        Log-Message "Downloading backup file..."

        # Download to temp
        $tempZip = Join-Path $env:TEMP "unifi_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').zip"

        # Build the remote path properly
        $remotePath = "$($userTextBox.Text)@$($ipTextBox.Text):$latestBackup"
        Log-Message "Remote: $remotePath"

        $pscpResult = echo y | pscp -batch -pw $passTextBox.Text $remotePath $tempZip 2>&1

        # Check if file was downloaded (pscp exit codes can be unreliable)
        if (-not (Test-Path $tempZip) -or (Get-Item $tempZip).Length -eq 0) {
            throw "Download failed: $pscpResult"
        }

        Log-Message "Download complete"
        Update-Status "Extracting recovery codes..." ([System.Drawing.Color]::Blue)
        Log-Message "Extracting recovery codes..."

        # Extract codes
        $devices = Extract-RecoveryCodes $tempZip

        # Clean up temp
        Remove-Item $tempZip -Force -ErrorAction SilentlyContinue

        # Count devices generically across every known device type
        $total = 0
        $breakdownLines = @()
        Log-Message ""
        Log-Message "Devices found:"
        foreach ($t in $script:DeviceTypes) {
            $c = $devices[$t].Count
            $total += $c
            if ($c -gt 0) {
                $label = $t.Substring(0,1).ToUpper() + $t.Substring(1)
                Log-Message "  ${label}: $c"
                $breakdownLines += "- ${label}: $c"
            }
        }
        Log-Message "  Total: $total"

        # Get NVR hostname and MAC for filename
        Log-Message ""
        Log-Message "Getting NVR info..."
        $nvrName = "UniFi"
        $nvrMAC = ""
        try {
            $hostCmd = "hostname"
            $hostResult = echo y | plink -batch -ssh -l $userTextBox.Text -pw $passTextBox.Text $ipTextBox.Text $hostCmd 2>&1
            $hostName = $hostResult | Where-Object { $_ -notmatch 'keyboard-interactive|plink' -and $_.Trim() } | Select-Object -First 1
            if ($hostName) {
                $nvrName = ($hostName -replace '[\r\n]', '').Trim() -replace '[^\w\-]', ''
            }

            # Try to get MAC address
            $macCmd = "cat /sys/class/net/eth0/address 2>/dev/null || ip link show eth0 2>/dev/null | grep ether | awk '{print \`$2}'"
            $macResult = echo y | plink -batch -ssh -l $userTextBox.Text -pw $passTextBox.Text $ipTextBox.Text $macCmd 2>&1
            $macAddr = $macResult | Where-Object { $_ -match '[0-9a-fA-F:]{17}' } | Select-Object -First 1
            if ($macAddr) {
                $nvrMAC = ($macAddr -replace '[\r\n:]', '').Trim().ToUpper()
                if ($nvrMAC.Length -ge 4) {
                    $nvrMAC = $nvrMAC.Substring($nvrMAC.Length - 4)
                }
            }
        } catch {
            # Ignore errors getting NVR info, use defaults
        }

        Log-Message "NVR Name: $nvrName"
        if ($nvrMAC) { Log-Message "NVR MAC (last 4): $nvrMAC" }

        # Save CSV with NVR name and MAC in filename
        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $filenameParts = @("recovery_codes", $nvrName)
        if ($nvrMAC) { $filenameParts += $nvrMAC }
        $filenameParts += $timestamp
        $filename = ($filenameParts -join "_") + ".csv"
        $outputFile = Join-Path $saveTextBox.Text $filename

        Save-ToCSV $devices $outputFile

        Log-Message ""
        Log-Message "Saved to: $outputFile"

        Update-Status "Backup complete! $total devices saved." ([System.Drawing.Color]::Green)

        [System.Windows.Forms.MessageBox]::Show(
            "Successfully backed up recovery codes!`n`nTotal devices: $total`n$($breakdownLines -join "`n")`n`nSaved to:`n$outputFile",
            "Backup Complete", "OK", "Information")

    } catch {
        Log-Message "ERROR: $_"
        Update-Status "Backup failed" ([System.Drawing.Color]::Red)
        [System.Windows.Forms.MessageBox]::Show("Backup failed:`n`n$_", "Error", "OK", "Error")
    } finally {
        $testBtn.Enabled = $true
        $backupBtn.Enabled = $true
    }
})

# Check for PuTTY on startup
if (-not $pscpPath) {
    $form.Add_Shown({
        [System.Windows.Forms.MessageBox]::Show(
            "PuTTY tools (plink/pscp) are required but not found.`n`nPlease install PuTTY from:`nhttps://www.putty.org/`n`nDuring installation, make sure the tools are added to PATH,`nor manually add the PuTTY folder to your system PATH.",
            "Missing Dependency", "OK", "Warning")
    })
}

# Show form
[void]$form.ShowDialog()
