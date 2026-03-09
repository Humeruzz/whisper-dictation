#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Whisper Dictation Tool Setup ==="
echo ""

# Install system packages
echo "[1/6] Installing system packages..."
sudo apt install -y wl-clipboard libportaudio2 portaudio19-dev gir1.2-ayatanaappindicator3-0.1

# Add user to input group (needed for evdev + uinput)
echo ""
echo "[2/6] Adding $USER to 'input' group..."
if groups "$USER" | grep -qw input; then
    echo "  Already in 'input' group."
else
    sudo usermod -aG input "$USER"
    echo "  Added. You MUST log out and back in for this to take effect."
fi

# Grant input group access to /dev/uinput (needed for Ctrl+V simulation)
echo ""
UDEV_RULE="/etc/udev/rules.d/80-uinput.rules"
echo "[3/6] Setting up /dev/uinput access..."
if [ -f "$UDEV_RULE" ]; then
    echo "  Udev rule already exists."
else
    echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | sudo tee "$UDEV_RULE" > /dev/null
    sudo udevadm control --reload-rules
    sudo udevadm trigger /dev/uinput
    echo "  Created udev rule and reloaded."
fi

# Create virtual environment
echo ""
echo "[4/6] Creating Python virtual environment..."
if [ -d ".venv" ]; then
    echo "  .venv already exists, skipping."
else
    /usr/bin/python3 -m venv --system-site-packages .venv
    echo "  Created .venv/"
fi

# Install Python dependencies
echo ""
echo "[5/6] Installing Python dependencies..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Install .desktop file for app launcher
echo ""
echo "[6/6] Installing desktop launcher..."
DESKTOP_FILE="$HOME/.local/share/applications/whisper-dictation.desktop"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
DICTATE_SCRIPT="$SCRIPT_DIR/dictate.py"
mkdir -p "$HOME/.local/share/applications"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=Whisper Dictation
Comment=Speech-to-text with Super+Shift+S
Exec=$VENV_PYTHON $DICTATE_SCRIPT
Icon=audio-input-microphone
Type=Application
Categories=Utility;Audio;
Terminal=false
EOF
echo "  Installed: $DESKTOP_FILE"

echo ""
echo "=== Setup complete ==="
echo ""
echo "If you were just added to the 'input' group, you MUST:"
echo "  1. Log out of your session"
echo "  2. Log back in"
echo ""
echo "You can now launch 'Whisper Dictation' from your app menu,"
echo "or run manually:"
echo "  source .venv/bin/activate"
echo "  python dictate.py"
