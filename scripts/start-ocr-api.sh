#!/bin/bash
#
# Start the OCR API server manually (foreground mode)
#
# Use this if you prefer manual control over the OCR API rather than
# running it as a background service via LaunchAgent.
#
# Usage:
#   ./scripts/start-ocr-api.sh           # Start in foreground (Ctrl+C to stop)
#   ./scripts/start-ocr-api.sh --check   # Just check if running
#   ./scripts/start-ocr-api.sh --stop    # Stop if running via launchd
#
# For automatic background operation, use: ./scripts/install-launchd.sh
#

set -e

# Default OCR API location
OCR_API_DIR="${OCR_API_DIR:-$HOME/services/ocr-api}"
OCR_PORT="${OCR_PORT:-8100}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_running() {
    if curl -s "http://localhost:$OCR_PORT/health" > /dev/null 2>&1; then
        return 0
    fi
    return 1
}

show_status() {
    if check_running; then
        log_info "OCR API is running on port $OCR_PORT"
        echo ""
        curl -s "http://localhost:$OCR_PORT/health" | python3 -m json.tool 2>/dev/null || \
            curl -s "http://localhost:$OCR_PORT/health"
        return 0
    else
        log_warn "OCR API is not running"
        return 1
    fi
}

# Handle --check flag
if [[ "$1" == "--check" ]] || [[ "$1" == "--status" ]]; then
    show_status
    exit $?
fi

# Handle --stop flag
if [[ "$1" == "--stop" ]]; then
    PLIST_NAME="com.supernote.ocr-api"
    if launchctl list | grep -q "$PLIST_NAME"; then
        log_info "Stopping OCR API LaunchAgent..."
        launchctl unload "$HOME/Library/LaunchAgents/$PLIST_NAME.plist" 2>/dev/null || true
        sleep 1
        log_info "Stopped"
    else
        log_warn "LaunchAgent not running. Checking for manual process..."
        pkill -f "python.*server.py.*$OCR_PORT" 2>/dev/null && log_info "Stopped manual process" || log_warn "No process found"
    fi
    exit 0
fi

# Check if already running
if check_running; then
    log_info "OCR API is already running!"
    show_status
    exit 0
fi

# Check prerequisites
if [[ ! -d "$OCR_API_DIR" ]]; then
    log_error "OCR API directory not found: $OCR_API_DIR"
    log_error ""
    log_error "Setup instructions:"
    log_error "  1. mkdir -p ~/services/ocr-api"
    log_error "  2. cd ~/services/ocr-api"
    log_error "  3. uv init --name ocr-api --python 3.11"
    log_error "  4. uv add ocrmac pillow fastapi uvicorn python-multipart"
    log_error "  5. cp /path/to/supernote-ocr-enhancer/examples/server.py ."
    log_error ""
    log_error "Or set OCR_API_DIR to your server location"
    exit 1
fi

if [[ ! -f "$OCR_API_DIR/server.py" ]]; then
    log_error "server.py not found in $OCR_API_DIR"
    exit 1
fi

# Check for uv
if ! command -v uv &> /dev/null; then
    if [[ -f "$HOME/.local/bin/uv" ]]; then
        export PATH="$HOME/.local/bin:$PATH"
    else
        log_error "uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
fi

# Start the server
log_info "Starting OCR API server..."
log_info "Directory: $OCR_API_DIR"
log_info "Port: $OCR_PORT"
log_info ""
log_info "Press Ctrl+C to stop"
log_info ""

cd "$OCR_API_DIR"
exec uv run python server.py
