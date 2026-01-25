#!/bin/bash

set -e

cd "$(dirname "$0")"

echo "🔍 Supernote App Monitor with OCR Trigger"
echo "=========================================="
echo "This script will:"
echo "1. Launch the Supernote app"
echo "2. Monitor when you close it"
echo "3. Automatically run OCR processing"
echo ""

# Activate virtual environment
source .venv/bin/activate

# Configuration
SUPERNOTE_APP_PATH="/Applications/Supernote Partner.app"
SUPERNOTE_BUNDLE_ID="com.ratta.supernote"
OCR_SCRIPT="./run-native.sh"

# Check if Supernote app exists
if [ ! -d "$SUPERNOTE_APP_PATH" ]; then
    echo "❌ Error: Supernote app not found at $SUPERNOTE_APP_PATH"
    echo "Please install the Supernote app first"
    exit 1
fi

# Check if OCR script exists
if [ ! -f "$OCR_SCRIPT" ]; then
    echo "❌ Error: OCR script not found at $OCR_SCRIPT"
    exit 1
fi

echo "✅ Found Supernote app at $SUPERNOTE_APP_PATH"
echo "✅ Found OCR script at $OCR_SCRIPT"
echo ""

# Function to run OCR processing
run_ocr_processing() {
    echo ""
    echo "🚀 Supernote app closed - Starting OCR processing..."
    echo "================================================"
    echo "Timestamp: $(date)"
    echo ""
    
    # Give a moment for file syncing to complete
    echo "⏳ Waiting 3 seconds for file sync to complete..."
    sleep 3
    
    # Wait for OCR API to be ready (in case restart is still running)
    echo "🔍 Checking OCR API status..."
    for i in {1..30}; do
        if curl -s http://localhost:8100/health > /dev/null 2>&1; then
            echo "✅ OCR API is ready!"
            break
        fi
        if [ $i -eq 30 ]; then
            echo "⚠️  Warning: OCR API not ready after 30s, proceeding anyway..."
        fi
        sleep 1
    done
    
    # Run the OCR script
    if [ -f "$OCR_SCRIPT" ]; then
        echo "📝 Executing: $OCR_SCRIPT"
        bash "$OCR_SCRIPT"
        
        echo ""
        echo "✅ OCR processing completed at $(date)"
        echo "📄 Your searchable files should be ready!"
    else
        echo "❌ Error: OCR script not found - cannot process files"
    fi
    
    echo ""
    echo "👋 Script finished. You can safely close this window."
    exit 0
}

# Function to monitor app status
monitor_app() {
    echo "🔄 Restarting OCR API in parallel..."
    ./restart-ocr-api.sh &
    OCR_API_PID=$!
    
    echo "🚀 Launching Supernote Partner app..."
    echo "💡 Use the app normally. When you close it, OCR will run automatically."
    echo "⏳ Monitoring Supernote app status..."
    echo ""
    
    # Launch the app
    open "$SUPERNOTE_APP_PATH"
    
    # Wait for app to start
    sleep 2
    
    # Monitor loop
    local app_running=true
    while $app_running; do
        # Check if app is still running
        if ! pgrep -f "$SUPERNOTE_BUNDLE_ID" > /dev/null 2>&1; then
            echo "📱 Supernote app detected as closed"
            app_running=false
        else
            # App is still running, wait a bit
            sleep 1
        fi
    done
    
    # App closed, trigger OCR
    run_ocr_processing
}

# Handle Ctrl+C gracefully
trap 'echo ""; echo "🛑 Monitor stopped by user"; exit 0' INT

# Start monitoring
monitor_app
