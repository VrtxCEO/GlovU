#!/bin/bash
# GlovU Linux Installer
# Usage: ./install.sh [--uninstall]

set -e

INSTALL_DIR="$HOME/.local/share/glovu/app"

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
    echo ""
    echo "Glove AI Protection has been removed."
    echo "Log out and back in for proxy environment variables to clear."
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
    fail "Python 3 not found. Install with: sudo apt install python3 (or your distro's package manager)"
fi

PY_OK=$(python3 -c "import sys; print('ok' if sys.version_info >= (3, 11) else 'no')")
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if [[ "$PY_OK" != "ok" ]]; then
    fail "Python 3.11+ required (found $PY_VER)."
fi
green "Python $PY_VER found."

# Check tkinter
if ! python3 -c "import tkinter" &>/dev/null; then
    warn "tkinter not found. Installing..."
    sudo apt-get install -y python3-tk 2>/dev/null || \
    sudo dnf install -y python3-tkinter 2>/dev/null || \
    warn "Could not install tkinter automatically. Install python3-tk with your package manager."
fi

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
python3 -m pip install --user -q -r "$INSTALL_DIR/requirements.txt"
green "Dependencies installed."

# Run Python installer
cyan "Configuring system..."
python3 "$INSTALL_DIR/main.py" --install || warn "Some steps failed — check output above."

echo ""
echo "Installation complete."
echo "Glove AI Protection is running in the background."
echo ""
echo "Note: Proxy environment variables in /etc/environment take effect on next login."
echo "To uninstall: ./install.sh --uninstall"
echo ""
