#!/bin/bash

set -e

cd "$(dirname "$0")"

# Load environment variables from .env.local
if [ -f ".env.local" ]; then
    echo "📝 Loading environment from .env.local..."
    set -a
    source .env.local
    set +a
    echo "✅ Environment loaded successfully"
else
    echo "❌ Error: .env.local file not found!"
    echo "Please create .env.local with your configuration"
    exit 1
fi

# Activate venv and run main.py
source .venv/bin/activate

# Display key configuration (without sensitive data)
echo "🔧 Configuration:"
echo "  - Supernote Data Path: ${SUPERNOTE_DATA_PATH:0:50}..."
echo "  - OCR API URL: ${OCR_API_URL}"
echo "  - Storage Mode: ${STORAGE_MODE}"
echo "  - Text Export: ${OCR_TXT_EXPORT_ENABLED} → ${OCR_TXT_EXPORT_PATH}"
echo "  - PDF Export: ${OCR_PDF_EXPORT_ENABLED} → ${OCR_PDF_EXPORT_PATH}"
echo "  - Logseq Export: ${LOGSEQ_EXPORT_ENABLED}"
if [ "$LOGSEQ_EXPORT_ENABLED" = "true" ]; then
    echo "    Pages: ${LOGSEQ_PAGES_PATH:0:50}..."
    echo "    Assets: ${LOGSEQ_ASSETS_PATH:0:50}..."
fi
echo "  - AI Cleanup: ${AI_TEXT_CLEANUP_ENABLED}"
echo "  - Debug Mode: ${PDF_DEBUG_MODE}"
echo ""

python3 app/main.py

