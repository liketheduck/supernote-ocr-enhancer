#!/bin/bash
#
# Supernote OCR Enhancer - Run with Supernote Mac App
#
# This script processes .note files from the official Supernote Mac app.
# It optionally prompts you to quit the app, runs OCR enhancement, and
# updates the Mac app's SQLite database to prevent sync conflicts.
#
# Usage:
#   ./run-with-macapp.sh              # Run OCR enhancer with Mac app mode
#   ./run-with-macapp.sh --dry-run    # Show what would happen without doing it
#   ./run-with-macapp.sh --auto       # Auto-detect paths (no config needed)
#
# Unlike Personal Cloud mode, this does NOT require stopping a sync server.
# The Mac app stores sync state locally in SQLite, which we update directly.
#

set -e

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OCR_COMPOSE="$SCRIPT_DIR/docker-compose.yml"
LOG_FILE="$SCRIPT_DIR/data/macapp-control.log"

# Load local environment
if [ -f "$SCRIPT_DIR/.env.local" ]; then
    set -a
    source "$SCRIPT_DIR/.env.local"
    set +a
elif [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# State tracking
DRY_RUN=false
AUTO_DETECT=false
APP_WAS_RUNNING=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Parse arguments
for arg in "$@"; do
    case $arg in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --auto)
            AUTO_DETECT=true
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

# Auto-detect Supernote Mac app paths
auto_detect_paths() {
    local base_path="$HOME/Library/Containers/com.ratta.supernote/Data/Library/Application Support/com.ratta.supernote"

    if [ ! -d "$base_path" ]; then
        log_error "Supernote Mac app not installed or never run"
        log_error "Expected path: $base_path"
        return 1
    fi

    # Find user ID directory (numeric)
    local user_dir=""
    for dir in "$base_path"/*/; do
        dirname=$(basename "$dir")
        if [[ "$dirname" =~ ^[0-9]+$ ]]; then
            user_dir="$dir"
            break
        fi
    done

    if [ -z "$user_dir" ]; then
        log_error "No user data found in Supernote Mac app"
        return 1
    fi

    # Set paths (export so docker compose inherits them)
    MACAPP_USER_DATA_PATH="${user_dir%/}"
    export MACAPP_DATABASE_PATH="$MACAPP_USER_DATA_PATH/supernote.db"
    export MACAPP_NOTES_PATH="$MACAPP_USER_DATA_PATH/Supernote"
    export SUPERNOTE_DATA_PATH="$MACAPP_NOTES_PATH"

    if [ ! -f "$MACAPP_DATABASE_PATH" ]; then
        log_error "Mac app database not found: $MACAPP_DATABASE_PATH"
        return 1
    fi

    if [ ! -d "$MACAPP_NOTES_PATH" ]; then
        log_error "Mac app notes folder not found: $MACAPP_NOTES_PATH"
        return 1
    fi

    log_success "Auto-detected Mac app paths:"
    log_info "  User data: $MACAPP_USER_DATA_PATH"
    log_info "  Database:  $MACAPP_DATABASE_PATH"
    log_info "  Notes:     $MACAPP_NOTES_PATH"

    return 0
}

# Check if Supernote Mac app is running
# Note: The app is called "Supernote Partner" not just "Supernote"
is_app_running() {
    pgrep -f "Supernote Partner" >/dev/null 2>&1
}

# Get app status
get_app_status() {
    if is_app_running; then
        echo "Running (PID: $(pgrep -f 'Supernote Partner' | head -1))"
    else
        echo "Not running"
    fi
}

# Prompt user to quit the app (optional but recommended)
prompt_quit_app() {
    if ! is_app_running; then
        log_info "Supernote Mac app is not running"
        return 0
    fi

    APP_WAS_RUNNING=true

    echo ""
    log_warn "Supernote Mac app is currently running"
    log_warn "It's recommended (but not required) to quit the app during OCR processing"
    log_warn "to prevent potential file access conflicts."
    echo ""

    if $DRY_RUN; then
        log_info "[DRY RUN] Would prompt to quit the app"
        return 0
    fi

    read -p "Would you like to quit the Supernote app? [y/N] " -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Sending quit signal to Supernote Partner..."
        osascript -e 'tell application "Supernote Partner" to quit' 2>/dev/null || true
        sleep 2

        if is_app_running; then
            log_warn "App is still running. You may need to quit it manually."
        else
            log_success "Supernote Partner app quit successfully"
        fi
    else
        log_info "Continuing with app running (not recommended but usually works)"
    fi
}

# Offer to restart the app
offer_restart_app() {
    if ! $APP_WAS_RUNNING; then
        return 0
    fi

    if is_app_running; then
        return 0
    fi

    echo ""
    read -p "Would you like to restart the Supernote app? [Y/n] " -n 1 -r
    echo ""

    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        log_info "Starting Supernote Partner app..."
        open -a "Supernote Partner" 2>/dev/null || log_warn "Could not start Supernote Partner app"
    fi
}

# Count .note files
count_note_files() {
    local notes_path="${MACAPP_NOTES_PATH:-$SUPERNOTE_DATA_PATH}"
    if [ -d "$notes_path" ]; then
        find "$notes_path" -name "*.note" -type f 2>/dev/null | wc -l | tr -d ' '
    else
        echo "0"
    fi
}

# Run OCR enhancer with Mac app configuration
run_ocr_enhancer() {
    log_info "Running Supernote OCR Enhancer (Mac app mode)..."

    # Build docker arguments array
    local docker_args=(
        -e STORAGE_MODE=mac_app
        -e SUPERNOTE_DATA_PATH=/supernote/data
        -e MACAPP_DATABASE_PATH=/macapp/supernote.db
        -v "$SUPERNOTE_DATA_PATH:/supernote/data"
        -v "$MACAPP_DATABASE_PATH:/macapp/supernote.db"
    )

    # Add text export configuration if enabled
    if [ "${OCR_TXT_EXPORT_ENABLED:-false}" = "true" ]; then
        docker_args+=(-e OCR_TXT_EXPORT_ENABLED=true)
        if [ -n "$OCR_TXT_EXPORT_PATH" ]; then
            # Expand ~ to full path
            local export_path_expanded="${OCR_TXT_EXPORT_PATH/#\~/$HOME}"
            # Ensure directory exists
            mkdir -p "$export_path_expanded"
            # Mount and set container path
            docker_args+=(-e OCR_TXT_EXPORT_PATH=/txt-export)
            docker_args+=(-v "$export_path_expanded:/txt-export")
            log_info "Text export: $export_path_expanded -> /txt-export"
        else
            log_warn "Text export enabled but OCR_TXT_EXPORT_PATH not set"
        fi
    fi

    if $DRY_RUN; then
        log_info "[DRY RUN] Would run OCR enhancer with:"
        log_info "  SUPERNOTE_DATA_PATH=$SUPERNOTE_DATA_PATH"
        log_info "  STORAGE_MODE=mac_app"
        log_info "  MACAPP_DATABASE_PATH=$MACAPP_DATABASE_PATH"
        if [ "${OCR_TXT_EXPORT_ENABLED:-false}" = "true" ]; then
            log_info "  OCR_TXT_EXPORT_ENABLED=true"
            log_info "  OCR_TXT_EXPORT_PATH=${OCR_TXT_EXPORT_PATH:-not set}"
        fi
        return 0
    fi

    # Run with Mac app configuration
    docker compose -f "$OCR_COMPOSE" run --rm \
        "${docker_args[@]}" \
        ocr-enhancer python /app/main.py

    local exit_code=$?

    if [ $exit_code -eq 0 ]; then
        log_success "OCR enhancer completed successfully"
    else
        log_error "OCR enhancer exited with code $exit_code"
    fi

    return $exit_code
}

# Update Mac app database for modified files
sync_macapp_database() {
    log_info "Syncing Mac app database..."

    if $DRY_RUN; then
        log_info "[DRY RUN] Would sync database at: $MACAPP_DATABASE_PATH"
        return 0
    fi

    # The sync_handlers.py module handles this inside the container
    # This function is here for any additional cleanup needed

    # Verify database is accessible
    if [ -f "$MACAPP_DATABASE_PATH" ]; then
        local note_count=$(sqlite3 "$MACAPP_DATABASE_PATH" \
            "SELECT COUNT(*) FROM supernote_sqlite_info WHERE file_name LIKE '%.note';" 2>/dev/null || echo "unknown")
        log_success "Mac app database synced ($note_count .note files tracked)"
    else
        log_warn "Could not verify database sync"
    fi
}

# Main execution
main() {
    log_info "=========================================="
    log_info "Supernote OCR Enhancer - Mac App Mode"
    log_info "=========================================="

    if $DRY_RUN; then
        log_warn "DRY RUN MODE - No changes will be made"
    fi

    # Check compose file
    if [ ! -f "$OCR_COMPOSE" ]; then
        log_error "Docker compose file not found: $OCR_COMPOSE"
        exit 1
    fi

    # Auto-detect or validate paths
    if $AUTO_DETECT; then
        log_info "Auto-detecting Supernote Mac app paths..."
        if ! auto_detect_paths; then
            exit 1
        fi
    else
        # Check required environment variables
        if [ -z "$SUPERNOTE_DATA_PATH" ] && [ -z "$MACAPP_NOTES_PATH" ]; then
            log_warn "No paths configured. Attempting auto-detection..."
            if ! auto_detect_paths; then
                log_error "Set SUPERNOTE_DATA_PATH or MACAPP_NOTES_PATH in .env.local"
                log_error "Or run with --auto flag for auto-detection"
                exit 1
            fi
        else
            # Export so docker compose inherits the value
            export SUPERNOTE_DATA_PATH="${MACAPP_NOTES_PATH:-$SUPERNOTE_DATA_PATH}"
        fi

        if [ -z "$MACAPP_DATABASE_PATH" ]; then
            # Try to find it relative to notes path
            local user_dir=$(dirname "$SUPERNOTE_DATA_PATH")
            if [ -f "$user_dir/supernote.db" ]; then
                export MACAPP_DATABASE_PATH="$user_dir/supernote.db"
                log_info "Found database at: $MACAPP_DATABASE_PATH"
            else
                log_error "MACAPP_DATABASE_PATH not set and could not be auto-detected"
                exit 1
            fi
        fi
    fi

    # Show configuration
    echo ""
    log_info "Configuration:"
    log_info "  Notes path:    $SUPERNOTE_DATA_PATH"
    log_info "  Database:      $MACAPP_DATABASE_PATH"
    log_info "  .note files:   $(count_note_files)"
    echo ""

    # Check app status and optionally quit
    log_info "Checking Supernote app status..."
    log_info "  Status: $(get_app_status)"
    prompt_quit_app

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

    # Sync database
    if [ $ocr_exit -eq 0 ]; then
        echo ""
        sync_macapp_database
    fi

    # Offer to restart app if it was running
    if ! $DRY_RUN; then
        offer_restart_app
    fi

    echo ""
    log_info "Done!"

    exit $ocr_exit
}

# Run main
main "$@"
