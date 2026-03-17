# Whisper Dictation

Local speech-to-text dictation for Linux (Wayland). Press a keyboard shortcut to start recording, press again to stop — transcribed text is pasted at your cursor position.

Runs entirely offline using [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Optionally routes transcription through a local LLM ([LM Studio](https://lmstudio.ai)) to clean up filler words, false starts, and mid-sentence corrections before pasting. Includes a system tray icon and desktop notifications.

## How It Works

1. A background process listens for a global hotkey via `evdev`
2. On first press, recording starts from your microphone via `sounddevice`
3. On second press, recording stops and audio is transcribed with `faster-whisper`
4. *(Optional)* The transcription is sent to a local LLM for cleanup or summarization
5. The final text is copied to clipboard (`wl-copy`) and pasted at your cursor via a simulated `Ctrl+V` (`evdev` UInput)

## Requirements

- Linux with **Wayland** (tested on GNOME/Mutter with PipeWire)
- Python 3.10+
- A microphone
- GNOME with AppIndicator extension (installed by default on Ubuntu)
- *(Optional)* [LM Studio](https://lmstudio.ai) for LLM-based text cleanup

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

## Configuration

All settings live in a `.env` file that you create from the provided template:

```bash
cp .env.example .env
```

Then edit `.env` to your preferences. Your changes are git-ignored — they stay local. The `.env.example` file is committed and serves as the reference template with full comments.

### Key settings

| Setting | Default | Description |
|---|---|---|
| `MODEL_SIZE` | `small` | Whisper model: `tiny`, `base`, `small`, `medium`, `large-v3` |
| `WHISPER_LANGUAGE` | `en` | Language code, or empty for auto-detect |
| `PASTE_DELAY_MS` | `100` | Delay between clipboard copy and Ctrl+V (increase if paste is blank) |
| `LLM_ENABLED` | `true` | Set to `false` to skip LLM and paste raw Whisper output |
| `LLM_BASE_URL` | `http://localhost:1234/v1` | LM Studio local server address |
| `LLM_MODE` | `format` | `format` = cleanup only, `summarize` = condense to key points |
| `LLM_TIMEOUT` | `10` | Seconds to wait for LLM before falling back to raw transcription |

To change the hotkey (default: **Super+Shift+S**), edit the `HOTKEY_*` constants at the top of `whisper.py`.

## Usage

**From the app menu:** Search for "Whisper Dictation" in Activities / app launcher.

**From the terminal:**

```bash
source .venv/bin/activate
python src/app.py
```

1. Wait for the "Ready" notification (first run downloads the Whisper model)
2. Press **Super+Shift+S** to start recording
3. Speak
4. Press **Super+Shift+S** again to stop
5. The tray icon shows: Recording → Transcribing → Formatting *(if LLM enabled)* → Idle
6. Transcribed (and optionally cleaned-up) text is pasted at your cursor

## LLM Formatting (LM Studio)

When `LLM_ENABLED=true`, each transcription is sent to a local LLM before pasting.

**Recommended models** (search by name in LM Studio, download the `Q4_K_M` variant):

- **Qwen2.5-7B-Instruct** (~5 GB RAM) — best balance of speed and quality, recommended default
- **Phi-4-Mini-Instruct** (~3 GB RAM) — great instruction following, lighter on RAM
- **Llama-3.1-8B-Instruct** (~6 GB RAM) — highest output quality if you have the RAM

All three reliably follow the "return only cleaned text" instruction without adding commentary.

**Setup:**
1. Download and install [LM Studio](https://lmstudio.ai)
2. Search for one of the models above and download its `Q4_K_M` variant
3. Load the model and enable the local server (default port: 1234)

**Modes (`LLM_MODE`):**

- `format` — Removes filler words ("um", "uh", "like"), fixes false starts and corrections, improves punctuation. Does not rephrase or shorten. Best for messages, emails, code comments.
- `summarize` — Condenses the transcription to its key points. Best for long voice notes, meeting recaps, brainstorming dumps.

If LM Studio is not running or times out, the app falls back to raw Whisper output silently — dictation always works.

## Known Limitations

- **Super+Shift+S** may conflict with GNOME's screenshot shortcut — disable it in Settings > Keyboard > Shortcuts, or change the hotkey in `whisper.py`
- `evdev` and `/dev/uinput` require the user to be in the `input` group
- The venv must be created with `/usr/bin/python3` (not Anaconda) to access system `gi` bindings

## Troubleshooting

| Error | Fix |
|---|---|
| Cannot access input devices | `sudo usermod -aG input $USER`, then re-login |
| No audio input device found | Check mic is connected, PipeWire is running |
| Cannot write to /dev/uinput | Run `setup.sh` or see the error for manual udev steps |
| Text not appearing at cursor | Text is on your clipboard — paste manually with Ctrl+V |
| No tray icon | `gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com` |
| LLM not responding | Check LM Studio is running and a model is loaded; or set `LLM_ENABLED=false` |

## License

[MIT](LICENSE)
