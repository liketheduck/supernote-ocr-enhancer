#!/bin/bash
# Cron job for scheduled OCR processing (runs INSIDE container)
# Prevents overlapping runs with file locking
#
# ARCHITECTURE NOTE: This script does NOT stop/start the sync server.
# Database updates (MariaDB) are safe to perform while the sync server runs:
# - MariaDB handles concurrent access via row-level locking
# - Our UPDATE statements are atomic single-row operations
# - The sync protocol is stateless request-response (no long transactions)
#
# This allows OCR to run frequently (every 10 minutes) without service interruption.

LOCK_FILE="/tmp/ocr-processing.lock"
LOG_FILE="/app/data/cron-ocr.log"

# Function to log with timestamp
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

# Cleanup function
cleanup() {
    local exit_code=$?
    rm -f "$LOCK_FILE"
    log "OCR job completed with exit code: $exit_code"
    exit $exit_code
}

trap cleanup EXIT INT TERM

log "Starting scheduled OCR processing..."

# Run the OCR processing directly (we're already inside the container)
# The Python code handles:
# - Graceful skip of already-processed files (via hash comparison)
# - Sync database updates via PersonalCloudSyncHandler (if configured)
log "Running OCR processing..."
cd /app
python main.py >> "$LOG_FILE" 2>&1
OCR_EXIT=$?

if [ $OCR_EXIT -ne 0 ]; then
    log "ERROR: OCR processing failed with exit code $OCR_EXIT"
else
    log "OCR processing completed successfully"
fi

exit $OCR_EXIT
