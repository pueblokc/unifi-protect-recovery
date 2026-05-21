#!/bin/bash
#
# UniFi Protect Recovery Code Backup Script
# Automatically extracts and saves recovery codes from latest backup
#
# Author:  KCCS <info@kccsonline.com> (https://kccsonline.com)
# License: MIT
# Copyright (c) 2026 KCCS - kccsonline.com
#

BACKUP_DIR="/root/unifi_protect_recovery_backups"
DATE=$(date +%Y%m%d_%H%M%S)
LATEST_BACKUP=$(ls -t /srv/unifi-protect/backups/unifi_protect_backup.*.zip 2>/dev/null | head -1)

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

if [ -z "$LATEST_BACKUP" ]; then
    echo "Error: No UniFi Protect backup files found!"
    exit 1
fi

echo "Processing backup: $LATEST_BACKUP"

# Extract recovery codes to CSV
python3 /root/extract_recovery_codes.py "$LATEST_BACKUP" csv

# Copy CSV to dated backup
if [ -f /root/unifi_protect_recovery_codes.csv ]; then
    cp /root/unifi_protect_recovery_codes.csv "$BACKUP_DIR/recovery_codes_$DATE.csv"
    echo "Recovery codes backed up to: $BACKUP_DIR/recovery_codes_$DATE.csv"
    
    # Also create a 'latest' symlink
    ln -sf "$BACKUP_DIR/recovery_codes_$DATE.csv" "$BACKUP_DIR/recovery_codes_latest.csv"
    
    # Keep only last 30 days of recovery code backups
    find "$BACKUP_DIR" -name "recovery_codes_*.csv" -mtime +30 -delete
    
    echo "Backup completed successfully!"
    echo "Total devices: $(tail -n +2 /root/unifi_protect_recovery_codes.csv | wc -l)"
else
    echo "Error: Failed to create CSV file"
    exit 1
fi
