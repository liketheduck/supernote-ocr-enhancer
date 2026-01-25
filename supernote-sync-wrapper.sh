#!/bin/bash
#
# Supernote Sync Wrapper - Manual Mode
#
# Este script:
# 1. Abre la aplicación Supernote Partner
# 2. Espera a que TÚ la cierres manualmente
# 3. Ejecuta automáticamente el procesamiento OCR
#
# Uso:
#   ./supernote-sync-wrapper.sh
#

set -e

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/data/sync-wrapper.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Create log directory
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local message="[$timestamp] $1"
    echo -e "$message"
    echo "$message" | sed $'s/\033\\[[0-9;]*m//g' >> "$LOG_FILE"
}

log_info() {
    log "${BLUE}ℹ${NC}  $1"
}

log_success() {
    log "${GREEN}✓${NC}  $1"
}

log_warn() {
    log "${YELLOW}⚠${NC}  $1"
}

log_error() {
    log "${RED}✗${NC}  $1"
}

# Check if Supernote Partner is running
is_app_running() {
    pgrep -x "Supernote Partner" >/dev/null 2>&1
}

# Wait for app to close with visual feedback
wait_for_app_close() {
    local check_interval=2
    local elapsed=0
    
    echo ""
    log_info "Esperando a que cierres Supernote Partner..."
    echo ""
    echo -e "${CYAN}  Sincroniza tus notas y cierra la aplicación cuando termines.${NC}"
    echo -e "${CYAN}  El procesamiento OCR comenzará automáticamente.${NC}"
    echo ""
    
    # Show a simple progress indicator
    while is_app_running; do
        elapsed=$((elapsed + check_interval))
        local minutes=$((elapsed / 60))
        local seconds=$((elapsed % 60))
        printf "\r  ⏱  Tiempo transcurrido: %02d:%02d" $minutes $seconds
        sleep $check_interval
    done
    
    printf "\r\033[K"  # Clear the line
    echo ""
}

# Main execution
main() {
    echo ""
    echo "=========================================="
    echo "  Supernote Sync Wrapper"
    echo "=========================================="
    echo ""
    
    # Check if app is already running
    if is_app_running; then
        log_warn "Supernote Partner ya está en ejecución"
        log_info "Continuando con la app abierta..."
    else
        # Open Supernote Partner
        log_info "Abriendo Supernote Partner..."
        
        if ! open -a "Supernote Partner" 2>/dev/null; then
            log_error "No se pudo abrir Supernote Partner"
            log_error "¿Está instalada la aplicación?"
            exit 1
        fi
        
        # Give the app time to start
        sleep 3
        
        if ! is_app_running; then
            log_error "La aplicación no se inició correctamente"
            exit 1
        fi
        
        log_success "Supernote Partner abierta correctamente"
    fi
    
    # Wait for user to close the app
    wait_for_app_close
    
    log_success "Supernote Partner cerrada"
    
    # Small delay to ensure files are fully written
    log_info "Esperando a que los archivos se estabilicen..."
    sleep 2
    
    # Run OCR processing
    echo ""
    echo "=========================================="
    echo "  Procesamiento OCR"
    echo "=========================================="
    echo ""
    
    log_info "Iniciando procesamiento OCR..."
    
    # Check which mode to use
    if [[ -f "$SCRIPT_DIR/.env.local" ]]; then
        source "$SCRIPT_DIR/.env.local"
    elif [[ -f "$SCRIPT_DIR/.env" ]]; then
        source "$SCRIPT_DIR/.env"
    fi
    
    # Determine which script to run based on storage mode
    if [[ "${STORAGE_MODE:-}" == "mac_app" ]]; then
        log_info "Usando modo Mac App..."
        "$SCRIPT_DIR/run-with-macapp.sh" --auto
    else
        log_info "Usando modo nativo..."
        "$SCRIPT_DIR/scripts/run-ocr-native.sh"
    fi
    
    local exit_code=$?
    
    echo ""
    echo "=========================================="
    
    if [ $exit_code -eq 0 ]; then
        log_success "¡Procesamiento completado exitosamente!"
        echo ""
        log_info "Tus notas han sido procesadas con OCR mejorado"
        log_info "Los archivos están listos para sincronizar de vuelta al dispositivo"
    else
        log_error "El procesamiento OCR falló (código: $exit_code)"
        log_error "Revisa los logs para más detalles: $LOG_FILE"
    fi
    
    echo "=========================================="
    echo ""
    
    # Ask if user wants to reopen the app
    read -p "¿Quieres volver a abrir Supernote Partner para sincronizar? [Y/n] " -n 1 -r
    echo ""
    
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        log_info "Abriendo Supernote Partner..."
        open -a "Supernote Partner" 2>/dev/null || log_warn "No se pudo abrir la aplicación"
        log_info "Sincroniza para subir los cambios a la nube"
    fi
    
    echo ""
    log_info "¡Listo!"
    
    exit $exit_code
}

# Run main
main "$@"
