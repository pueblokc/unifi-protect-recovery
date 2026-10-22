#!/usr/bin/env python3
"""
UniFi Protect Recovery Code Extractor
Extracts device recovery codes from UniFi Protect backup files

Author:  KCCS <info@kccsonline.com> (https://kccsonline.com)
License: MIT
"""

__author__ = "KCCS <info@kccsonline.com>"
__license__ = "MIT"
__copyright__ = "Copyright (c) 2026 KCCS - kccsonline.com"

import csv
import json
import os
import re
import sys
import zipfile
from datetime import datetime

# Where UniFi Protect writes its automatic backups (varies by console/firmware).
CANDIDATE_BACKUP_DIRS = [
    '/srv/unifi-protect/backups',
    '/etc/unifi-protect/backups',
    '/data/unifi-core/backups',
    '/data/unifi-protect/backups',
]
DEFAULT_CSV_FILE = '/root/unifi_protect_recovery_codes.csv'
OUTPUT_FORMATS = ('text', 'json', 'csv')

# Every adoptable UniFi Protect device stores its recovery code in the
# "password" field of its per-type JSON file inside the backup ZIP. Keep this
# list complete — a missing entry silently drops those devices' recovery codes.
DEVICE_FILES = {
    'cameras':  'cameras.json',
    'bridges':  'bridges.json',
    'lights':   'lights.json',
    'speakers': 'speakers.json',
    'aiports':  'aiports.json',
    'sirens':   'sirens.json',
    'viewers':  'viewers.json',
}


def device_record(d):
    """Build a normalized recovery record. `or` (not dict default) so empty
    strings fall back too — e.g. bridges often have an empty `host`."""
    return {
        'name': d.get('name') or 'Unknown',
        'model': d.get('type') or 'Unknown',
        'mac': d.get('mac') or 'N/A',
        'ip': d.get('host') or 'N/A',
        'recovery_code': d.get('password') or 'N/A',
    }


# Backup names are unifi_protect_backup.v<ver>.<YYYYMMDD[HHMMSS]>.zip; the
# version precedes the timestamp, so sort on the timestamp, not the name.
_BACKUP_TS_RE = re.compile(r'(\d{8,14})\.zip$', re.IGNORECASE)


def backup_sort_key(name, mtime=0):
    m = _BACKUP_TS_RE.search(name)
    ts = m.group(1).ljust(14, '0') if m else ''
    return (ts, mtime or 0, name)


def find_latest_backup(dirs=None):
    """Return the newest backup ZIP across the known backup dirs, or None."""
    for backup_dir in (dirs or CANDIDATE_BACKUP_DIRS):
        try:
            names = [f for f in os.listdir(backup_dir) if f.lower().endswith('.zip')]
        except OSError:
            continue
        files = [os.path.join(backup_dir, f) for f in names]
        files = [f for f in files if os.path.isfile(f)]
        if files:
            return max(files, key=lambda f: backup_sort_key(os.path.basename(f),
                                                            os.path.getmtime(f)))
    return None


def _find_member(names, fname):
    """Exact top-level match first, else the first entry with that basename."""
    if fname in names:
        return fname
    for n in names:
        if n.rsplit('/', 1)[-1] == fname:
            return n
    return None


def extract_recovery_codes(backup_file):
    """Extract recovery codes for every device type in a Protect backup ZIP.
    Returns None (after printing the reason) if the backup can't be read."""

    devices = {k: [] for k in DEVICE_FILES}

    try:
        with zipfile.ZipFile(backup_file, 'r') as zip_ref:
            names = zip_ref.namelist()
            for dtype, fname in DEVICE_FILES.items():
                member = _find_member(names, fname)
                if member is None:
                    continue
                data = json.loads(zip_ref.read(member))
                if isinstance(data, dict):
                    data = [data]
                for d in data:
                    if isinstance(d, dict):
                        devices[dtype].append(device_record(d))
    except Exception as e:
        print(f'Error reading backup file: {e}', file=sys.stderr)
        return None

    return devices


def print_recovery_codes(devices, output_format='text'):
    """Print recovery codes in specified format"""

    if output_format == 'json':
        print(json.dumps(devices, indent=2))
        return

    # Text format
    print('=' * 80)
    print('UNIFI PROTECT DEVICE RECOVERY CODES')
    print(f'Extracted: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 80)
    print()

    for device_type, device_list in devices.items():
        if device_list:
            print(f'{device_type.upper()}:')
            print('-' * 80)
            for device in device_list:
                print(f'  Name: {device["name"]}')
                print(f'  Model: {device["model"]}')
                print(f'  MAC: {device["mac"]}')
                print(f'  IP: {device["ip"]}')
                print(f'  Recovery Code: {device["recovery_code"]}')
                print()
            print(f'Total {device_type}: {len(device_list)}')
            print()


def csv_safe(value):
    """Neutralise spreadsheet formula injection in free-text columns.
    Recovery codes/MACs/IPs are never altered."""
    value = str(value)
    if value and value[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + value
    return value


def save_to_csv(devices, output_file):
    """Save recovery codes to CSV file, readable only by its owner (0600)"""
    fd = os.open(output_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Type', 'Name', 'Model', 'MAC', 'IP', 'Recovery Code']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for device_type, device_list in devices.items():
            for device in device_list:
                writer.writerow({
                    'Type': device_type.rstrip('s').title(),
                    'Name': csv_safe(device['name']),
                    'Model': csv_safe(device['model']),
                    'MAC': device['mac'],
                    'IP': device['ip'],
                    'Recovery Code': device['recovery_code']
                })

    print(f'Recovery codes saved to: {output_file}')


USAGE = (
    'usage: extract_recovery_codes.py [BACKUP_ZIP] [text|json|csv] [CSV_OUTPUT]\n'
    '  BACKUP_ZIP  defaults to the newest backup on this NVR\n'
    f'  CSV_OUTPUT  csv format only; defaults to {DEFAULT_CSV_FILE}'
)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ('-h', '--help'):
        print(USAGE)
        return 0

    if not args or args[0] == '':
        backup_file = find_latest_backup()
        if not backup_file:
            print('No backup files found! Checked: ' + ', '.join(CANDIDATE_BACKUP_DIRS),
                  file=sys.stderr)
            return 1
        # Status goes to stderr so `... json > out.json` stays valid JSON
        print(f'Using latest backup: {backup_file}', file=sys.stderr)
    else:
        backup_file = args[0]

    output_format = args[1].lower() if len(args) > 1 else 'text'
    if output_format not in OUTPUT_FORMATS:
        print(f"Unknown output format '{output_format}'.\n{USAGE}", file=sys.stderr)
        return 2

    devices = extract_recovery_codes(backup_file)
    if devices is None:
        return 1

    if output_format == 'csv':
        csv_file = args[2] if len(args) > 2 else DEFAULT_CSV_FILE
        try:
            save_to_csv(devices, csv_file)
        except OSError as e:
            print(f'Could not write {csv_file}: {e}', file=sys.stderr)
            return 1
    else:
        print_recovery_codes(devices, output_format)
    return 0


if __name__ == '__main__':
    sys.exit(main())
