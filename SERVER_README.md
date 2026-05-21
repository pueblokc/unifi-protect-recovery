# UniFi Protect Device Recovery Codes — Server-Side Guide

This guide documents the **server-side** (on-the-NVR) method for backing up UniFi
Protect device recovery codes. If you just want a point-and-click tool, use the
GUI described in the main [README](README.md) instead — you don't need any of this.

Recovery codes are essential for:

- Re-adopting cameras and sensors after a factory reset
- Recovering from network/controller issues
- Migrating devices to a new controller
- Disaster recovery scenarios

> ⚠️ **All example IPs, MACs, and recovery codes in this document are fake**
> (RFC 5737 test addresses / locally-administered MACs). They are placeholders.

---

## Quick Start (on the NVR)

Run the extraction script to dump all current recovery codes:

```bash
python3 extract_recovery_codes.py
```

Export to CSV:

```bash
python3 extract_recovery_codes.py /path/to/backup.zip csv
```

Or run the automated backup script (extract + dated copy + retention):

```bash
bash backup_recovery_codes.sh
```

---

## File Locations

### UniFi Protect Backups (input)
- **Default path:** `/srv/unifi-protect/backups/`
- **Other common paths:** `/data/unifi-core/backups/`, `/etc/unifi-protect/backups/`
- **Daily auto-backups:** created around midnight (00:00)
- **Format:** `unifi_protect_backup.vX.Y.Z.YYYYMMDDHHMMSS.zip`

### Recovery Code Backups (output)
- **CSV backups:** `/root/unifi_protect_recovery_backups/`
- **Latest symlink:** `recovery_codes_latest.csv`
- **Retention:** 30 days (configurable in `backup_recovery_codes.sh`)

---

## Scripts

### `extract_recovery_codes.py`
Extracts recovery codes from a UniFi Protect backup ZIP. Supports `text`, `json`,
and `csv` output. Uses the latest backup automatically if no file is given.

```bash
python3 extract_recovery_codes.py                          # latest backup, text
python3 extract_recovery_codes.py /path/to/backup.zip      # specific file, text
python3 extract_recovery_codes.py /path/to/backup.zip json # JSON output
python3 extract_recovery_codes.py /path/to/backup.zip csv  # CSV output
```

### `backup_recovery_codes.sh`
Finds the latest backup, extracts codes to CSV, creates a dated copy, maintains a
`recovery_codes_latest.csv` symlink, and prunes backups older than 30 days.

Optional daily cron at 1:00 AM:

```bash
echo "0 1 * * * /root/backup_recovery_codes.sh >> /var/log/recovery_backup.log 2>&1" | crontab -
```

---

## CSV Output Format

```csv
Type,Name,Model,MAC,IP,Recovery Code
Camera,Front Door,UVC G4 Bullet,02005E100001,192.0.2.11,EXAMPLE_CODE_aaaaaaaa
Camera,Driveway,UVC G6 Bullet,02005E100002,192.0.2.12,EXAMPLE_CODE_bbbbbbbb
Bridge,Garage,UFP-UAP-B,02005E100003,192.0.2.13,EXAMPLE_CODE_cccccccc
```

---

## What's Inside a UniFi Protect Backup

Each backup ZIP contains JSON files with device configuration:

| File | Contents |
|------|----------|
| `cameras.json` | Camera configs + recovery codes |
| `bridges.json` | Bridge / sensor configs |
| `lights.json` | Light configs |
| `speakers.json` | Speaker configs |
| `nvr.json` | NVR configuration |
| `users.json` | User configurations |
| `liveviews.json` | Live view layouts |
| `automations.json` | Smart-detection automations |
| `devices.crt` / `devices.key` | Device SSL cert + private key |

The recovery code lives in each device's `password` field.

---

## Downloading Backups to Windows

The recommended path is the **GUI** (see main README) — it does the SSH download
for you. If you prefer the command line, use PuTTY's `pscp`:

```powershell
pscp -l root -pw "YOUR_PASSWORD" YOUR_NVR_IP:/root/unifi_protect_recovery_backups/recovery_codes_latest.csv .
```

---

## Security Notes

**Recovery codes provide full access to adopt your devices. Treat the CSV like a
password file.**

- Store backups in encrypted/secure storage
- Restrict access to root only on the NVR
- Never commit a real CSV to source control (this repo's `.gitignore` blocks `*.csv`)
- Keep an offline copy for disaster recovery

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Script not found | Run with full path, or `cd` to the script directory |
| No backup files found | Confirm UniFi Protect automatic backups are enabled |
| Permission denied | Run as root: `sudo python3 extract_recovery_codes.py` |
| CSV not updating | Debug the backup script: `bash -x backup_recovery_codes.sh` |

---

<sub>■ © 2026 KCCS · [kccsonline.com](https://kccsonline.com) · MIT License</sub>
