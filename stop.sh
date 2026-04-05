#!/usr/bin/env bash
# Production stop script for ZeroDay Server (Dockerized)
set -e

cd "$(dirname "$0")"

echo "🛑 Stopping ZeroDay containers..."

# Stop and remove containers, networks, and orphans
docker-compose down --remove-orphans

echo "✅ Server stopped."