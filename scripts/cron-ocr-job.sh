#!/bin/bash
# Cron job for scheduled OCR processing with file locking
# Prevents overlapping runs

LOCK_FILE="/tmp/ocr-processing.lock"
LOG_FILE="/app/data/cron-ocr.log"

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Check if another instance is running
if [ -f "$LOCK_FILE" ]; then
    # Check if the process is actually still running
    if kill -0 $(cat "$LOCK_FILE" 2>/dev/null) 2>/dev/null; then
        log "Previous OCR job still running (PID $(cat "$LOCK_FILE")). Skipping this run."
        exit 0
    else
        log "Stale lock file found. Removing and proceeding."
        rm -f "$LOCK_FILE"
    fi
fi

# Create lock file with our PID
echo $$ > "$LOCK_FILE"

# Cleanup function to remove lock on exit
cleanup() {
    local exit_code=$?
    rm -f "$LOCK_FILE"
    log "OCR job completed with exit code: $exit_code"
    exit $exit_code
}

trap cleanup EXIT INT TERM

# Run the OCR processing with sync control
log "Starting scheduled OCR processing..."
cd /app
/app/run-with-sync-control.sh >> "$LOG_FILE" 2>&1

log "OCR processing finished"
