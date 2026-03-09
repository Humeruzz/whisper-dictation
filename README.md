# Whisper Dictation

Local speech-to-text dictation for Linux (Wayland). Press a keyboard shortcut to start recording, press again to stop — transcribed text is pasted at your cursor position.

Runs entirely offline using [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Includes a system tray icon and desktop notifications.

## How It Works

1. A background process listens for a global hotkey via `evdev`
2. On first press, recording starts from your microphone via `sounddevice`
3. On second press, recording stops and audio is transcribed with `faster-whisper`
4. The text is copied to clipboard (`wl-copy`) and pasted at your cursor via a simulated `Ctrl+V` (`evdev` UInput)

## Requirements

- Linux with **Wayland** (tested on GNOME/Mutter with PipeWire)
- Python 3.10+
- A microphone
- GNOME with AppIndicator extension (installed by default on Ubuntu)

## Setup

```bash
git clone https://github.com/Humeruzz/whisper-dictation.git
cd whisper-dictation
chmod +x setup.sh
./setup.sh
```

The setup script:
- Installs system packages (`wl-clipboard`, `libportaudio2`, AppIndicator GIR bindings)
- Adds your user to the `input` group (for keyboard/uinput access)
- Creates a udev rule for `/dev/uinput`
- Creates a Python venv and installs dependencies
- Installs a `.desktop` launcher

**You must log out and back in** after first setup for the `input` group change to take effect.

## Usage

**From the app menu:** Search for "Whisper Dictation" in Activities / app launcher.

**From the terminal:**

```bash
source .venv/bin/activate
python dictate.py
```

1. Wait for the "Ready" notification (first run downloads the ~500MB model)
2. Press **Super+Shift+S** to start recording
3. Speak
4. Press **Super+Shift+S** again to stop
5. Transcribed text is pasted at your cursor position

A **tray icon** in the top bar shows the current state (muted = idle, active = recording). Right-click to quit.

## Configuration

Edit the constants at the top of `dictate.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `MODEL_SIZE` | `"small"` | Whisper model: `tiny`, `base`, `small`, `medium`, `large-v3` |
| `LANGUAGE` | `"en"` | Language code, or `None` for auto-detect |
| `HOTKEY_KEY` | `KEY_S` | The letter key in the hotkey combo (Super+Shift+**S**) |

## Known Limitations

- **Super+Shift+S** may conflict with GNOME's screenshot shortcut — disable it in Settings > Keyboard > Shortcuts, or change the hotkey in `dictate.py`
- `evdev` and `/dev/uinput` require the user to be in the `input` group
- The venv must be created with `/usr/bin/python3` (not Anaconda) to access system `gi` bindings

## Troubleshooting

| Error | Fix |
|-------|-----|
| Cannot access input devices | `sudo usermod -aG input $USER`, then re-login |
| No audio input device found | Check mic is connected, PipeWire is running |
| Cannot write to /dev/uinput | Run `setup.sh` or see the error for manual udev steps |
| Text not appearing at cursor | Text is on your clipboard — paste manually with Ctrl+V |
| No tray icon | `gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com` |

## License

[MIT](LICENSE)
