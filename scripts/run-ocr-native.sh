#!/bin/bash
#
# Native OCR processing runner for launchd
#
# This script runs the OCR enhancer natively on macOS, replacing the
# Docker-based cron-ocr-job.sh. It handles:
# - Loading environment from ~/.supernote-ocr/.env
# - Activating the Python virtual environment
# - File locking to prevent overlapping runs
# - Logging to the data directory
#
# Usage:
#   ./scripts/run-ocr-native.sh                    # Normal run
#   SKIP_RECENT_CHECK=true ./scripts/run-ocr-native.sh  # Full run (3am job)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# Load base config from repo .env.local if it exists (provides defaults)
if [[ -f "$REPO_DIR/.env.local" ]]; then
    set -a
    source "$REPO_DIR/.env.local"
    set +a
fi

# Load user config second - this OVERRIDES .env.local values
# User config should have localhost instead of host.docker.internal
if [[ -f "$HOME/.supernote-ocr/.env" ]]; then
    set -a
    source "$HOME/.supernote-ocr/.env"
    set +a
fi

# Ensure we use localhost for native execution (override any Docker-specific URL)
export OCR_API_URL="${OCR_API_URL/host.docker.internal/localhost}"
export DATA_PATH="${DATA_PATH:-$REPO_DIR/data}"
export PROCESS_INTERVAL="${PROCESS_INTERVAL:-0}"

# Ensure data directory exists
mkdir -p "$DATA_PATH"
mkdir -p "$DATA_PATH/backups"

LOCK_FILE="/tmp/ocr-processing.lock"
LOG_FILE="$DATA_PATH/cron-ocr.log"

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

log "Starting scheduled OCR processing (native)..."
log "  SUPERNOTE_DATA_PATH: ${SUPERNOTE_DATA_PATH:-not set}"
log "  OCR_API_URL: $OCR_API_URL"
log "  DATA_PATH: $DATA_PATH"
log "  STORAGE_MODE: ${STORAGE_MODE:-none}"
log "  SKIP_RECENT_CHECK: ${SKIP_RECENT_CHECK:-false}"
if [[ "${OCR_TXT_EXPORT_ENABLED:-false}" == "true" ]]; then
    log "  OCR_TXT_EXPORT_ENABLED: true"
    if [[ -n "$OCR_TXT_EXPORT_PATH" ]]; then
        log "  OCR_TXT_EXPORT_PATH: $OCR_TXT_EXPORT_PATH"
    else
        log "  WARNING: Text export enabled but OCR_TXT_EXPORT_PATH not set"
    fi
fi

# Activate Python virtual environment if present
PYTHON_CMD="python3"
if [[ -f "$REPO_DIR/.venv/bin/activate" ]]; then
    source "$REPO_DIR/.venv/bin/activate"
    PYTHON_CMD="python"
    log "Using venv: $REPO_DIR/.venv"
elif [[ -f "$REPO_DIR/venv/bin/activate" ]]; then
    source "$REPO_DIR/venv/bin/activate"
    PYTHON_CMD="python"
    log "Using venv: $REPO_DIR/venv"
else
    log "No venv found, using system Python"
fi

# Wake up external drive if SUPERNOTE_DATA_PATH is on an external volume
# macOS puts external drives to sleep (disksleep setting) and os.scandir()
# can fail with EINTR if the disk is waking up during the call
if [[ -n "$SUPERNOTE_DATA_PATH" && "$SUPERNOTE_DATA_PATH" == /Volumes/* ]]; then
    VOLUME_PATH=$(echo "$SUPERNOTE_DATA_PATH" | cut -d'/' -f1-3)
    if [[ -d "$VOLUME_PATH" ]]; then
        log "Waking up external volume: $VOLUME_PATH"
        # Touch the volume to wake it from sleep
        ls "$VOLUME_PATH" > /dev/null 2>&1
        # Give the disk time to fully spin up (especially for HDDs)
        sleep 3
        # Verify the data path is accessible
        if ! ls "$SUPERNOTE_DATA_PATH" > /dev/null 2>&1; then
            log "ERROR: Cannot access $SUPERNOTE_DATA_PATH after wake attempt"
            exit 1
        fi
        log "External volume is ready"
    fi
fi

# Verify OCR API is accessible
if ! curl -s --connect-timeout 5 "$OCR_API_URL/health" > /dev/null 2>&1; then
    log "WARNING: OCR API at $OCR_API_URL is not responding"
    log "Make sure the OCR API is running: ./scripts/start-ocr-api.sh"
    # Continue anyway - the Python code will handle the error gracefully
fi

# Run the OCR processor
log "Running OCR processing..."
cd "$REPO_DIR"
export PYTHONPATH="$REPO_DIR/app:$PYTHONPATH"
$PYTHON_CMD "$REPO_DIR/app/main.py" >> "$LOG_FILE" 2>&1
OCR_EXIT=$?

if [ $OCR_EXIT -ne 0 ]; then
    log "ERROR: OCR processing failed with exit code $OCR_EXIT"
else
    log "OCR processing completed successfully"
fi

exit $OCR_EXIT
