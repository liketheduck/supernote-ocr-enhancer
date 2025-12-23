#!/bin/bash
#
# TEMPLATE: Mac App OCR Cron Job (runs on HOST, not in Docker)
#
# This is a TEMPLATE for users who want to schedule automatic OCR processing
# for the Supernote Mac app ("Supernote Partner"). It runs on your Mac (not in Docker).
#
# IMPORTANT: This script MUST quit the Supernote Partner app before processing
# to prevent sync conflicts. The app will be restarted after OCR completes.
#
# SETUP INSTRUCTIONS:
# 1. Copy this script to your preferred location:
#    cp scripts/cron-macapp-template.sh ~/scripts/supernote-ocr-cron.sh
#
# 2. Edit the script and set OCR_ENHANCER_DIR below
#
# 3. Make it executable:
#    chmod +x ~/scripts/supernote-ocr-cron.sh
#
# 4. Add to your crontab (runs daily at midnight):
#    crontab -e
#    0 0 * * * /Users/YOUR_USERNAME/scripts/supernote-ocr-cron.sh >> /tmp/supernote-ocr.log 2>&1
#
# WHAT THIS SCRIPT DOES:
# 1. Quits Supernote Partner app (REQUIRED to prevent sync conflicts)
# 2. Waits for app to fully close
# 3. Runs OCR enhancement on all .note files
# 4. Updates Mac app database to trigger upload (not download)
# 5. Restarts Supernote Partner app
# 6. App syncs enhanced files to Supernote cloud
#
# NOTE: This is SEPARATE from Personal Cloud cron which runs inside Docker.
#

set -e

# =============================================================================
# CONFIGURATION - EDIT THIS FOR YOUR SETUP
# =============================================================================

# Path to your supernote-ocr-enhancer project directory
OCR_ENHANCER_DIR="/path/to/supernote-ocr-enhancer"

# =============================================================================
# END CONFIGURATION
# =============================================================================

LOG_FILE="$OCR_ENHANCER_DIR/data/cron-macapp.log"
LOCK_FILE="/tmp/macapp-ocr-processing.lock"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Check if another instance is running
if [ -f "$LOCK_FILE" ]; then
    if kill -0 $(cat "$LOCK_FILE" 2>/dev/null) 2>/dev/null; then
        log "Previous OCR job still running (PID $(cat "$LOCK_FILE")). Skipping."
        exit 0
    else
        log "Stale lock file found. Removing."
        rm -f "$LOCK_FILE"
    fi
fi

# Create lock file
echo $$ > "$LOCK_FILE"

cleanup() {
    local exit_code=$?
    rm -f "$LOCK_FILE"
    log "Mac App OCR job completed with exit code: $exit_code"
    exit $exit_code
}

trap cleanup EXIT INT TERM

log "=========================================="
log "Starting scheduled Mac App OCR processing"
log "=========================================="

# Validate configuration
if [ ! -d "$OCR_ENHANCER_DIR" ]; then
    log "ERROR: OCR_ENHANCER_DIR not found: $OCR_ENHANCER_DIR"
    log "Please edit this script and set the correct path."
    exit 1
fi

cd "$OCR_ENHANCER_DIR"

# =============================================================================
# STEP 1: QUIT SUPERNOTE PARTNER APP (REQUIRED)
# =============================================================================
# The app MUST be quit to prevent sync conflicts. If the app is running during
# OCR processing, it may download the old server version and overwrite our changes.

APP_WAS_RUNNING=false

if pgrep -f "Supernote Partner" >/dev/null 2>&1; then
    APP_WAS_RUNNING=true
    log "Quitting Supernote Partner app..."

    # Graceful quit via AppleScript
    osascript -e 'tell application "Supernote Partner" to quit' 2>/dev/null || true

    # Wait for app to fully close (up to 30 seconds)
    for i in {1..30}; do
        if ! pgrep -f "Supernote Partner" >/dev/null 2>&1; then
            log "Supernote Partner quit successfully"
            break
        fi
        sleep 1
    done

    # Force kill if still running
    if pgrep -f "Supernote Partner" >/dev/null 2>&1; then
        log "WARNING: App didn't quit gracefully, force killing..."
        pkill -f "Supernote Partner" 2>/dev/null || true
        sleep 2
    fi
else
    log "Supernote Partner is not running"
fi

# =============================================================================
# STEP 2: RUN OCR ENHANCEMENT
# =============================================================================

log "Running OCR enhancement..."

# Run the Mac app OCR script with auto-detection
# This will:
# - Find all .note files in the Mac app folder
# - Run Vision Framework OCR on each page
# - Inject OCR data with FILE_RECOGN_TYPE=0
# - Update Mac app database to trigger upload

./run-with-macapp.sh --auto >> "$LOG_FILE" 2>&1
OCR_EXIT=$?

if [ $OCR_EXIT -ne 0 ]; then
    log "ERROR: OCR processing failed with exit code $OCR_EXIT"
fi

# =============================================================================
# STEP 3: RESTART SUPERNOTE PARTNER APP
# =============================================================================
# Restart the app so it syncs the enhanced files to the cloud

if [ "$APP_WAS_RUNNING" = true ]; then
    log "Restarting Supernote Partner..."
    open -a "Supernote Partner" 2>/dev/null || log "WARNING: Could not restart app"

    # Give the app time to start and begin syncing
    sleep 5

    if pgrep -f "Supernote Partner" >/dev/null 2>&1; then
        log "Supernote Partner restarted - will sync enhanced files"
    else
        log "WARNING: Supernote Partner may not have started"
    fi
else
    log "Supernote Partner was not running before - not restarting"
fi

log "=========================================="
log "Mac App OCR processing complete"
log "=========================================="

exit $OCR_EXIT
