#!/bin/bash

set -e

cd "$(dirname "$0")"

echo "🚀 Supernote Quick Launcher + OCR"
echo "=================================="
echo "Launch Supernote app and run OCR when you close it"
echo ""

# Activate virtual environment
source .venv/bin/activate


# Restart OCR API
echo "📱 Restarting OCR API..."
./restart-ocr-api.sh&

# Launch app and run OCR on exit
echo "📱 Launching Supernote app..."
echo "💡 When you close the app, OCR will run automatically"
echo ""

open "/Applications/Supernote Partner.app"

# Wait for app to close
echo "⏳ Waiting for Supernote app to close..."
while pgrep -f "com.ratta.supernote" > /dev/null; do
    sleep 1
done

echo "📱 App closed! Starting OCR..."
echo ""

# Wait for sync to complete
sleep 3

# Run OCR
./run-native.sh
