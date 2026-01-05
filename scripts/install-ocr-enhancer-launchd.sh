#!/bin/bash
#
# Install the OCR Enhancer as macOS LaunchAgents (scheduled jobs)
#
# This creates two scheduled jobs:
#   - Hourly: Runs at :00 every hour (skips recently uploaded files)
#   - Daily:  Runs at 3:30 AM (processes ALL files)
#
# Usage:
#   ./scripts/install-ocr-enhancer-launchd.sh           # Install and enable
#   ./scripts/install-ocr-enhancer-launchd.sh --remove  # Uninstall
#   ./scripts/install-ocr-enhancer-launchd.sh --check   # Check status
#   ./scripts/install-ocr-enhancer-launchd.sh --run     # Run once immediately
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="$HOME/.supernote-ocr"

PLIST_HOURLY="com.supernote.ocr-enhancer.hourly"
PLIST_DAILY="com.supernote.ocr-enhancer.daily"
PLIST_DEST="$HOME/Library/LaunchAgents"

# Templates
TEMPLATE_HOURLY="$REPO_DIR/config/$PLIST_HOURLY.plist.template"
TEMPLATE_DAILY="$REPO_DIR/config/$PLIST_DAILY.plist.template"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# Handle --remove flag
if [[ "$1" == "--remove" ]] || [[ "$1" == "--uninstall" ]]; then
    log_info "Removing OCR Enhancer LaunchAgents..."

    for PLIST in "$PLIST_HOURLY" "$PLIST_DAILY"; do
        if launchctl list 2>/dev/null | grep -q "$PLIST"; then
            launchctl unload "$PLIST_DEST/$PLIST.plist" 2>/dev/null || true
            log_info "Stopped $PLIST"
        fi

        if [[ -f "$PLIST_DEST/$PLIST.plist" ]]; then
            rm "$PLIST_DEST/$PLIST.plist"
            log_info "Removed $PLIST_DEST/$PLIST.plist"
        fi
    done

    echo ""
    log_info "OCR Enhancer LaunchAgents removed."
    log_info "To run manually: ./scripts/run-ocr-native.sh"
    log_info "To reinstall: ./scripts/install-ocr-enhancer-launchd.sh"
    exit 0
fi

# Handle --check flag
if [[ "$1" == "--check" ]] || [[ "$1" == "--status" ]]; then
    echo ""
    echo "OCR Enhancer LaunchAgent Status:"
    echo "================================="
    echo ""

    for PLIST in "$PLIST_HOURLY" "$PLIST_DAILY"; do
        if launchctl list 2>/dev/null | grep -q "$PLIST"; then
            echo -e "${GREEN}[RUNNING]${NC} $PLIST"
            launchctl list "$PLIST" 2>/dev/null | head -5
        else
            echo -e "${YELLOW}[NOT LOADED]${NC} $PLIST"
        fi
        echo ""
    done

    # Show recent log entries
    DATA_PATH="${DATA_PATH:-$REPO_DIR/data}"
    if [[ -f "$DATA_PATH/cron-ocr.log" ]]; then
        echo "Recent log entries:"
        echo "-------------------"
        tail -10 "$DATA_PATH/cron-ocr.log"
    fi
    exit 0
fi

# Handle --run flag
if [[ "$1" == "--run" ]]; then
    log_info "Running OCR Enhancer once..."
    exec "$REPO_DIR/scripts/run-ocr-native.sh"
fi

# Main installation flow
echo ""
echo "========================================"
echo "  Supernote OCR Enhancer Installation  "
echo "========================================"
echo ""

# Step 1: Check prerequisites
log_step "Checking prerequisites..."

# Check for Python
PYTHON_CMD=""
if command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    log_error "Python 3 not found. Install with: brew install python@3.11"
    exit 1
fi
PYTHON_VERSION=$($PYTHON_CMD --version 2>&1)
log_info "Found Python: $PYTHON_VERSION"

# Check templates exist
if [[ ! -f "$TEMPLATE_HOURLY" ]]; then
    log_error "Template not found: $TEMPLATE_HOURLY"
    exit 1
fi
if [[ ! -f "$TEMPLATE_DAILY" ]]; then
    log_error "Template not found: $TEMPLATE_DAILY"
    exit 1
fi
log_info "Templates found"

# Step 2: Set up Python virtual environment
log_step "Setting up Python environment..."

if [[ ! -d "$REPO_DIR/.venv" ]]; then
    log_info "Creating virtual environment..."
    $PYTHON_CMD -m venv "$REPO_DIR/.venv"
fi

source "$REPO_DIR/.venv/bin/activate"
log_info "Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r "$REPO_DIR/app/requirements.txt"
log_info "Python environment ready: $REPO_DIR/.venv"

# Step 3: Set up configuration
log_step "Setting up configuration..."

mkdir -p "$CONFIG_DIR"
DATA_PATH="$REPO_DIR/data"
mkdir -p "$DATA_PATH"
mkdir -p "$DATA_PATH/backups"

# Check for existing config
if [[ ! -f "$CONFIG_DIR/.env" ]]; then
    if [[ -f "$REPO_DIR/.env.local" ]]; then
        # Convert existing .env.local for native use
        log_info "Found .env.local, adapting for native execution..."
        # Copy but update OCR_API_URL
        sed 's|host.docker.internal|localhost|g' "$REPO_DIR/.env.local" > "$CONFIG_DIR/.env"
        log_info "Created $CONFIG_DIR/.env from .env.local"
    else
        log_warn "No configuration found!"
        log_warn "Please create $CONFIG_DIR/.env with your settings."
        log_warn "See config/.env.launchd.example for reference."
        echo ""
        echo "Minimum required settings:"
        echo "  SUPERNOTE_DATA_PATH=/path/to/your/supernote/data"
        echo ""
        echo "For Personal Cloud mode, also set:"
        echo "  STORAGE_MODE=personal_cloud"
        echo "  MYSQL_PASSWORD=your_password"
        echo ""
        # Create a minimal example
        cat > "$CONFIG_DIR/.env" << 'EOF'
# Supernote OCR Enhancer Configuration
# Edit this file with your settings

# REQUIRED: Path to your Supernote data
SUPERNOTE_DATA_PATH=/path/to/your/supernote/data

# Storage mode: personal_cloud, mac_app, or leave blank
STORAGE_MODE=

# For personal_cloud mode:
# MYSQL_PASSWORD=your_password

# Processing settings (defaults are usually fine)
LOG_LEVEL=INFO
WRITE_TO_NOTE=true
CREATE_BACKUPS=true
FILE_RECOGN_TYPE=0
EOF
        log_warn "Created template at $CONFIG_DIR/.env - please edit it!"
    fi
else
    log_info "Using existing config: $CONFIG_DIR/.env"
fi

# Step 4: Stop existing services if running
log_step "Checking for existing installations..."

for PLIST in "$PLIST_HOURLY" "$PLIST_DAILY"; do
    if launchctl list 2>/dev/null | grep -q "$PLIST"; then
        log_info "Stopping existing $PLIST..."
        launchctl unload "$PLIST_DEST/$PLIST.plist" 2>/dev/null || true
        sleep 1
    fi
done

# Step 5: Generate plist files from templates
log_step "Generating LaunchAgent configurations..."

mkdir -p "$PLIST_DEST"

# Generate hourly plist
sed -e "s|__REPO_DIR__|$REPO_DIR|g" \
    -e "s|__DATA_PATH__|$DATA_PATH|g" \
    -e "s|__HOME__|$HOME|g" \
    "$TEMPLATE_HOURLY" > "$PLIST_DEST/$PLIST_HOURLY.plist"
log_info "Created $PLIST_DEST/$PLIST_HOURLY.plist"

# Generate daily plist
sed -e "s|__REPO_DIR__|$REPO_DIR|g" \
    -e "s|__DATA_PATH__|$DATA_PATH|g" \
    -e "s|__HOME__|$HOME|g" \
    "$TEMPLATE_DAILY" > "$PLIST_DEST/$PLIST_DAILY.plist"
log_info "Created $PLIST_DEST/$PLIST_DAILY.plist"

# Step 6: Load the LaunchAgents
log_step "Loading LaunchAgents..."

launchctl load "$PLIST_DEST/$PLIST_HOURLY.plist"
launchctl load "$PLIST_DEST/$PLIST_DAILY.plist"

sleep 2

# Step 7: Verify installation
log_step "Verifying installation..."

HOURLY_OK=false
DAILY_OK=false

if launchctl list 2>/dev/null | grep -q "$PLIST_HOURLY"; then
    HOURLY_OK=true
    log_info "Hourly job loaded successfully"
fi

if launchctl list 2>/dev/null | grep -q "$PLIST_DAILY"; then
    DAILY_OK=true
    log_info "Daily job loaded successfully"
fi

# Step 8: Summary
echo ""
echo "========================================"
echo "  Installation Complete!               "
echo "========================================"
echo ""

if $HOURLY_OK && $DAILY_OK; then
    log_info "The OCR Enhancer is now scheduled:"
    echo "    - Hourly: Every hour at :00"
    echo "    - Daily:  Every day at 3:30 AM (full run)"
    echo ""
    log_info "Next steps:"
    echo "    1. Edit $CONFIG_DIR/.env with your settings"
    echo "    2. Ensure OCR API is running: ./scripts/start-ocr-api.sh"
    echo "    3. Test with: ./scripts/install-ocr-enhancer-launchd.sh --run"
    echo ""
    log_info "Useful commands:"
    echo "    Check status:  ./scripts/install-ocr-enhancer-launchd.sh --check"
    echo "    Run now:       ./scripts/install-ocr-enhancer-launchd.sh --run"
    echo "    View logs:     tail -f $DATA_PATH/cron-ocr.log"
    echo "    Uninstall:     ./scripts/install-ocr-enhancer-launchd.sh --remove"
else
    log_error "Some jobs failed to load. Check with:"
    echo "    launchctl list | grep supernote"
    echo "    cat $DATA_PATH/launchd-hourly-error.log"
fi
echo ""
