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

def extract_recovery_codes(backup_file):
    """Extract recovery codes from a UniFi Protect backup ZIP file"""
    
    devices = {
        'cameras': [],
        'bridges': [],
        'lights': [],
        'speakers': []
    }
    
    try:
        with zipfile.ZipFile(backup_file, 'r') as zip_ref:
            # Extract cameras
            if 'cameras.json' in zip_ref.namelist():
                cameras_data = json.loads(zip_ref.read('cameras.json'))
                for cam in cameras_data:
                    devices['cameras'].append({
                        'name': cam.get('name', 'Unknown'),
                        'model': cam.get('type', 'Unknown'),
                        'mac': cam.get('mac', 'N/A'),
                        'ip': cam.get('host', 'N/A'),
                        'recovery_code': cam.get('password', 'N/A')
                    })
            
            # Extract bridges
            if 'bridges.json' in zip_ref.namelist():
                bridges_data = json.loads(zip_ref.read('bridges.json'))
                for bridge in bridges_data:
                    devices['bridges'].append({
                        'name': bridge.get('name', 'Unknown'),
                        'model': bridge.get('type', 'Unknown'),
                        'mac': bridge.get('mac', 'N/A'),
                        'ip': bridge.get('host', 'N/A'),
                        'recovery_code': bridge.get('password', 'N/A')
                    })
            
            # Extract lights
            if 'lights.json' in zip_ref.namelist():
                lights_data = json.loads(zip_ref.read('lights.json'))
                for light in lights_data:
                    devices['lights'].append({
                        'name': light.get('name', 'Unknown'),
                        'model': light.get('type', 'Unknown'),
                        'mac': light.get('mac', 'N/A'),
                        'ip': light.get('host', 'N/A'),
                        'recovery_code': light.get('password', 'N/A')
                    })
            
            # Extract speakers
            if 'speakers.json' in zip_ref.namelist():
                speakers_data = json.loads(zip_ref.read('speakers.json'))
                for speaker in speakers_data:
                    devices['speakers'].append({
                        'name': speaker.get('name', 'Unknown'),
                        'model': speaker.get('type', 'Unknown'),
                        'mac': speaker.get('mac', 'N/A'),
                        'ip': speaker.get('host', 'N/A'),
                        'recovery_code': speaker.get('password', 'N/A')
                    })
                    
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
    
    with open(output_file, 'w', newline='') as csvfile:
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
