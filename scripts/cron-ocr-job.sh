#!/bin/bash
# Cron job for scheduled OCR processing (runs INSIDE container)
# Prevents overlapping runs with file locking

LOCK_FILE="/tmp/ocr-processing.lock"
LOG_FILE="/app/data/cron-ocr.log"
SYNC_COMPOSE="${SYNC_SERVER_COMPOSE:-}"
SYNC_ENV="${SYNC_SERVER_ENV:-}"

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

# Check if sync server coordination is configured
if [ -n "$SYNC_COMPOSE" ] && [ -f "$SYNC_COMPOSE" ]; then
    log "Stopping sync server..."
    docker -H unix:///var/run/docker.sock compose -f "$SYNC_COMPOSE" stop >> "$LOG_FILE" 2>&1 || {
        log "ERROR: Failed to stop sync server"
        exit 1
    }
fi

# Run the OCR processing directly (we're already inside the container)
log "Running OCR processing..."
cd /app
python main.py >> "$LOG_FILE" 2>&1
OCR_EXIT=$?

if [ $OCR_EXIT -ne 0 ]; then
    log "ERROR: OCR processing failed with exit code $OCR_EXIT"
fi

# Restart sync server if we stopped it
if [ -n "$SYNC_COMPOSE" ] && [ -f "$SYNC_COMPOSE" ]; then
    log "Restarting sync server..."
    docker -H unix:///var/run/docker.sock compose -f "$SYNC_COMPOSE" start >> "$LOG_FILE" 2>&1 || {
        log "ERROR: Failed to restart sync server"
    }
fi

log "OCR processing finished"
exit $OCR_EXIT
