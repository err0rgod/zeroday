#!/usr/bin/env bash
# Production stop script for ZeroDay Server
set -e

cd "$(dirname "$0")"
PROJECT_DIR=$(pwd)

echo "🛑 Stopping ZeroDay server..."

if [ ! -f "$PROJECT_DIR/app.pid" ]; then
    echo "⚠️ No app.pid found. Attempting to find uvicorn processes..."
    # Attempt to gracefully stop uvicorn processes running the app if PID is lost
    pkill -f "uvicorn web.main:app" || echo "✅ No running app found."
    exit 0
fi

PID=$(cat "$PROJECT_DIR/app.pid")

if kill -0 "$PID" 2>/dev/null; then
    echo "⏳ Gracefully stopping process $PID..."
    kill -15 "$PID"
    
    # Wait up to 10 seconds for graceful shutdown
    for i in {1..10}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            echo "✅ Server stopped gracefully."
            rm -f "$PROJECT_DIR/app.pid"
            exit 0
        fi
        sleep 1
    done
    
    # Force kill if still running
    if kill -0 "$PID" 2>/dev/null; then
        echo "⚠️ Process did not exit gracefully. Force killing..."
        kill -9 "$PID"
        echo "✅ Server force stopped."
    fi
else
    echo "🧹 Process $PID is not running. Cleaning up stale PID file."
fi

rm -f "$PROJECT_DIR/app.pid"