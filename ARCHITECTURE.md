# Architecture

## What it is

A small toolkit that backs up **UniFi Protect device recovery codes** (the
per-device adoption secret stored in the `password` field of each device in a
Protect backup ZIP) to a CSV, so a device can be re-adopted after a factory
reset or controller migration.

There is no server component, no database and no network listener. Everything
runs as a short-lived desktop app or script. The only network traffic is one
outbound SSH/SFTP session from the user's PC to their own NVR.

## Entry points

| Component | Runs on | Transport | Output |
|-----------|---------|-----------|--------|
| `unifi_protect_backup_gui.py` (Tkinter) | Windows / macOS / Linux PC with Python + paramiko | paramiko SSH + SFTP | `recovery_codes_<ts>.csv` in *Save To* (0600 on POSIX) |
| `UniFi-Protect-Backup.ps1` (WinForms) | Windows PowerShell 5.1+ | PuTTY `plink` (remote `ls`, `hostname`) + `pscp` (download) | `recovery_codes_<host>_<mac4>_<ts>.csv` in *Save To* |
| `extract_recovery_codes.py` (CLI) | On the NVR itself (stdlib only) | local file | text / JSON on stdout, or CSV (0600) |
| `backup_recovery_codes.sh` | On the NVR (cron) | local file | dated CSV copies + `recovery_codes_latest.csv` symlink, 30-day retention |
| `download_latest.ps1`, `UPDATE_BACKUP.bat` | Windows | `pscp` | Pulls the CSV the cron job produced. Credentials are placeholders the user edits in. |
| `RUN_BACKUP.bat`, `RUN_BACKUP_GUI.bat` | Windows | — | Launchers for the PowerShell / Python GUIs |

## Data flow

```
UniFi Protect (nightly)                       user's PC
─────────────────────────                     ─────────────────────────────────────
/srv/unifi-protect/backups/                   GUI: host/user/password (+ backup path)
  unifi_protect_backup.vX.Y.Z.<ts>.zip  ◄─SSH─   │
     cameras.json  bridges.json ...              ├─ find_backup_dir(): probe configured
     devices.key (NVR TLS private key)           │    path, then the 4 known locations;
                                                 │    newest = timestamp in name, then mtime
                                        ─SFTP─►  ├─ download to a private temp file
                                                 ├─ extract_devices(): for each DEVICE_FILES
                                                 │    entry read JSON, map via device_record()
                                                 ├─ write_csv() 0600, formula-guarded Name/Model
                                                 └─ temp ZIP deleted in `finally`
```

`device_record()` normalises each device to
`{name, model(type), mac, ip(host), recovery_code(password)}`, using `or`
fallbacks so empty strings become `Unknown` / `N/A`.

## Modules

### `unifi_protect_backup_gui.py`
* Module-level, Tk-free logic (unit-tested): `DEVICE_FILES`,
  `device_record`, `backup_sort_key`, `candidate_paths`, `find_backup_dir`,
  `extract_devices`, `csv_safe`, `write_csv`, `make_ssh_client`,
  `host_key_error_message`.
* `UniFiProtectBackupGUI`: builds the window, validates inputs, snapshots the
  Tk variables on the main thread (`_snapshot_inputs`) and runs
  `_test_connection_thread` / `_backup_thread` on a daemon thread. Worker
  threads only touch the UI through `self._ui(func, *args)` →
  `root.after(0, …)`, with arguments bound eagerly.
* SSH host keys: `~/.ssh/known_hosts` plus an app-local `known_hosts` file
  (trust on first use, persisted). A changed key raises
  `BadHostKeyException` and the connection is refused.
* `config.json` (next to the script): last IP, username, backup path and save
  folder. The password is never written.

### `UniFi-Protect-Backup.ps1`
Same flow implemented with WinForms and PuTTY. Pure helpers
(`Extract-RecoveryCodes`, `Save-ToCSV`, `ConvertTo-CsvField`,
`Test-SafeRemotePath`, `Load-Config`, `Save-Config`) are tested by
`tests/powershell/Test-Functions.ps1`, which loads only the function
definitions from the script's AST (the script opens a window at load time).
Remote commands interpolate the backup path inside single quotes, so paths
are restricted to `[A-Za-z0-9._/- ]`.

### `extract_recovery_codes.py`
Stdlib-only copy of the extraction logic so it can be dropped onto an NVR.
`main(argv)` returns an exit code. **`DEVICE_FILES` / `device_record` /
`backup_sort_key` are intentionally duplicated in the GUI** (each file must
work standalone); `tests/test_gui_logic.py::test_device_tables_match_cli`
fails if they drift.

### `backup_recovery_codes.sh`
Cron wrapper around the CLI: newest ZIP by mtime → CSV → dated copy →
`latest` symlink → prune after `RETENTION_DAYS`. `umask 077`; removes the
previous CSV before extracting so a failure can't be reported as success.

## Adding a new Protect device type
Add it to `DEVICE_FILES` in **both** Python files and to `$script:DeviceTypes`
in the PowerShell GUI (and its test), then update the README list.

## Tests & CI
`pytest` (see `tests/`) fakes paramiko's SSH/SFTP objects and stubs tkinter
when absent, so it needs no NVR, network or display. The shell script is run
for real against a temp directory. CI: `.github/workflows/ci.yml` (ruff,
ShellCheck, PowerShell parse, pytest on Linux with Python 3.9/3.13, pytest +
Windows PowerShell 5.1 checks on Windows).
