#!/usr/bin/env bash
# Production rollback script for ZeroDay Server
set -e

cd "$(dirname "$0")"
PROJECT_DIR=$(pwd)

echo "🔙 Rolling back..."

# Find the latest backup directory
BACKUPS_BASE="${HOME}/backups"
if [ ! -d "$BACKUPS_BASE" ]; then
    echo "❌ Backup directory not found!"
    exit 1
fi

LATEST_BACKUP=$(ls -td "${BACKUPS_BASE}/zeroday_"* 2>/dev/null | head -1 || true)

if [ -z "$LATEST_BACKUP" ]; then
    echo "❌ No backup found!"
    exit 1
fi

echo "📦 Found latest backup: $LATEST_BACKUP"
read -p "Are you sure you want to restore this backup? (Wait 5s... auto-proceeding) " -t 5 || echo "Proceeding..."

# --- Stop app ---
echo "🛑 Stopping current application..."
./stop.sh || echo "⚠️ Warning: Failed to stop cleanly. Proceeding..."

# --- Restore ---
echo "📂 Restoring files from backup..."
# rsync to mirror the state of the backup directory onto the current directory
# Deletes files that were added since the backup, absolutely excludes runtime stuff including db
rsync -a --delete --exclude={'venv','logs','data','.git'} "$LATEST_BACKUP/" "$PROJECT_DIR/"

# Dependencies are handled securely by docker-compose up --build in start.sh

echo "🔒 Fixing permissions..."
chmod +x *.sh

# --- Restart ---
echo "🔁 Restarting app..."
./start.sh

echo "✅ Rollback complete!"