#!/usr/bin/env bash
# Production stop script for ZeroDay Server (Dockerized)
set -e

cd "$(dirname "$0")"
PROJECT_DIR=$(pwd)

echo "🛑 Stopping ZeroDay server via Docker and destroying stale containers..."

docker-compose down

echo "✅ Server gracefully stopped and containers removed."