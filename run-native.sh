#!/bin/bash

set -e

cd "$(dirname "$0")"


# Activate venv and run main.py
source .venv/bin/activate

# Asegurar que las variables clave se pasan
export SUPERNOTE_DATA_PATH="/path/to/Library/Containers/com.ratta.supernote/Data/Library/Application Support/com.ratta.supernote/YOUR_USER_ID/Supernote"
export OCR_API_URL="http://localhost:8100"
# Mac app database is encrypted - can't update it directly
# Using "none" mode for testing (files will be processed but sync DB won't be updated)
export STORAGE_MODE="none"
# export MACAPP_DATABASE_PATH="/path/to/Library/Containers/com.ratta.supernote/Data/Library/Application Support/com.ratta.supernote/YOUR_USER_ID/en_supernote.db"
export OCR_TXT_EXPORT_ENABLED="true"
export OCR_TXT_EXPORT_PATH="/path/to/supernote-txt"
# PDF export: generate searchable PDFs with embedded OCR
export OCR_PDF_EXPORT_ENABLED="true"
export OCR_PDF_EXPORT_PATH="/path/to/supernote-pdf"

# Enable Logseq export (default: false)
export LOGSEQ_EXPORT_ENABLED=true
#
# Path to Logseq pages directory. Markdown files will be created here,
# preserving your Supernote folder structure under a 'supernote' namespace.
#
# Example: If your Logseq graph is at ~/Documents/logseq
# Set: LOGSEQ_PAGES_PATH=~/Documents/logseq/pages/supernote
#
export LOGSEQ_PAGES_PATH='/path/to/Library/Mobile Documents/iCloud~com~logseq~logseq/Documents/MainGraph/pages/SuperNote'
#
# Path to Logseq assets directory. PDFs will be copied here for linking.
# This should be your Logseq graph's assets folder.
#
# Example: LOGSEQ_ASSETS_PATH=~/Documents/logseq/assets
#
export LOGSEQ_ASSETS_PATH='/path/to/Library/Mobile Documents/iCloud~com~logseq~logseq/Documents/MainGraph/assets'
#
#
# Force reprocessing of all files (reset database)
export RESET_DATABASE="false"
# Disable backups to save disk space
export CREATE_BACKUPS="true"

# 2. Configurar en .env.local
export AI_TEXT_CLEANUP_ENABLED=true

# PDF Debug Mode: Visualize bounding boxes (set to true for debugging)
# Set to true to see red rectangles and blue text for debugging coordinates
export PDF_DEBUG_MODE=false

python3 app/main.py

