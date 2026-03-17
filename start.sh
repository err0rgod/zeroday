#!/usr/bin/env bash
set -e

echo "🚀 Starting ZeroDay server..."

cd "$(dirname "$0")"

# Activate venv
source venv/bin/activate

# Load env
export $(grep -v '^#' .env | xargs)

# Start app (no reload in production)
nohup python -m uvicorn web.main:app --host 0.0.0.0 --port 8000 > app.log 2>&1 &

echo $! > app.pid

echo "✅ Server started on port 8000"