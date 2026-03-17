#!/usr/bin/env python3
"""Whisper Dictation Tool — Press Super+Shift+S to dictate text at your cursor."""

__version__ = "2.0.0"

import os
import pathlib
import shutil
import signal
import subprocess
import sys
import threading
import time

import evdev
import gi
import sounddevice as sd
from dotenv import load_dotenv, set_key

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import GLib, Gtk  # noqa: E402
from gi.repository import AyatanaAppIndicator3 as appindicator  # noqa: E402

import llm
import whisper

load_dotenv()

_DOTENV_PATH = pathlib.Path(__file__).resolve().parent.parent / ".env"

# ── Configuration (from .env) ─────────────────────────────────────────────────

PASTE_DELAY_MS = int(os.getenv("PASTE_DELAY_MS", "100"))

ICON_IDLE = "microphone-sensitivity-muted-symbolic"
ICON_RECORDING = "microphone-sensitivity-high-symbolic"
ICON_PROCESSING = "emblem-synchronizing-symbolic"

# Notification toggles — each can be disabled independently via .env
NOTIFY_ON_READY        = os.getenv("NOTIFY_ON_READY",        "true").lower() == "true"
NOTIFY_ON_RECORDING    = os.getenv("NOTIFY_ON_RECORDING",    "true").lower() == "true"
NOTIFY_ON_TRANSCRIBING = os.getenv("NOTIFY_ON_TRANSCRIBING", "true").lower() == "true"
NOTIFY_ON_DONE         = os.getenv("NOTIFY_ON_DONE",         "true").lower() == "true"
NOTIFY_ON_SKIPPED      = os.getenv("NOTIFY_ON_SKIPPED",      "true").lower() == "true"
NOTIFY_VERBOSE         = os.getenv("NOTIFY_VERBOSE",         "false").lower() == "true"


# ── Notifications ─────────────────────────────────────────────────────────────

def notify(summary, body="", icon="audio-input-microphone", urgency="normal"):
    """Send a desktop notification and print to terminal."""
    print(f"[{summary}] {body}" if body else f"[{summary}]")
    args = ["notify-send", "-i", icon, "-u", urgency, summary]
    if body:
        args.append(body)
    try:
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    except FileNotFoundError:
        pass


# ── Prerequisite Checks ───────────────────────────────────────────────────────

def check_prerequisites():
    ok = True

    # Check wl-copy
    if not shutil.which("wl-copy"):
        print("ERROR: 'wl-copy' not found.")
        print("  Install with: sudo apt install wl-clipboard")
        ok = False

    # Check /dev/uinput access (needed to simulate Ctrl+V)
    if not os.access("/dev/uinput", os.W_OK):
        print("ERROR: Cannot write to /dev/uinput.")
        print("  Run setup.sh to create the udev rule, or manually:")
        print('    echo \'KERNEL=="uinput", GROUP="input", MODE="0660"\' | sudo tee /etc/udev/rules.d/80-uinput.rules')
        print("    sudo udevadm control --reload-rules && sudo udevadm trigger /dev/uinput")
        ok = False

    # Check evdev device access
    devices = evdev.list_devices()
    if not devices:
        print("ERROR: Cannot access input devices.")
        print("  Add yourself to the 'input' group:")
        print("    sudo usermod -aG input $USER")
        print("  Then log out and log back in.")
        ok = False

    # Check audio input
    try:
        sd.query_devices(kind="input")
    except sd.PortAudioError:
        print("ERROR: No audio input device found.")
        print("  Check that your microphone is connected and PipeWire is running.")
        ok = False

    if not ok:
        sys.exit(1)


# ── Text Pasting ──────────────────────────────────────────────────────────────

def paste_text(text):
    """Copy text to clipboard via wl-copy, then simulate Ctrl+V via evdev uinput."""
    try:
        # Step 1: Copy to Wayland clipboard
        subprocess.run(["wl-copy", "--", text], check=True, timeout=5)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"[ERROR] wl-copy: {e}")
        body = f"wl-copy failed: {e}" if NOTIFY_VERBOSE else "Clipboard copy failed — check terminal for details."
        notify("Error", body, urgency="critical")
        return

    # Step 2: Small delay so clipboard is ready
    time.sleep(PASTE_DELAY_MS / 1000)

    # Step 3: Simulate Ctrl+V via evdev UInput (works on all compositors)
    try:
        from evdev import ecodes
        ui = evdev.UInput()
        try:
            ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1)
            ui.write(ecodes.EV_KEY, ecodes.KEY_V, 1)
            ui.syn()
            time.sleep(0.05)
            ui.write(ecodes.EV_KEY, ecodes.KEY_V, 0)
            ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0)
            ui.syn()
        finally:
            ui.close()
    except Exception as e:
        print(f"[ERROR] Ctrl+V: {e}")
        body = f"Ctrl+V failed: {e}\nText copied to clipboard — paste manually." if NOTIFY_VERBOSE else "Paste failed — text is on clipboard, paste manually."
        notify("Error", body, urgency="critical")


# ── Transcription + LLM Orchestration ────────────────────────────────────────

def transcribe_and_paste(model, audio_data, app):
    # Reject recordings that are too short to contain speech
    if len(audio_data) < whisper.SAMPLE_RATE // 10:
        if NOTIFY_ON_SKIPPED:
            notify("Skipped", "Recording too short")
        GLib.idle_add(app.set_idle)
        return

    start = time.monotonic()
    try:
        text = whisper.transcribe_audio(model, audio_data)
    except Exception as e:
        print(f"[ERROR] Transcription: {e}")
        body = f"Transcription failed: {e}" if NOTIFY_VERBOSE else "Transcription failed — check terminal for details."
        notify("Error", body, urgency="critical")
        GLib.idle_add(app.set_idle)
        return

    elapsed = time.monotonic() - start

    if not text:
        if NOTIFY_ON_SKIPPED:
            notify("Skipped", f"No speech detected ({elapsed:.1f}s)")
        GLib.idle_add(app.set_idle)
        return

    print(f"[TRANSCRIBED] ({elapsed:.1f}s, {len(text)} chars)")

    # LLM formatting/summarization (blocking; runs in this worker thread)
    # format_with_llm() handles all exceptions internally and always returns a string
    if llm.LLM_ENABLED:
        GLib.idle_add(app.set_formatting)
    text = llm.format_with_llm(text)

    paste_text(text)
    if NOTIFY_ON_DONE:
        notify("Transcribed", f"({elapsed:.1f}s, {len(text)} chars)")
    audio_data[:] = 0
    del audio_data
    GLib.idle_add(app.set_idle)


# ── Tray Icon App ─────────────────────────────────────────────────────────────

class DictationApp:
    def __init__(self, model, keyboards):
        self.model = model
        self.keyboards = keyboards
        self.state = "IDLE"
        self.recorder = None
        self.last_trigger = 0.0
        self.pressed_keys = set()
        self.fd_to_dev = {dev.fd: dev for dev in keyboards}
        self.loop = None
        self._recording_timeout_id = None

        # Set up tray indicator
        self.indicator = appindicator.Indicator.new(
            "whisper-dictation",
            ICON_IDLE,
            appindicator.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(appindicator.IndicatorStatus.ACTIVE)

        # Build menu
        menu = Gtk.Menu()

        self.status_item = Gtk.MenuItem(label="Status: Idle")
        self.status_item.set_sensitive(False)
        menu.append(self.status_item)

        menu.append(Gtk.SeparatorMenuItem())

        # LLM toggle
        self.llm_toggle = Gtk.CheckMenuItem(label="LLM Formatting")
        self.llm_toggle.set_active(llm.LLM_ENABLED)
        self.llm_toggle.connect("toggled", self._on_llm_toggle)
        menu.append(self.llm_toggle)

        # LLM mode submenu
        self.llm_mode_item = Gtk.MenuItem(label="LLM Mode")
        mode_submenu = Gtk.Menu()
        self.llm_mode_item.set_submenu(mode_submenu)

        group = []
        for label, mode in [("Format", "format"), ("Summarize", "summarize")]:
            item = Gtk.RadioMenuItem.new_with_label(group, label)
            group = item.get_group()
            if llm.LLM_MODE == mode:
                item.set_active(True)
            item.connect("toggled", self._on_llm_mode, mode)
            mode_submenu.append(item)

        self.llm_mode_item.set_sensitive(llm.LLM_ENABLED)
        menu.append(self.llm_mode_item)

        menu.append(Gtk.SeparatorMenuItem())

        # About
        about_item = Gtk.MenuItem(label="About")
        about_item.connect("activate", self._on_about)
        menu.append(about_item)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self._on_quit)
        menu.append(quit_item)

        menu.show_all()
        self.indicator.set_menu(menu)

        # Register evdev file descriptors with GLib main loop
        for fd in self.fd_to_dev:
            GLib.io_add_watch(fd, GLib.IO_IN, self._on_evdev_event)

    def set_idle(self):
        self.state = "IDLE"
        self.indicator.set_icon_full(ICON_IDLE, "Idle")
        self.status_item.set_label("Status: Idle")

    def set_recording(self):
        self.state = "RECORDING"
        self.indicator.set_icon_full(ICON_RECORDING, "Recording")
        self.status_item.set_label("Status: Recording...")

    def set_transcribing(self):
        self.indicator.set_icon_full(ICON_IDLE, "Transcribing")
        self.status_item.set_label("Status: Transcribing...")

    def set_formatting(self):
        self.indicator.set_icon_full(ICON_PROCESSING, "Formatting")
        self.status_item.set_label("Status: Formatting...")

    def _save_env(self, key, value):
        if _DOTENV_PATH.exists():
            set_key(str(_DOTENV_PATH), key, value)

    def _on_llm_toggle(self, widget):
        llm.LLM_ENABLED = widget.get_active()
        self.llm_mode_item.set_sensitive(llm.LLM_ENABLED)
        self._save_env("LLM_ENABLED", "true" if llm.LLM_ENABLED else "false")

    def _on_llm_mode(self, widget, mode):
        if widget.get_active():
            llm.LLM_MODE = mode
            self._save_env("LLM_MODE", mode)

    def _on_about(self, _widget):
        dialog = Gtk.AboutDialog()
        dialog.set_program_name("Whisper Dictation")
        dialog.set_version(__version__)
        dialog.set_comments(
            "Speech-to-text dictation with optional LLM formatting.\n"
            "Press Super+Shift+S to start/stop recording."
        )
        dialog.run()
        dialog.destroy()

    def _on_quit(self, _widget):
        self.loop.quit()

    def _on_evdev_event(self, fd, _condition):
        dev = self.fd_to_dev.get(fd)
        if dev is None:
            return False  # remove this watch

        try:
            for event in dev.read():
                if event.type != evdev.ecodes.EV_KEY:
                    continue

                key_event = evdev.categorize(event)

                if key_event.keystate == evdev.KeyEvent.key_down:
                    self.pressed_keys.add(event.code)
                elif key_event.keystate == evdev.KeyEvent.key_up:
                    self.pressed_keys.discard(event.code)
                else:
                    continue

                if key_event.keystate != evdev.KeyEvent.key_down:
                    continue

                if not whisper.check_hotkey(self.pressed_keys):
                    continue

                # Debounce
                now = time.monotonic()
                if now - self.last_trigger < whisper.DEBOUNCE_SECONDS:
                    continue
                self.last_trigger = now

                self._toggle()

        except OSError:
            print(f"  Device disconnected: {dev.name}")
            del self.fd_to_dev[fd]
            if not self.fd_to_dev:
                notify("Error", "All keyboard devices disconnected", urgency="critical")
                self.loop.quit()
            return False  # remove this watch

        return True  # keep watching

    def _auto_stop(self):
        if self.state == "RECORDING":
            notify("Recording", "Auto-stopped (max duration reached)")
            self._toggle()
        return False  # don't repeat

    def _toggle(self):
        if self.state == "IDLE":
            try:
                self.recorder = whisper.AudioRecorder()
                self.recorder.start()
                self.set_recording()
                self._recording_timeout_id = GLib.timeout_add_seconds(
                    whisper.MAX_RECORDING_SECONDS, self._auto_stop
                )
                if NOTIFY_ON_RECORDING:
                    notify("Recording", "Speak now...")
            except sd.PortAudioError as e:
                print(f"[ERROR] Recording: {e}")
                body = f"Could not start recording: {e}" if NOTIFY_VERBOSE else "Could not start recording — check terminal for details."
                notify("Error", body, urgency="critical")
                self.recorder = None
        elif self.state == "RECORDING":
            if self._recording_timeout_id is not None:
                GLib.source_remove(self._recording_timeout_id)
                self._recording_timeout_id = None
            self.set_transcribing()
            if NOTIFY_ON_TRANSCRIBING:
                notify("Stopped", "Transcribing...")
            audio_data = self.recorder.stop()
            self.recorder = None
            self.state = "TRANSCRIBING"
            threading.Thread(
                target=transcribe_and_paste,
                args=(self.model, audio_data, self),
                daemon=True,
            ).start()

    def run(self):
        self.loop = GLib.MainLoop()
        if NOTIFY_ON_READY:
            notify("Ready", "Press Super+Shift+S to dictate")
        print("\nReady. Press Super+Shift+S to start/stop dictation.\n")
        self.loop.run()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    print("Whisper Dictation Tool")
    print("======================")
    print()

    print("Checking prerequisites... ", end="", flush=True)
    check_prerequisites()
    print("OK")

    model = whisper.load_model()

    print("Scanning keyboards...")
    keyboards = whisper.find_keyboard_devices()
    if not keyboards:
        print("ERROR: No keyboard devices found.")
        print("  sudo usermod -aG input $USER  (then re-login)")
        sys.exit(1)

    try:
        app = DictationApp(model, keyboards)
        app.run()
    except SystemExit:
        pass
    finally:
        print("\nExiting.")


if __name__ == "__main__":
    main()
