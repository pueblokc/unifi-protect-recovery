#!/bin/bash
#
# UniFi Protect Recovery Code Backup Script
# Automatically extracts and saves recovery codes from latest backup
#
# Author:  KCCS <info@kccsonline.com> (https://kccsonline.com)
# License: MIT
# Copyright (c) 2026 KCCS - kccsonline.com
#

set -u

# Recovery codes are secrets: everything this script creates is owner-only.
umask 077

BACKUP_DIR="${BACKUP_DIR:-/root/unifi_protect_recovery_backups}"
PROTECT_BACKUP_DIR="${PROTECT_BACKUP_DIR:-/srv/unifi-protect/backups}"
CSV_FILE="${CSV_FILE:-/root/unifi_protect_recovery_codes.csv}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
DATE=$(date +%Y%m%d_%H%M%S)

# Use the extractor that sits next to this script, else the historical /root copy.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTRACTOR="$SCRIPT_DIR/extract_recovery_codes.py"
[ -f "$EXTRACTOR" ] || EXTRACTOR="/root/extract_recovery_codes.py"

# Newest backup by modification time
# shellcheck disable=SC2012  # Protect backup names never contain whitespace
LATEST_BACKUP=$(ls -t "$PROTECT_BACKUP_DIR"/unifi_protect_backup.*.zip 2>/dev/null | head -1)

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

if [ -z "$LATEST_BACKUP" ]; then
    echo "Error: No UniFi Protect backup files found in $PROTECT_BACKUP_DIR!"
    exit 1
fi

echo "Processing backup: $LATEST_BACKUP"

# Remove the previous run's CSV first so a failed extraction can never be
# copied forward (and reported as success) as if it were fresh data.
rm -f "$CSV_FILE"

# Extract recovery codes to CSV
if ! python3 "$EXTRACTOR" "$LATEST_BACKUP" csv "$CSV_FILE"; then
    echo "Error: Failed to extract recovery codes"
    exit 1
fi

# Copy CSV to dated backup
if [ -f "$CSV_FILE" ]; then
    DATED="$BACKUP_DIR/recovery_codes_$DATE.csv"
    cp "$CSV_FILE" "$DATED"
    echo "Recovery codes backed up to: $DATED"

    # Also create a 'latest' symlink
    ln -sf "$DATED" "$BACKUP_DIR/recovery_codes_latest.csv"

    # Keep only last N days of recovery code backups
    find "$BACKUP_DIR" -name "recovery_codes_*.csv" -type f -mtime +"$RETENTION_DAYS" -delete

    echo "Backup completed successfully!"
    echo "Total devices: $(tail -n +2 "$CSV_FILE" | wc -l)"
else
    echo "Error: Failed to create CSV file"
    exit 1
fi
