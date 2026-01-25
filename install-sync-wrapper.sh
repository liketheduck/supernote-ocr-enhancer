#!/bin/bash
#
# Instalador del Supernote Sync Wrapper
#
# Este script configura el wrapper manual y opcionalmente añade un alias
# para ejecutarlo desde cualquier lugar.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER_SCRIPT="$SCRIPT_DIR/supernote-sync-wrapper.sh"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "=========================================="
echo "  Supernote Sync Wrapper - Instalación"
echo "=========================================="
echo ""

# Make wrapper executable
if [[ ! -x "$WRAPPER_SCRIPT" ]]; then
    echo -e "${BLUE}[1/3]${NC} Haciendo el script ejecutable..."
    chmod +x "$WRAPPER_SCRIPT"
    echo -e "${GREEN}✓${NC} Script ejecutable"
else
    echo -e "${GREEN}✓${NC} Script ya es ejecutable"
fi

echo ""

# Test the wrapper (dry run)
echo -e "${BLUE}[2/3]${NC} Verificando dependencias..."

# Check if Supernote Partner is installed
if [[ ! -d "/Applications/Supernote Partner.app" ]]; then
    echo -e "${YELLOW}⚠${NC}  Advertencia: No se encuentra Supernote Partner en /Applications/"
    echo "   El wrapper intentará abrirla de todas formas."
fi

# Check if OCR API is running
if curl -s http://localhost:8100/health >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} OCR API está corriendo"
else
    echo -e "${YELLOW}⚠${NC}  OCR API no está corriendo en localhost:8100"
    echo "   Inicia el OCR API antes de usar el wrapper:"
    echo "   ./scripts/start-ocr-api.sh"
fi

echo ""

# Offer to add alias
echo -e "${BLUE}[3/3]${NC} Configuración de alias (opcional)"
echo ""
echo "¿Quieres añadir un alias 'supernote-sync' a tu shell?"
echo "Esto te permitirá ejecutar el wrapper desde cualquier directorio."
echo ""
read -p "Añadir alias? [Y/n] " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    # Detect shell
    SHELL_CONFIG=""
    if [[ -n "$ZSH_VERSION" ]] || [[ "$SHELL" == *"zsh"* ]]; then
        SHELL_CONFIG="$HOME/.zshrc"
    elif [[ -n "$BASH_VERSION" ]] || [[ "$SHELL" == *"bash"* ]]; then
        SHELL_CONFIG="$HOME/.bashrc"
    fi
    
    if [[ -z "$SHELL_CONFIG" ]]; then
        echo -e "${YELLOW}⚠${NC}  No se pudo detectar tu shell"
        echo "   Añade manualmente a tu archivo de configuración:"
        echo "   alias supernote-sync='$WRAPPER_SCRIPT'"
    else
        # Check if alias already exists
        if grep -q "alias supernote-sync=" "$SHELL_CONFIG" 2>/dev/null; then
            echo -e "${YELLOW}⚠${NC}  El alias ya existe en $SHELL_CONFIG"
            echo "   Actualízalo manualmente si es necesario"
        else
            # Add alias
            echo "" >> "$SHELL_CONFIG"
            echo "# Supernote Sync Wrapper" >> "$SHELL_CONFIG"
            echo "alias supernote-sync='$WRAPPER_SCRIPT'" >> "$SHELL_CONFIG"
            
            echo -e "${GREEN}✓${NC} Alias añadido a $SHELL_CONFIG"
            echo ""
            echo "   Recarga tu shell para usar el alias:"
            echo "   source $SHELL_CONFIG"
            echo ""
            echo "   O simplemente abre una nueva terminal."
        fi
    fi
else
    echo "   Puedes ejecutar el wrapper directamente:"
    echo "   $WRAPPER_SCRIPT"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}✓${NC} Instalación completada"
echo "=========================================="
echo ""
echo "Uso:"
echo ""
echo "  Opción 1 - Con alias (si lo configuraste):"
echo "    supernote-sync"
echo ""
echo "  Opción 2 - Ruta completa:"
echo "    $WRAPPER_SCRIPT"
echo ""
echo "  Opción 3 - Desde el directorio del proyecto:"
echo "    ./supernote-sync-wrapper.sh"
echo ""
echo "Lee SYNC-WRAPPER.md para más información."
echo ""
