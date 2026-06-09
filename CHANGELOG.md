# Changelog

## [2.2.0] - 2026-06-09

### Added
- `DEVICE` env var to select computation device (`auto`, `cpu`, `cuda`)
- `COMPUTE_TYPE` env var to control precision (`int8`, `float16`, `float32`)
- Float16 guard: if `COMPUTE_TYPE=float16` is set but no CUDA GPU is detected,
  the app warns and automatically falls back to `int8`
- `uninstall.sh` — interactive script that walks through reversing every change
  made by `setup.sh` (desktop launcher, `.venv`, udev rule, group membership, packages)
- Theme-aware SVG launcher icon — `setup.sh` now asks whether you use a dark or
  light system theme and installs the matching icon variant

### Changed
- New branch `feature/openai-whisper-rocm` available as an alternative installation
  for AMD GPUs, CPU-only machines, or users who want broader hardware compatibility —
  it replaces faster-whisper with openai-whisper + PyTorch (supports NVIDIA CUDA,
  AMD ROCm, and CPU; `setup.sh` auto-detects and installs the correct PyTorch build)
- README: added Variants section comparing both branches with a separate `git clone`
  command for each so users can pick the right one for their hardware
- About dialog now shows the transcription backend (`faster-whisper + CTranslate2`)
- `setup.sh` banner now identifies which backend variant is being installed

### Fixed
- `setup.sh` now installs `build-essential` and `python3-dev` (required to compile
  some pip packages from source)
- Corrected run command in `setup.sh` output and `.env.example` (`app.py` → `src/app.py`)
- Removed unreachable `except TimeoutError` handler in `llm.py` — `urllib` wraps
  timeouts inside `URLError`, so that branch was never executed

## [2.1.0] - 2026-03-17

### Added
- Tray menu: LLM Formatting toggle (enable/disable at runtime)
- Tray menu: LLM Mode submenu to switch between `format` and `summarize`
- Tray menu: About dialog showing app name, version, and description
- All tray menu changes are persisted to `.env` and survive restarts

### Fixed
- `.env` path now resolved from `__file__` instead of CWD, ensuring tray menu changes
  are always saved regardless of how or from where the app is launched

## [2.0.1] - 2026-03-17

### Changed
- Moved source files into `src/` directory
- Entry point is now `src/app.py` (or via the app launcher)

## [2.0.0] - 2026-03-17

### Added
- Modular architecture: `app.py` (GTK tray + orchestration), `llm.py` (LM Studio client), `whisper.py` (audio + transcription)
- Optional LLM formatting via LM Studio (OpenAI-compatible API)
- `format` mode: remove filler words, fix false starts, correct punctuation
- `summarize` mode: condense transcription to key points
- `FORMATTING` state in the tray icon state machine
- `.env.example` configuration template — all settings documented with comments
- Per-event notification toggles (`NOTIFY_ON_READY`, `NOTIFY_ON_RECORDING`, etc.)
- `NOTIFY_VERBOSE` flag for detailed error messages
- `setup.sh` auto-creates `.env` from `.env.example` on first run
- LM Studio graceful fallback — dictation always works even if LLM is unavailable

### Changed
- All hardcoded constants moved to `.env` / environment variables
- `setup.sh` step count: 6 → 7 (added `.env` bootstrap step)

### Removed
- `dictate.py` — replaced by modular architecture above

## [1.0.0] - 2026-03-09

### Added
- Initial release: local speech-to-text dictation for Linux/Wayland
- `faster-whisper` transcription (offline, no cloud)
- `evdev` global hotkey listener (Super+Shift+S)
- GTK system tray icon via AyatanaAppIndicator3
- `wl-copy` + UInput Ctrl+V paste on Wayland
- Security hardening: max recording duration, sanitized logs, audio memory clearing