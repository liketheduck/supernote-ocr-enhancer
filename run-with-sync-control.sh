#!/bin/bash
#
# Supernote OCR Enhancer - Run with Sync Server Coordination
#
# This script ensures the Supernote sync server is stopped during OCR processing
# to prevent file conflicts, then restarts it afterward.
#
# Usage:
#   ./run-with-sync-control.sh              # Run OCR enhancer
#   ./run-with-sync-control.sh --dry-run    # Show what would happen without doing it
#

set -e

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OCR_COMPOSE="$SCRIPT_DIR/docker-compose.yml"
LOG_FILE="$SCRIPT_DIR/data/sync-control.log"

# Load local environment (contains paths specific to this machine)
if [ -f "$SCRIPT_DIR/.env.local" ]; then
    set -a
    source "$SCRIPT_DIR/.env.local"
    set +a
elif [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# Use environment variables with defaults
SYNC_COMPOSE="${SYNC_SERVER_COMPOSE:-}"
SYNC_ENV="${SYNC_SERVER_ENV:-}"
SUPERNOTE_DATA="${SUPERNOTE_DATA_PATH:-/supernote/data}"

# State tracking
SYNC_WAS_RUNNING=false
DRY_RUN=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
for arg in "$@"; do
    case $arg in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
    esac
done

log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local message="[$timestamp] $1"
    echo -e "$message"
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "$message" | sed $'s/\033\\[[0-9;]*m//g' >> "$LOG_FILE"
}

log_info() {
    log "${BLUE}INFO${NC}: $1"
}

log_success() {
    log "${GREEN}SUCCESS${NC}: $1"
}

log_warn() {
    log "${YELLOW}WARNING${NC}: $1"
}

log_error() {
    log "${RED}ERROR${NC}: $1"
}

# Check if sync server is running
is_sync_running() {
    local running_containers=$(docker compose -f "$SYNC_COMPOSE" ps --status running -q 2>/dev/null | wc -l)
    [ "$running_containers" -gt 0 ]
}

# Get sync server status summary
get_sync_status() {
    docker compose -f "$SYNC_COMPOSE" ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null || echo "Unable to get status"
}

# Stop sync server gracefully
stop_sync_server() {
    log_info "Stopping Supernote sync server..."

    if $DRY_RUN; then
        log_info "[DRY RUN] Would run: docker compose -f $SYNC_COMPOSE stop"
        return 0
    fi

    # Graceful stop with timeout
    if docker compose -f "$SYNC_COMPOSE" stop --timeout 30; then
        log_success "Sync server stopped gracefully"
        return 0
    else
        log_error "Failed to stop sync server gracefully"
        return 1
    fi
}

# Start sync server
start_sync_server() {
    log_info "Starting Supernote sync server..."

    if $DRY_RUN; then
        log_info "[DRY RUN] Would run: docker compose -f $SYNC_COMPOSE start"
        return 0
    fi

    if docker compose -f "$SYNC_COMPOSE" start; then
        log_success "Sync server started"

        # Wait a moment and verify
        sleep 3
        if is_sync_running; then
            log_success "Sync server is running"
            return 0
        else
            log_warn "Sync server may not have started correctly"
            return 1
        fi
    else
        log_error "Failed to start sync server"
        return 1
    fi
}

# Run OCR enhancer
run_ocr_enhancer() {
    log_info "Running Supernote OCR Enhancer..."

    if $DRY_RUN; then
        log_info "[DRY RUN] Would run: docker compose -f $OCR_COMPOSE run --rm ocr-enhancer python /app/main.py"
        return 0
    fi

    # Run OCR enhancer (single run mode with PROCESS_INTERVAL=0)
    docker compose -f "$OCR_COMPOSE" run --rm ocr-enhancer python /app/main.py
    local exit_code=$?

    if [ $exit_code -eq 0 ]; then
        log_success "OCR enhancer completed successfully"
    else
        log_error "OCR enhancer exited with code $exit_code"
    fi

    return $exit_code
}

# Sync Supernote database to match filesystem changes
sync_supernote_database() {
    log_info "Syncing Supernote database to filesystem..."

    if $DRY_RUN; then
        log_info "[DRY RUN] Would sync database to match modified files"
        return 0
    fi

    # Get database password from sync server env
    if [ -z "$SYNC_ENV" ] || [ ! -f "$SYNC_ENV" ]; then
        log_error "SYNC_SERVER_ENV not set or file not found. Set in .env.local"
        return 1
    fi
    source "$SYNC_ENV"

    # Need sync server running temporarily to access database
    log_info "Starting MariaDB temporarily for database sync..."
    docker compose -f "$SYNC_COMPOSE" start supernote-mariadb supernote-redis >/dev/null 2>&1
    sleep 3

    # Wait for MariaDB to be healthy
    local retries=10
    while [ $retries -gt 0 ]; do
        if docker exec supernote-mariadb mysqladmin ping -usupernote -p"${MYSQL_PASSWORD}" >/dev/null 2>&1; then
            break
        fi
        sleep 1
        ((retries--))
    done

    if [ $retries -eq 0 ]; then
        log_error "MariaDB not responding, skipping database sync"
        return 1
    fi

    local updated=0
    local deleted=0
    # SUPERNOTE_DATA is set from environment at script start

    # Get all .note file records from database (id, filename, size, md5, terminal_file_edit_time)
    local db_records=$(docker exec supernote-mariadb mysql -usupernote -p"${MYSQL_PASSWORD}" supernotedb -N -e \
        "SELECT id, file_name, size, md5, terminal_file_edit_time FROM f_user_file WHERE file_name LIKE '%.note' AND is_active = 'Y';" 2>/dev/null)

    # Current timestamp in milliseconds for terminal_file_edit_time
    local current_ts=$(($(date +%s) * 1000))

    while IFS=$'\t' read -r id filename dbsize dbmd5 db_edit_time; do
        [ -z "$id" ] && continue

        # Find this file on disk
        local diskfile=$(find "$SUPERNOTE_DATA" -name "$filename" -type f 2>/dev/null | head -1)

        if [ -z "$diskfile" ]; then
            # File doesn't exist on disk - remove from database
            log_info "  Removing orphaned record: $filename"
            docker exec supernote-mariadb mysql -usupernote -p"${MYSQL_PASSWORD}" supernotedb -e \
                "DELETE FROM f_user_file WHERE id = $id;" 2>/dev/null
            ((deleted++))
        else
            # File exists - check if size, MD5, or terminal_file_edit_time needs update
            local disksize=$(stat -f%z "$diskfile" 2>/dev/null)
            local diskmd5=$(md5 -q "$diskfile" 2>/dev/null)

            # Update if: size changed, MD5 changed, OR terminal_file_edit_time is 0/missing
            if [ "$disksize" != "$dbsize" ] || [ "$diskmd5" != "$dbmd5" ] || [ "$db_edit_time" = "0" ] || [ -z "$db_edit_time" ]; then
                log_info "  Updating: $filename"
                # Use local time (not UTC) to match how Supernote device stores timestamps
                local local_time=$(date '+%Y-%m-%d %H:%M:%S')
                docker exec supernote-mariadb mysql -usupernote -p"${MYSQL_PASSWORD}" supernotedb -e \
                    "UPDATE f_user_file
                     SET size = $disksize,
                         md5 = '$diskmd5',
                         terminal_file_edit_time = $current_ts,
                         update_time = '$local_time'
                     WHERE id = $id;" 2>/dev/null
                ((updated++))
            fi
        fi
    done <<< "$db_records"

    # Stop the database again (cleanup will restart everything properly)
    docker compose -f "$SYNC_COMPOSE" stop supernote-mariadb supernote-redis >/dev/null 2>&1

    log_success "Database sync complete: $updated updated, $deleted removed"
    return 0
}

# Cleanup function - ensures sync server is restarted
cleanup() {
    local exit_code=$?

    log_info "Cleanup triggered (exit code: $exit_code)"

    if $SYNC_WAS_RUNNING; then
        log_info "Sync server was running before - ensuring it's restarted..."
        start_sync_server || log_error "Failed to restart sync server during cleanup!"
    else
        log_info "Sync server was not running before - leaving it stopped"
    fi

    exit $exit_code
}

# Main execution
main() {
    log_info "=========================================="
    log_info "Supernote OCR Enhancer - Sync Control"
    log_info "=========================================="

    if $DRY_RUN; then
        log_warn "DRY RUN MODE - No changes will be made"
    fi

    # Check if compose files exist
    if [ ! -f "$OCR_COMPOSE" ]; then
        log_error "OCR compose file not found: $OCR_COMPOSE"
        exit 1
    fi

    if [ ! -f "$SYNC_COMPOSE" ]; then
        log_error "Sync server compose file not found: $SYNC_COMPOSE"
        exit 1
    fi

    # Check current sync server status
    log_info "Checking sync server status..."
    if is_sync_running; then
        SYNC_WAS_RUNNING=true
        log_info "Sync server is currently running"
        echo ""
        get_sync_status
        echo ""
    else
        SYNC_WAS_RUNNING=false
        log_info "Sync server is not running"
    fi

    # Set up cleanup trap AFTER we know if sync was running
    trap cleanup EXIT INT TERM

    # Stop sync server if running
    if $SYNC_WAS_RUNNING; then
        stop_sync_server || {
            log_error "Cannot proceed - sync server failed to stop"
            exit 1
        }

        # Verify it's stopped
        sleep 2
        if is_sync_running && ! $DRY_RUN; then
            log_error "Sync server still running after stop command!"
            exit 1
        fi
        log_success "Sync server stopped - safe to proceed with OCR"
    fi

    echo ""
    log_info "=========================================="
    log_info "Starting OCR Processing"
    log_info "=========================================="
    echo ""

    # Run OCR enhancer
    run_ocr_enhancer
    local ocr_exit=$?

    echo ""
    log_info "=========================================="
    log_info "OCR Processing Complete"
    log_info "=========================================="

    # Sync database to match filesystem changes (prevents conflicts)
    echo ""
    log_info "=========================================="
    log_info "Syncing Database"
    log_info "=========================================="
    echo ""
    sync_supernote_database

    # Note: cleanup trap will handle restarting sync server
    # We just need to exit with the OCR exit code
    exit $ocr_exit
}

# Run main
main "$@"
