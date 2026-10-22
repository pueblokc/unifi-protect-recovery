# Cloud Wave 2 — Overnight Quality Pass

Branch: `claude/cloud-wave2-2026-10-22` (based on `main` @ `e6e007b`). No PR opened, nothing merged, deployed or tagged.

## TL;DR

1. **The Python GUI's error dialogs were all broken.** Every `except Exception as e` handler scheduled a `lambda` that used `e`. Python 3 deletes `e` when the `except` block ends, so the callback raised `NameError`. Users saw "Backup failed" with no reason given. Fixed, with a regression test.
2. **Recovery-code secrets leaked onto disk.** If a download or extraction failed, the downloaded backup ZIP stayed in `%TEMP%`. That ZIP holds every recovery code plus the NVR's TLS private key. This happened in both GUIs. On macOS, Linux and the NVR, CSVs were written world-readable (0644). Both are fixed: the temp file is deleted in `finally`, and CSVs are now written 0600.
3. **The server cron script could report stale data as success.** If extraction failed, `backup_recovery_codes.sh` copied the *previous* run's CSV into a new dated file and printed "Backup completed successfully!". Fixed.
4. **The wrong "latest" backup could be picked.** Backup names put the version before the timestamp (`…v6.10.0.<ts>.zip`), and the code sorted by name, so `v6.9` sorted after `v6.10`. The Python GUI and the CLI now sort by the timestamp in the name, then by file mtime.
5. **SSH host keys were never checked.** Paramiko used `AutoAddPolicy` with nothing persisted, so the GUI accepted any host key every time. It now trusts the key on first use and **refuses to connect if the key changes**. Added 38 tests and CI on Linux and Windows. CI is green.

No secrets, real IPs, internal hostnames or personal paths are committed anywhere in the history. I checked all files, the full git log, and both screenshots. They use RFC 5737 IPs and `C:\Users\you`.

## Commits

| Hash | What |
|------|------|
| `d9eecdb` | GUI: fix broken error dialogs, temp-file leak, Tk thread-safety, backup ordering, 0600 CSV, host-key trust-on-first-use (TOFU) |
| `a9eeeed` | CLI + server script: exit codes, newest-backup selection, stale CSV, 0600 output; ruff config |
| `2846982` | PowerShell GUI: valid CSV quoting, temp ZIP cleanup, newest-backup display, remote path guard |
| `6104ee9` | pytest suite + PowerShell helper checks |
| `e1027da` | CI workflow; `paramiko>=3.4.0` |
| `2cb4cca` | ARCHITECTURE.md; README / SERVER_README corrected |
| (this commit) | This report |

## Bugs found and fixed

Line numbers refer to the original code at `e6e007b`.

| # | Where | Symptom | Fix |
|---|-------|---------|-----|
| 1 | `unifi_protect_backup_gui.py:472, 605, 606` | `lambda: …str(e)` ran after `e` had been deleted, causing a `NameError` in a Tk callback. No error dialog or log line was shown for any generic failure (timeout, DNS, no backups, corrupt ZIP). | All worker→UI calls go through `self._ui(func, *args)`, which binds the arguments immediately. |
| 2 | `unifi_protect_backup_gui.py:540-557` | The temp ZIP was only deleted on the success path. On a failed download or extraction it stayed behind with all codes and the TLS key. | `mkstemp` plus `os.unlink` in `finally`. |
| 3 | `unifi_protect_backup_gui.py:398-…, 503-…` | `ssh`/`sftp` were never closed when an exception was raised. | Closed in `finally`. |
| 4 | `unifi_protect_backup_gui.py:390` | `sorted()` by name picked the wrong "latest" backup (the version comes before the timestamp). | `backup_sort_key`: name timestamp (8–14 digits), then mtime, then name. Uses `listdir_attr`. |
| 5 | `unifi_protect_backup_gui.py:402-404, 507-509, 574` | Worker threads read `tk.StringVar`s. Tkinter isn't thread-safe and this can raise `RuntimeError: main thread is not in main loop`. | Inputs are snapshotted on the main thread and passed to the thread. A double-click guard was also added. |
| 6 | `unifi_protect_backup_gui.py:574` | If the Save-To folder didn't exist, the backup failed after the download. | `mkdir(parents=True, exist_ok=True)`. |
| 7 | `unifi_protect_backup_gui.py` (summary) | A backup with 0 devices was reported as "Backup complete!". | Now shows a warning dialog instead. |
| 8 | `extract_recovery_codes.py:119` | With no argument, it crashed with a traceback if `/srv/unifi-protect/backups` was missing, and it used a name sort (same issue as #4). | Probes all 4 known directories and picks the newest by timestamp/mtime. |
| 9 | `extract_recovery_codes.py:132` | Exited 0 on failure, and an unknown format silently fell back to text. | `main()` returns 1 on failure and 2 on a bad format. |
| 10 | `extract_recovery_codes.py:116-118` | "Using latest backup" was printed to stdout, which corrupted `json` output. | Moved to stderr. |
| 11 | `backup_recovery_codes.sh:26-29` | On extraction failure, the old `/root/…csv` was copied forward and reported as success. | Old CSV removed first, Python's exit status checked, `set -u`. |
| 12 | `UniFi-Protect-Backup.ps1:101` | Names containing `"` produced a malformed CSV. | `ConvertTo-CsvField` (RFC 4180 quoting). |
| 13 | `UniFi-Protect-Backup.ps1:465` | Temp ZIP left in `%TEMP%` when extraction threw. | Removed in `finally`. |
| 14 | `UniFi-Protect-Backup.ps1:82` | The ZIP handle leaked when parsing failed. | `Dispose()` in `finally`. |
| 15 | `UniFi-Protect-Backup.ps1:332, 350` | "Test Connection" showed the alphabetically-last ZIP as "Latest". | `ls -t | head` and take the first item. |
| 16 | Both Python files | JSON members were only found at the ZIP root. A non-list JSON or junk entries raised errors. | Falls back to a basename match (same as the PowerShell GUI already did). Tolerates dicts and junk entries. |

## Security findings

### Fixed
- **Recovery codes at rest:** CSVs are written 0600 (Python GUI, CLI, cron script with `umask 077`), and a pre-existing file is tightened too. The cron output directory is `chmod 700`. The temp backup ZIP is always deleted (bugs #2 and #13).
- **SSH host-key verification (Python GUI):** before, any key was accepted on every connection, so a man-in-the-middle could capture the root password. Now `~/.ssh/known_hosts` is loaded, plus an app-local `known_hosts` file (0600, gitignored). The first key is persisted, and a changed key raises `BadHostKeyException` with a clear explanation. **This is a behaviour change** (see Needs Justin).
- **CSV/formula injection:** Name and Model values starting with `= + - @ TAB CR` get a leading `'`. **Recovery codes, MACs and IPs are never altered**, because changing a code would make it useless.
- **Remote shell injection (PowerShell GUI):** the backup path was interpolated into `ls '<path>'/*.zip` on the NVR. Paths are now limited to `^/[A-Za-z0-9._/\- ]*$`. Practical risk was low, because it was the user's own input to their own root shell.
- **Dependency:** `paramiko>=2.7.0` → `>=3.4.0` (CVE-2022-24302 and the Terrapin fix CVE-2023-48795).
- TLS verification: not applicable. There is no HTTPS client in this repo.
- There is no HTTP, IPC or Electron surface, so the CSRF, SSRF, XSS and SQL checks don't apply.

### Not fixed (needs a decision)
- **The PowerShell GUI passes the password with `plink`/`pscp -pw`** (orig `UniFi-Protect-Backup.ps1:333, 418, 450, 490`). It is visible in the process list to other users on the same PC while the command runs. The fix would be `-pwfile` (PuTTY ≥ 0.77) or Posh-SSH. That needs testing on real Windows and PuTTY versions, so I only documented it in the README.
- **`echo y | plink -batch …`:** with `-batch`, plink refuses unknown host keys rather than reading the `y`. So either first connections fail until the key is cached in PuTTY, or PuTTY's cache already did the trust-on-first-use. The PowerShell GUI never shows the fingerprint. This needs a real-hardware check (below) before I'd change it.
- `UPDATE_BACKUP.bat` and `download_latest.ps1` tell users to hard-code their root password into the file. That is a doc/design choice. They are placeholders only, and no real value is committed.
- `RUN_BACKUP_GUI.bat` skips installing paramiko if *any* version is present, so an old, vulnerable paramiko would keep running. Low risk.

## Tests

```bash
pip install -r requirements-dev.txt
ruff check .
pytest -v
```

- **38 tests:** 15 CLI, 19 GUI logic, 3 shell script, 1 PowerShell wrapper. The PowerShell wrapper runs `tests/powershell/Test-Functions.ps1`, which has 16 checks.
- Locally (Linux, Python 3.13, pwsh 7.4): **38 passed**. Without pwsh: 37 passed, 1 skipped.
- **CI** (`.github/workflows/ci.yml`): ruff, ShellCheck, a PowerShell parse check, pytest on Ubuntu with Python 3.9 and 3.13, and on Windows pytest plus the **Windows PowerShell 5.1** checks. Run 1 is green on all 3 jobs. No secrets are needed and there are no deploy steps.
- Tkinter is stubbed when it's missing, and SSH/SFTP are faked. No NVR, network or display is needed.

## Needs Justin

1. **Real-hardware smoke test (Python GUI):** run Test Connection and Backup against a real NVR. Check that a `known_hosts` file appears next to the script and that a second run still connects. Test the mismatch message by editing a byte of the key in that file.
2. **Real-hardware smoke test (PowerShell GUI, real Windows desktop):** run a backup against a host that is *not* yet cached in PuTTY. Does it fail on the host key? (See the `echo y | plink -batch` note above.) Also open the CSV in Excel and confirm names with quotes or commas look right.
3. **Decision: host-key TOFU in the Python GUI.** Customers who replace an NVR at the same IP will now see a "Host key mismatch" error until they delete the line. I think that's the right default for a tool that sends a root password. Revert `make_ssh_client` if you disagree.
4. **Decision: the PowerShell GUI's `-pw` on the command line.** Move to `-pwfile` (needs PuTTY ≥ 0.77) or Posh-SSH?
5. **Existing CSVs on customer NVRs** in `/root/unifi_protect_recovery_backups/` were created 0644. The script now tightens new ones and the directory (700), which protects them going forward. Old files only become private through the directory permission.
6. **Credentials to rotate:** none. No secrets were found in the repo or its history.
7. Before release: re-take the screenshots if you want them to match exactly. The "Ready" screenshot shows placeholder text in the IP and Save-To fields that the Tk app doesn't actually render.

## Unsure about

- **Backup filename format.** SERVER_README says `…YYYYMMDDHHMMSS.zip`, but the screenshot shows `…20260521.zip`. The sort key handles 8–14 digits and falls back to mtime, so both work. I haven't confirmed the real format.
- **Nested JSON in the ZIP.** I don't know whether any firmware puts `cameras.json` in a subfolder. The basename fallback is harmless if none do.
- **Formula guard on Name/Model.** It shows a leading `'` for device names that really start with `-`, `+`, `=` or `@`. That's cosmetic, but it is visible.
- **CLI status line.** `extract_recovery_codes.py` now prints "Using latest backup" to stderr instead of stdout. Any script that grepped stdout for it would need updating. That seems unlikely.
