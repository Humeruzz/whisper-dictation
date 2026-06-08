#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_FILE="$HOME/.local/share/applications/whisper-dictation.desktop"
UDEV_RULE="/etc/udev/rules.d/80-uinput.rules"
VENV_DIR="$SCRIPT_DIR/.venv"
ENV_FILE="$SCRIPT_DIR/.env"

# ── helpers ──────────────────────────────────────────────────────────────────

section() {
    echo ""
    echo "──────────────────────────────────────────────────────────────────"
    echo " $*"
    echo "──────────────────────────────────────────────────────────────────"
}

info()    { echo "  $*"; }
warn()    { echo "  ⚠  $*"; }
done_ok() { echo "  ✓  $*"; }
skipped() { echo "  –  Skipped."; }

ask_yes() { # default YES
    read -r -p "  $1 [Y/n] " reply
    [[ -z "${reply}" || "${reply,,}" == "y" ]]
}

ask_no() { # default NO (for risky/shared-resource actions)
    read -r -p "  $1 [y/N] " reply
    [[ "${reply,,}" == "y" ]]
}

# ── header ───────────────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Whisper Dictation — Uninstall Script   ║"
echo "╚══════════════════════════════════════════╝"
echo ""
info "The project folder will NOT be deleted."
info "You can reinstall at any time by running ./setup.sh again."
info ""
info "This script will walk you through each item that setup.sh"
info "installed and let you decide what to remove."

# ── [1/6] desktop launcher ───────────────────────────────────────────────────

section "[1/6] Desktop launcher"
info "WHAT: A .desktop file that registers 'Whisper Dictation' in your"
info "      application menu."
info "FILE: $DESKTOP_FILE"
info "SAFE: Yes — this file is specific to this project and has no"
info "      effect on any other software."
echo ""

if [[ -f "$DESKTOP_FILE" ]]; then
    rm -f "$DESKTOP_FILE"
    command -v update-desktop-database &>/dev/null && \
        update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    done_ok "Removed."
else
    done_ok "Not installed — nothing to do."
fi

# ── [2/6] virtual environment ────────────────────────────────────────────────

section "[2/6] Python virtual environment (.venv)"
info "WHAT: An isolated Python environment created inside this project"
info "      folder. It contains all Python dependencies for this app."
info "DIR:  $VENV_DIR"
info "SAFE: Yes — it lives inside the project folder and is completely"
info "      self-contained. No other software uses it."
echo ""

if [[ -d "$VENV_DIR" ]]; then
    rm -rf "$VENV_DIR"
    done_ok "Removed."
else
    done_ok "Not found — nothing to do."
fi

# ── [3/6] .env configuration file ────────────────────────────────────────────

section "[3/6] .env configuration file"
info "WHAT: Your personal configuration file — it stores settings like"
info "      your API key, microphone choice, and hotkey."
info "FILE: $ENV_FILE"
info "NOTE: Keeping it means you won't need to re-enter your settings"
info "      if you reinstall. Removing it is safe but irreversible."
echo ""

if [[ -f "$ENV_FILE" ]]; then
    if ask_yes "Keep .env so you can reinstall without re-configuring?"; then
        done_ok "Kept."
    else
        rm -f "$ENV_FILE"
        done_ok "Removed."
    fi
else
    done_ok "Not found — nothing to do."
fi

# ── [4/6] udev rule ──────────────────────────────────────────────────────────

section "[4/6] udev rule"
info "WHAT: A low-level Linux rule that grants the 'input' user group"
info "      permission to access /dev/uinput (a virtual keyboard device)."
info "FILE: $UDEV_RULE"
info "WHY:  Without it, this app cannot type transcribed text into other"
info "      windows."
info ""
info "RISK: Other tools like 'ydotool' or 'dotool' also need this rule."
info "      Removing it would silently break those tools."
info ""
info "Checking for other uinput consumers..."

UINPUT_TOOLS=()
for tool in ydotool dotool xdotool; do
    command -v "$tool" &>/dev/null && UINPUT_TOOLS+=("$tool")
done
OTHER_UINPUT_RULES=$(grep -rl "uinput" /etc/udev/rules.d/ 2>/dev/null | \
    grep -v "80-uinput.rules" || true)

if [[ -f "$UDEV_RULE" ]]; then
    if [[ ${#UINPUT_TOOLS[@]} -gt 0 || -n "$OTHER_UINPUT_RULES" ]]; then
        warn "Other uinput consumers detected:"
        [[ ${#UINPUT_TOOLS[@]} -gt 0 ]] && warn "  tools installed: ${UINPUT_TOOLS[*]}"
        [[ -n "$OTHER_UINPUT_RULES" ]] && warn "  other udev rules: $OTHER_UINPUT_RULES"
        warn "Removing the rule would break those tools."
        echo ""
        if ask_no "Remove it anyway?"; then
            sudo rm -f "$UDEV_RULE"
            sudo udevadm control --reload-rules && sudo udevadm trigger
            done_ok "Removed."
        else
            skipped
            info "To remove manually later: sudo rm $UDEV_RULE"
        fi
    else
        info "No other uinput consumers found."
        echo ""
        if ask_no "Remove the udev rule? (requires sudo)"; then
            sudo rm -f "$UDEV_RULE"
            sudo udevadm control --reload-rules && sudo udevadm trigger
            done_ok "Removed."
        else
            skipped
        fi
    fi
else
    done_ok "Not found — nothing to do."
fi

# ── [5/6] input group membership ─────────────────────────────────────────────

section "[5/6] 'input' group membership"
info "WHAT: Your user account was added to the 'input' Linux group."
info "      This group controls access to input devices like keyboards,"
info "      mice, and the virtual uinput device."
info ""
info "RISK: Other applications (ydotool, some accessibility tools, gaming"
info "      peripherals software) may also rely on this group membership."
info "      Removing it could prevent those tools from working."
info "NOTE: The change takes effect only after you log out and back in."
echo ""

if id -nG "$USER" 2>/dev/null | grep -qw input; then
    if ask_no "Remove '$USER' from the 'input' group? (requires sudo)"; then
        sudo gpasswd -d "$USER" input
        done_ok "Removed. Log out and back in for the change to take effect."
    else
        skipped
        info "To remove manually later: sudo gpasswd -d $USER input"
    fi
else
    done_ok "User '$USER' is not in the 'input' group — nothing to do."
fi

# ── [6/6] apt + pip packages ─────────────────────────────────────────────────

section "[6/6] System packages (apt + pip)"
info "WHAT: setup.sh installed these packages system-wide:"
info ""
info "  apt: build-essential           — C build tools (needed to compile some pip packages)"
info "       python3-dev               — Python C headers (needed to compile some pip packages)"
info "       wl-clipboard              — clipboard tool for Wayland (used at paste step)"
info "       libportaudio2             — audio I/O library (used by sounddevice)"
info "       portaudio19-dev           — development headers for PortAudio"
info "       gir1.2-ayatanaappindicator3-0.1 — system tray support"
info ""
info "  pip: openai-whisper  — AI speech recognition engine (core feature)"
info "       torch            — PyTorch backend for Whisper (installed separately by setup.sh)"
info "       torchvision      — companion to torch (installed by setup.sh)"
info "       sounddevice      — microphone recording library"
info "       evdev            — Linux input device library"
info "       python-dotenv    — .env file loader"
info "       (numpy is not listed — too commonly used by other tools)"
info ""
warn "These packages may be used by other software on your system."
warn "This script will NOT remove them automatically."
info ""
info "If you want to remove them manually, run:"
info ""
info "  sudo apt remove build-essential python3-dev wl-clipboard libportaudio2 \\"
info "       portaudio19-dev gir1.2-ayatanaappindicator3-0.1"
info ""
info "  pip uninstall openai-whisper torch torchvision sounddevice evdev python-dotenv"
info ""
info "Tip: Before removing apt packages, run:"
info "  apt rdepends --installed <package-name>"
info "to check if other installed software depends on them."

# ── done ─────────────────────────────────────────────────────────────────────

echo ""
echo "══════════════════════════════════════════════════════════════"
echo " Uninstall complete."
echo " Project folder is intact: $SCRIPT_DIR"
echo " Run ./setup.sh to reinstall."
echo "══════════════════════════════════════════════════════════════"
echo ""
