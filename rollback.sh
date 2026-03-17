#!/usr/bin/env bash
set -e

echo "🔙 Rolling back..."

cd ~

LATEST_BACKUP=$(ls -td backups/zeroday_* | head -1)

if [ -z "$LATEST_BACKUP" ]; then
    echo "❌ No backup found!"
    exit 1
fi

echo "Restoring from $LATEST_BACKUP"

rm -rf zeroday
cp -r "$LATEST_BACKUP" zeroday

cd zeroday
./start.sh

echo "✅ Rollback complete!"