# Changelog

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