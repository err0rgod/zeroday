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

# Backup everything except runtime directories (logs, venv, data db, .git)
# Using rsync to accurately mirror the current working directory safely
rsync -a --exclude={'venv','logs','data','.git'} "$PROJECT_DIR/" "$BACKUP_DIR/"
echo "✅ Backup created at $BACKUP_DIR"

# --- Stop app ---
echo "🛑 Stopping current application..."
./stop.sh || echo "⚠️ Warning: Failed to stop cleanly. Proceeding..."

# --- Clean & Pull ---
echo "⬇️ Pulling latest code..."
git fetch origin
git reset --hard origin/main
git clean -fd

# --- Reinstall deps ---
echo "📦 Installing dependencies..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
if [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
else
    source venv/bin/activate
fi
pip install -r requirements.txt

# --- Setup Permissions ---
echo "🔒 Fixing permissions..."
chmod +x *.sh

# --- Restart ---
echo "🔁 Restarting app..."
./start.sh

echo "✅ Update complete!"