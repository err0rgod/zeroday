#!/usr/bin/env bash
# Production start script for ZeroDay Server
set -e

# Change to the directory containing this script
cd "$(dirname "$0")"
PROJECT_DIR=$(pwd)

echo "🚀 Starting ZeroDay server from $PROJECT_DIR..."

LOG_DIR="${PROJECT_DIR}/logs"
mkdir -p "$LOG_DIR"

if [ -f "$PROJECT_DIR/app.pid" ]; then
    PID=$(cat "$PROJECT_DIR/app.pid")
    if kill -0 "$PID" 2>/dev/null; then
        echo "⚠️ Server is already running with PID $PID. Stop it first."
        exit 1
    else
        echo "🧹 Cleaning up stale PID file..."
        rm "$PROJECT_DIR/app.pid"
    fi
fi

# Activate venv, create if not exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements.txt > "$LOG_DIR/install.log" 2>&1

# Export environment variables cleanly
if [ -f .env ]; then
    set -a
    source .env
    set +a
else
    echo "⚠️ Warning: .env file not found."
fi

# Run the app using uvicorn with async workers for production performance
NUM_WORKERS=4
echo "⚙️  Starting Uvicorn with $NUM_WORKERS workers..."

# Execute unconditionally from the project root and reference the app as a package module
nohup python -m uvicorn zeroday.web.main:app --host 0.0.0.0 --port 8000 --workers $NUM_WORKERS > "$LOG_DIR/app.log" 2>&1 &
APP_PID=$!
echo $APP_PID > "$PROJECT_DIR/app.pid"
# Prevent bash from killing background process on exit
disown $APP_PID

echo "✅ Server started on port 8000 with PID $APP_PID"