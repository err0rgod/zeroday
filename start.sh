#!/usr/bin/env bash
# Production start script for ZeroDay Server (Dockerized)
set -e

cd "$(dirname "$0")"
PROJECT_DIR=$(pwd)

echo "🚀 Starting ZeroDay server via Docker from $PROJECT_DIR..."

docker-compose up -d --build web

echo "✅ Server started via Docker."