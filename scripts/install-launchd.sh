#!/bin/bash
#
# Install the OCR API as a macOS LaunchAgent (auto-start service)
#
# This makes the OCR API:
# - Start automatically when you log in
# - Restart automatically if it crashes
# - Run in the background (no terminal window needed)
#
# Usage:
#   ./scripts/install-launchd.sh           # Install and start
#   ./scripts/install-launchd.sh --remove  # Uninstall
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_NAME="com.supernote.ocr-api"
PLIST_TEMPLATE="$REPO_DIR/config/$PLIST_NAME.plist.template"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

# Default OCR API location
OCR_API_DIR="${OCR_API_DIR:-$HOME/services/ocr-api}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Handle --remove flag
if [[ "$1" == "--remove" ]] || [[ "$1" == "--uninstall" ]]; then
    log_info "Removing OCR API LaunchAgent..."

    if launchctl list | grep -q "$PLIST_NAME"; then
        launchctl unload "$PLIST_DEST" 2>/dev/null || true
        log_info "Stopped OCR API service"
    fi

    if [[ -f "$PLIST_DEST" ]]; then
        rm "$PLIST_DEST"
        log_info "Removed $PLIST_DEST"
    fi

    log_info "OCR API LaunchAgent removed. Use ./scripts/start-ocr-api.sh for manual runs."
    exit 0
fi

# Check prerequisites
log_info "Checking prerequisites..."

# Check for uv
UV_PATH=$(which uv 2>/dev/null || echo "")
if [[ -z "$UV_PATH" ]]; then
    if [[ -f "$HOME/.local/bin/uv" ]]; then
        UV_PATH="$HOME/.local/bin/uv"
    else
        log_error "uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
fi
log_info "Found uv at: $UV_PATH"

# Check for OCR API directory
if [[ ! -d "$OCR_API_DIR" ]]; then
    log_error "OCR API directory not found: $OCR_API_DIR"
    log_error "Set OCR_API_DIR environment variable or follow README setup instructions"
    exit 1
fi

if [[ ! -f "$OCR_API_DIR/server.py" ]]; then
    log_error "server.py not found in $OCR_API_DIR"
    log_error "Copy examples/server.py to $OCR_API_DIR/"
    exit 1
fi
log_info "Found OCR API at: $OCR_API_DIR"

# Ensure logs directory exists
mkdir -p "$OCR_API_DIR/logs"

# Check template exists
if [[ ! -f "$PLIST_TEMPLATE" ]]; then
    log_error "Template not found: $PLIST_TEMPLATE"
    exit 1
fi

# Stop existing service if running
if launchctl list | grep -q "$PLIST_NAME"; then
    log_info "Stopping existing OCR API service..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
    sleep 1
fi

# Generate plist from template
log_info "Generating LaunchAgent configuration..."
mkdir -p "$(dirname "$PLIST_DEST")"

sed -e "s|__UV_PATH__|$UV_PATH|g" \
    -e "s|__OCR_API_DIR__|$OCR_API_DIR|g" \
    -e "s|__HOME__|$HOME|g" \
    "$PLIST_TEMPLATE" > "$PLIST_DEST"

# Load the LaunchAgent
log_info "Loading LaunchAgent..."
launchctl load "$PLIST_DEST"

# Wait for startup
sleep 3

# Verify it's running
if curl -s http://localhost:8100/health > /dev/null 2>&1; then
    log_info "OCR API is running and healthy!"
    echo ""
    echo "Service status:"
    curl -s http://localhost:8100/health | python3 -m json.tool 2>/dev/null || curl -s http://localhost:8100/health
    echo ""
    log_info "The OCR API will now:"
    log_info "  - Start automatically on login"
    log_info "  - Restart automatically if it crashes"
    log_info "  - Run in background (no terminal needed)"
    echo ""
    log_info "To stop/remove: ./scripts/install-launchd.sh --remove"
    log_info "View logs: tail -f $OCR_API_DIR/logs/launchd-stdout.log"
else
    log_warn "OCR API may still be starting up..."
    log_warn "Check logs: tail -f $OCR_API_DIR/logs/launchd-stderr.log"
    log_warn "Check status: launchctl list | grep $PLIST_NAME"
fi
