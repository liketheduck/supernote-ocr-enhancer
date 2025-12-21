#!/bin/bash
#
# Sync Supernote database to match filesystem
# Run this after modifying .note files to prevent sync conflicts
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load local environment
if [ -f "$PROJECT_DIR/.env.local" ]; then
    set -a
    source "$PROJECT_DIR/.env.local"
    set +a
fi

SUPERNOTE_DATA="${SUPERNOTE_DATA_PATH:?Set SUPERNOTE_DATA_PATH in .env.local}"
SUPERNOTE_COMPOSE="${SYNC_SERVER_COMPOSE:-}"
SYNC_ENV="${SYNC_SERVER_ENV:-}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "$1"
}

# Get database password
get_db_password() {
    if [ -n "$SYNC_ENV" ] && [ -f "$SYNC_ENV" ]; then
        source "$SYNC_ENV"
        echo "$MYSQL_PASSWORD"
    else
        echo "ERROR: SYNC_SERVER_ENV not set" >&2
        exit 1
    fi
}

# Run SQL query
run_sql() {
    local query="$1"
    local password=$(get_db_password)
    docker exec supernote-mariadb mysql -usupernote -p"${password}" supernotedb -N -e "$query" 2>/dev/null
}

# Get all .note files from filesystem with their sizes
get_filesystem_files() {
    find "$SUPERNOTE_DATA" -name "*.note" -type f -exec stat -f "%z %N" {} \; 2>/dev/null
}

# Main sync function
sync_database() {
    log "${YELLOW}Syncing Supernote database to filesystem...${NC}"

    local updated=0
    local deleted=0
    local password=$(get_db_password)

    # Get all file records from database
    local db_files=$(run_sql "SELECT id, file_name, size FROM f_user_file WHERE file_name LIKE '%.note' AND is_active = 'Y';")

    # Check each database record against filesystem
    while IFS=$'\t' read -r id filename dbsize; do
        [ -z "$id" ] && continue

        # Find this file on disk (search by filename)
        local diskfile=$(find "$SUPERNOTE_DATA" -name "$filename" -type f 2>/dev/null | head -1)

        if [ -z "$diskfile" ]; then
            # File doesn't exist on disk - mark as deleted or remove
            log "  Removing orphaned DB record: $filename"
            run_sql "DELETE FROM f_user_file WHERE id = $id;"
            ((deleted++))
        else
            # File exists - check if size matches
            local disksize=$(stat -f%z "$diskfile" 2>/dev/null)
            if [ "$disksize" != "$dbsize" ]; then
                log "  Updating: $filename ($dbsize -> $disksize bytes)"
                run_sql "UPDATE f_user_file SET size = $disksize, update_time = NOW() WHERE id = $id;"
                ((updated++))
            fi
        fi
    done <<< "$db_files"

    log "${GREEN}Database sync complete: $updated updated, $deleted removed${NC}"
}

# Run
sync_database
