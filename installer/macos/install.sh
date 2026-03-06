#!/bin/bash
# GlovU macOS Installer
# Usage: ./install.sh [--uninstall]

set -e

INSTALL_DIR="$HOME/Library/Application Support/GlovU/app"
PYTHON_MIN="3.11"

green() { echo -e "\033[32m  [ok] $1\033[0m"; }
cyan()  { echo -e "\033[36m  $1\033[0m"; }
warn()  { echo -e "\033[33m  [!]  $1\033[0m"; }
fail()  { echo -e "\033[31m  [x]  $1\033[0m"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------
if [[ "$1" == "--uninstall" ]]; then
    echo ""
    echo "Removing Glove AI Protection..."
    python3 "$INSTALL_DIR/main.py" --uninstall 2>/dev/null || true
    rm -rf "$INSTALL_DIR"
    green "Files removed."
    # Remove CA cert
    sudo security delete-certificate -c "mitmproxy" /Library/Keychains/System.keychain 2>/dev/null || true
    green "CA certificate removed."
    echo ""
    echo "Glove AI Protection has been removed."
    exit 0
fi

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
echo ""
echo "Glove AI Protection — Installer"
echo "================================"

# Check Python
cyan "Checking Python..."
if ! command -v python3 &>/dev/null; then
    fail "Python 3 not found. Install from https://python.org or via Homebrew: brew install python"
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_OK=$(python3 -c "import sys; print('ok' if sys.version_info >= (3, 11) else 'no')")
if [[ "$PY_OK" != "ok" ]]; then
    fail "Python 3.11+ required (found $PY_VER)."
fi
green "Python $PY_VER found."

# Create install directory
cyan "Setting up installation directory..."
mkdir -p "$INSTALL_DIR"

# Copy files
cyan "Copying files..."
cp -r "$PROJECT_DIR/glovu" "$INSTALL_DIR/"
cp "$PROJECT_DIR/main.py" "$INSTALL_DIR/"
cp "$PROJECT_DIR/requirements.txt" "$INSTALL_DIR/"
green "Files copied."

# Install dependencies
cyan "Installing dependencies..."
python3 -m pip install -q -r "$INSTALL_DIR/requirements.txt"
green "Dependencies installed."

# Run Python installer
cyan "Configuring system..."
python3 "$INSTALL_DIR/main.py" --install || warn "Some steps failed — check output above."

echo ""
echo "Installation complete."
echo "Glove AI Protection is running in the background."
echo "Look for the small icon in your menu bar."
echo ""
echo "To uninstall: ./install.sh --uninstall"
echo ""
