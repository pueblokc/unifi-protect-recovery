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

import json
import sys
import zipfile
import os
from datetime import datetime

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


def extract_recovery_codes(backup_file):
    """Extract recovery codes for every device type in a Protect backup ZIP"""

    devices = {k: [] for k in DEVICE_FILES}

    try:
        with zipfile.ZipFile(backup_file, 'r') as zip_ref:
            names = zip_ref.namelist()
            for dtype, fname in DEVICE_FILES.items():
                if fname not in names:
                    continue
                for d in json.loads(zip_ref.read(fname)):
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

def save_to_csv(devices, output_file):
    """Save recovery codes to CSV file"""
    import csv
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Type', 'Name', 'Model', 'MAC', 'IP', 'Recovery Code']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for device_type, device_list in devices.items():
            for device in device_list:
                writer.writerow({
                    'Type': device_type.rstrip('s').title(),
                    'Name': device['name'],
                    'Model': device['model'],
                    'MAC': device['mac'],
                    'IP': device['ip'],
                    'Recovery Code': device['recovery_code']
                })
    
    print(f'Recovery codes saved to: {output_file}')

if __name__ == '__main__':
    if len(sys.argv) < 2:
        # Use latest backup
        backup_dir = '/srv/unifi-protect/backups'
        backups = sorted([f for f in os.listdir(backup_dir) if f.endswith('.zip')])
        if not backups:
            print('No backup files found!', file=sys.stderr)
            sys.exit(1)
        backup_file = os.path.join(backup_dir, backups[-1])
        print(f'Using latest backup: {backups[-1]}')
        print()
    else:
        backup_file = sys.argv[1]
    
    output_format = sys.argv[2] if len(sys.argv) > 2 else 'text'
    
    devices = extract_recovery_codes(backup_file)
    if devices:
        if output_format == 'csv':
            csv_file = '/root/unifi_protect_recovery_codes.csv'
            save_to_csv(devices, csv_file)
        else:
            print_recovery_codes(devices, output_format)
