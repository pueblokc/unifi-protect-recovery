# Unit checks for the pure helper functions in UniFi-Protect-Backup.ps1.
# The script builds a WinForms window at load time, so instead of
# dot-sourcing it we parse it and load only its function definitions.
# Runs on Windows PowerShell 5.1 and PowerShell 7 (any OS). Exit 1 on failure.
$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot '..\..\UniFi-Protect-Backup.ps1'
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path $scriptPath), [ref]$null, [ref]$errors)
if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }

$script:DeviceTypes = @('cameras', 'bridges', 'lights', 'speakers', 'aiports', 'sirens', 'viewers')
$ast.FindAll({ $args[0] -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false) |
    ForEach-Object { . ([scriptblock]::Create($_.Extent.Text)) }

$failures = 0
function Check($name, $cond) {
    if ($cond) { Write-Host "ok   $name" } else { Write-Host "FAIL $name"; $script:failures++ }
}

# CSV field quoting
Check 'plain field quoted' ((ConvertTo-CsvField 'abc') -eq '"abc"')
Check 'embedded quotes doubled' ((ConvertTo-CsvField 'a "b" c') -eq '"a ""b"" c"')
Check 'formula guarded in free text' ((ConvertTo-CsvField '=1+1' -FreeText) -eq "`"'=1+1`"")
Check 'codes never altered' ((ConvertTo-CsvField '-abc') -eq '"-abc"')

# Remote path validation (guards the single-quoted ls argument)
Check 'default path ok' (Test-SafeRemotePath '/srv/unifi-protect/backups')
Check 'quote rejected' (-not (Test-SafeRemotePath "/tmp/x'; rm -rf / #"))
Check 'subshell rejected' (-not (Test-SafeRemotePath '/tmp/$(id)'))
Check 'relative rejected' (-not (Test-SafeRemotePath 'backups'))

# Extraction + CSV round trip
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("upr-test-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zipPath = Join-Path $tmp 'backup.zip'
    $zip = [System.IO.Compression.ZipFile]::Open($zipPath, 'Create')
    $files = @{
        'cameras.json' = '[{"name":"Front, \"Door\"","type":"G4","mac":"02005E100001","host":"192.0.2.11","password":"EXAMPLE_a"},{"name":"=cmd","type":"G6","mac":"M2","host":"","password":"EXAMPLE_b"}]'
        'viewers.json' = '[{"name":"Lobby","type":"VP","mac":"M3","host":"192.0.2.15","password":"EXAMPLE_c"}]'
        'nvr.json'     = '{"name":"x"}'
    }
    foreach ($k in $files.Keys) {
        $w = New-Object System.IO.StreamWriter($zip.CreateEntry($k).Open())
        $w.Write($files[$k]); $w.Close()
    }
    $zip.Dispose()

    $devices = Extract-RecoveryCodes $zipPath
    Check 'two cameras' ($devices['cameras'].Count -eq 2)
    Check 'one viewer' ($devices['viewers'].Count -eq 1)
    Check 'empty host -> N/A' ($devices['cameras'][1].ip -eq 'N/A')

    $csvPath = Join-Path $tmp 'out.csv'
    Save-ToCSV $devices $csvPath
    $rows = Import-Csv $csvPath
    Check 'csv row count' (@($rows).Count -eq 3)
    Check 'csv quotes/commas round-trip' ($rows[0].Name -eq 'Front, "Door"')
    Check 'csv formula guarded' ($rows[1].Name -eq "'=cmd")
    Check 'csv code intact' ($rows[2].'Recovery Code' -eq 'EXAMPLE_c')

    $bad = Join-Path $tmp 'bad.zip'
    Set-Content -Path $bad -Value 'not a zip'
    $threw = $false
    try { Extract-RecoveryCodes $bad | Out-Null } catch { $threw = $true }
    Check 'corrupt zip throws' $threw
} finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

if ($failures -gt 0) { Write-Host "$failures failure(s)"; exit 1 }
Write-Host 'All PowerShell checks passed'
exit 0
