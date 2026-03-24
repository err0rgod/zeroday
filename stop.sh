#!/usr/bin/env bash
# Production stop script for ZeroDay Server (Dockerized)
set -e

cd "$(dirname "$0")"
PROJECT_DIR=$(pwd)

echo "🛑 Stopping ZeroDay server via Docker..."

docker-compose stop web

echo "✅ Server gracefully stopped."