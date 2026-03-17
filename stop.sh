#!/usr/bin/env bash
set -e

echo "🛑 Stopping ZeroDay server..."

if [ -f app.pid ]; then
    PID=$(cat app.pid)
    kill $PID || true
    rm app.pid
    echo "✅ Server stopped."
else
    echo "⚠️ No running app found."
fi