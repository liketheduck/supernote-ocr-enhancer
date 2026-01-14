#!/bin/bash
#
# Restart OCR API to load new endpoints
#

set -e

echo "🔄 Restarting OCR API..."

# Stop the service
launchctl stop com.supernote.ocr-api
echo "✓ Sent stop signal to OCR API"

# Wait for process to actually stop (max 30 seconds)
echo "⏳ Waiting for OCR API to shut down..."
for i in {1..30}; do
    if ! pgrep -f "ocr-api/server.py" > /dev/null 2>&1; then
        echo "✓ OCR API stopped (after ${i}s)"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "⚠️  Warning: OCR API still running after 30s, forcing restart anyway"
    fi
    sleep 1
done

# Small delay to ensure port is released
sleep 1

# Start the service
launchctl start com.supernote.ocr-api
echo "✓ Started OCR API"

# Wait for it to be ready (check health endpoint)
echo "⏳ Waiting for OCR API to be ready..."
for i in {1..60}; do
    if curl -s http://localhost:8100/health > /dev/null 2>&1; then
        echo "✓ OCR API is ready (after ${i}s)"
        break
    fi
    if [ $i -eq 60 ]; then
        echo "❌ OCR API failed to start after 60s"
        exit 1
    fi
    sleep 1
done

# Check health
echo ""
echo "📊 OCR API Status:"
curl -s http://localhost:8100/health | python3 -m json.tool

# Check if /generate endpoint exists
echo ""
echo "🔍 Checking /generate endpoint..."
if curl -s -X POST http://localhost:8100/generate \
    -H "Content-Type: application/json" \
    -d '{"prompt": "test", "max_tokens": 10}' | grep -q "text"; then
    echo "✅ /generate endpoint is working!"
else
    echo "❌ /generate endpoint not found or not working"
    echo "   The OCR API may need more time to load the model"
    echo "   Check logs: tail -f ~/services/ocr-api/logs/server.log"
fi

echo ""
echo "✅ OCR API restart complete!"
