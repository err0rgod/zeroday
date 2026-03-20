#!/usr/bin/env bash
# Script to manually trigger the ZeroDay AI Pipeline and Mailer

# Move to the root project directory automatically
cd "$(dirname "$0")"

# Activate the local virtual environment across platforms
if [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
elif [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "⚠️ Warning: No virtual environment found. Proceeding with system python..."
fi

# Run the spider and AI generation pipeline
echo "🚀 Starting ZeroDay Scraper & AI Pipeline..."
python content_gen/v2.py
echo "✅ Pipeline execution finished."
