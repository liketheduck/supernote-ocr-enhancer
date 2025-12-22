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

# Sync database with new file info if sync server is configured
if [ -n "$SYNC_COMPOSE" ] && [ -f "$SYNC_COMPOSE" ] && [ -n "$SYNC_ENV" ] && [ -f "$SYNC_ENV" ]; then
    log "Syncing database with updated file info..."

    # Source sync server env for database credentials
    source "$SYNC_ENV"

    # Start just the database temporarily
    docker -H unix:///var/run/docker.sock compose -f "$SYNC_COMPOSE" start supernote-mariadb supernote-redis >> "$LOG_FILE" 2>&1
    sleep 5

    # Get current timestamp
    current_ts=$(($(date +%s) * 1000))
    local_time=$(date '+%Y-%m-%d %H:%M:%S')

    # Update all .note files in database
    SUPERNOTE_DATA="${SUPERNOTE_DATA_PATH:-/supernote/data}"
    updated=0

    # Get file list from database
    docker -H unix:///var/run/docker.sock exec supernote-mariadb mysql -usupernote -p"${MYSQL_PASSWORD}" supernotedb -N -e \
        "SELECT id, file_name FROM f_user_file WHERE file_name LIKE '%.note' AND is_active = 'Y';" 2>/dev/null > /tmp/db_files.txt

    while IFS=$'\t' read -r id filename; do
        [ -z "$id" ] && continue

        # Find file on disk
        diskfile=$(find "$SUPERNOTE_DATA" -name "$filename" -type f 2>/dev/null | head -1)

        if [ -n "$diskfile" ]; then
            disksize=$(stat -c%s "$diskfile" 2>/dev/null || stat -f%z "$diskfile" 2>/dev/null)
            diskmd5=$(md5sum "$diskfile" 2>/dev/null | cut -d' ' -f1 || md5 -q "$diskfile" 2>/dev/null)

            docker -H unix:///var/run/docker.sock exec supernote-mariadb mysql -usupernote -p"${MYSQL_PASSWORD}" supernotedb -e \
                "UPDATE f_user_file SET size = $disksize, md5 = '$diskmd5', terminal_file_edit_time = $current_ts, update_time = '$local_time' WHERE id = $id;" 2>/dev/null
            updated=$((updated + 1))
        fi
    done < /tmp/db_files.txt

    log "Updated $updated files in sync database"
    rm -f /tmp/db_files.txt
fi

# Restart sync server if we stopped it
if [ -n "$SYNC_COMPOSE" ] && [ -f "$SYNC_COMPOSE" ]; then
    log "Restarting sync server..."
    docker -H unix:///var/run/docker.sock compose -f "$SYNC_COMPOSE" up -d >> "$LOG_FILE" 2>&1 || {
        log "ERROR: Failed to restart sync server"
    }
fi

log "OCR processing finished"
exit $OCR_EXIT
