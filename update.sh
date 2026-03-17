#!/usr/bin/env bash
set -e

echo "🚀 Starting update..."

cd "$(dirname "$0")"

# --- Backup ---
echo "📦 Creating backup..."
mkdir -p ~/backups
cp -r . ~/backups/zeroday_$(date +%F_%T)

# --- Stop app ---
./stop.sh || true

# --- Clean & Pull ---
echo "⬇️ Pulling latest code..."
git fetch origin
git reset --hard origin/main
git clean -fd

# --- Reinstall deps ---
echo "📦 Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt

# --- Restart ---
echo "🔁 Restarting app..."
chmod +x *.sh

echo "✅ Update complete!"