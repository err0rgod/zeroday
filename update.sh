#!/usr/bin/env bash
# Production update script for ZeroDay Server
set -e

cd "$(dirname "$0")"
PROJECT_DIR=$(pwd)

echo "🚀 Starting zero-downtime-ish update..."

# --- Backup ---
echo "📦 Creating backup..."
BACKUP_DIR="${HOME}/backups/zeroday_$(date +%F_%H-%M-%S)"
mkdir -p "$BACKUP_DIR"
rsync -a --exclude={'venv','logs','data','.git'} "$PROJECT_DIR/" "$BACKUP_DIR/"
echo "✅ Backup created at $BACKUP_DIR"

# --- Stop app ---
echo "🛑 Stopping current application..."
./stop.sh || echo "⚠️ Warning: Failed to stop cleanly. Proceeding..."

# --- Clean & Pull ---
echo "⬇️ Pulling latest code..."
git fetch origin
git reset --hard origin/main
git clean -fd -e data/

# --- Image Pruning ---
echo "📦 Pruning old images to save space..."
docker image prune -f

# --- Setup Permissions ---
echo "🔒 Fixing permissions..."
chmod +x *.sh

# --- Restart ---
echo "🔁 Restarting app with fresh build..."
./start.sh

echo "✅ Update complete!"