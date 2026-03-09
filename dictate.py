#!/usr/bin/env python3
"""Whisper Dictation Tool — Press Super+Shift+S to dictate text at your cursor."""

import os
import shutil
import signal
import subprocess
import sys
import threading
import time

import evdev
import gi
import numpy as np
import sounddevice as sd
from evdev import ecodes
from faster_whisper import WhisperModel

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import GLib, Gtk  # noqa: E402
from gi.repository import AyatanaAppIndicator3 as appindicator  # noqa: E402

# ── Configuration ────────────────────────────────────────────────────────────

# Available models (speed vs accuracy tradeoff):
#   "tiny"     ~75MB,  fastest,       least accurate
#   "base"     ~150MB, fast,          good for clear speech
#   "small"    ~500MB, moderate,      better accuracy
#   "medium"   ~1.5GB, slower,        high accuracy
#   "large-v3" ~3GB,   slowest,       best accuracy
MODEL_SIZE = "small"
COMPUTE_TYPE = "int8"
LANGUAGE = "en"
SAMPLE_RATE = 16000
CHANNELS = 1
PASTE_DELAY_MS = 100  # delay between wl-copy and Ctrl+V keystroke
MAX_RECORDING_SECONDS = 300  # auto-stop after 5 minutes to prevent unbounded memory use

# Hotkey: Super + Shift + S  (change these to customize)
HOTKEY_SUPER = {ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA}
HOTKEY_SHIFT = {ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT}
HOTKEY_KEY = ecodes.KEY_S
DEBOUNCE_SECONDS = 0.5

ICON_IDLE = "microphone-sensitivity-muted-symbolic"
ICON_RECORDING = "microphone-sensitivity-high-symbolic"


# ── Notifications ────────────────────────────────────────────────────────────

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


# ── Prerequisite Checks ─────────────────────────────────────────────────────

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


# ── Whisper Model ────────────────────────────────────────────────────────────

def load_model():
    print(f"Loading Whisper model ({MODEL_SIZE})... ", end="", flush=True)
    start = time.monotonic()
    model = WhisperModel(MODEL_SIZE, device="cpu", compute_type=COMPUTE_TYPE)
    elapsed = time.monotonic() - start
    print(f"done ({elapsed:.1f}s)")
    return model


# ── Keyboard Discovery ───────────────────────────────────────────────────────

def find_keyboard_devices():
    keyboards = []
    for path in evdev.list_devices():
        dev = evdev.InputDevice(path)
        caps = dev.capabilities(verbose=False)
        if ecodes.EV_KEY in caps:
            key_codes = caps[ecodes.EV_KEY]
            if ecodes.KEY_A in key_codes and ecodes.KEY_Z in key_codes:
                keyboards.append(dev)
                print(f"  Found keyboard: {dev.name} ({dev.path})")
    return keyboards


# ── Audio Recorder ───────────────────────────────────────────────────────────

class AudioRecorder:
    def __init__(self):
        self.chunks = []
        self.stream = None

    def _callback(self, indata, _frames, _time_info, status):
        if status:
            print(f"  Audio warning: {status}")
        self.chunks.append(indata.copy())

    def start(self):
        self.chunks = []
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            callback=self._callback,
            blocksize=1024,
        )
        self.stream.start()

    def stop(self):
        self.stream.stop()
        self.stream.close()
        self.stream = None
        if not self.chunks:
            return np.array([], dtype="float32")
        audio = np.concatenate(self.chunks, axis=0)
        self.chunks.clear()
        return audio.flatten()


# ── Text Pasting ─────────────────────────────────────────────────────────────

def paste_text(text):
    """Copy text to clipboard via wl-copy, then simulate Ctrl+V via evdev uinput."""
    try:
        # Step 1: Copy to Wayland clipboard
        subprocess.run(["wl-copy", "--", text], check=True, timeout=5)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        notify("Error", f"wl-copy failed: {e}", urgency="critical")
        return

    # Step 2: Small delay so clipboard is ready
    time.sleep(PASTE_DELAY_MS / 1000)

    # Step 3: Simulate Ctrl+V via evdev UInput (works on all compositors)
    try:
        ui = evdev.UInput()
        ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1)
        ui.write(ecodes.EV_KEY, ecodes.KEY_V, 1)
        ui.syn()
        time.sleep(0.05)
        ui.write(ecodes.EV_KEY, ecodes.KEY_V, 0)
        ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0)
        ui.syn()
        ui.close()
    except Exception as e:
        notify("Error", f"Ctrl+V failed: {e}\nText copied to clipboard — paste manually.", urgency="critical")


# ── Transcription ────────────────────────────────────────────────────────────

def transcribe_and_paste(model, audio_data, app):
    if len(audio_data) < SAMPLE_RATE // 10:  # less than 0.1s
        notify("Skipped", "Recording too short")
        GLib.idle_add(app.set_idle)
        return

    start = time.monotonic()
    try:
        segments, _info = model.transcribe(
            audio_data,
            language=LANGUAGE,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
    except Exception as e:
        notify("Error", f"Transcription failed: {e}", urgency="critical")
        GLib.idle_add(app.set_idle)
        return

    elapsed = time.monotonic() - start

    if not text:
        notify("Skipped", f"No speech detected ({elapsed:.1f}s)")
        GLib.idle_add(app.set_idle)
        return

    print(f"[TRANSCRIBED] ({elapsed:.1f}s, {len(text)} chars)")
    paste_text(text)
    notify("Transcribed", f"({elapsed:.1f}s, {len(text)} chars)")
    audio_data[:] = 0
    del audio_data
    GLib.idle_add(app.set_idle)


# ── Hotkey Detection ─────────────────────────────────────────────────────────

def check_hotkey(pressed):
    has_super = bool(pressed & HOTKEY_SUPER)
    has_shift = bool(pressed & HOTKEY_SHIFT)
    has_key = HOTKEY_KEY in pressed
    return has_super and has_shift and has_key


# ── Tray Icon App ───────────────────────────────────────────────────────────

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

    def _on_quit(self, _widget):
        self.loop.quit()

    def _on_evdev_event(self, fd, _condition):
        dev = self.fd_to_dev.get(fd)
        if dev is None:
            return False  # remove this watch

        try:
            for event in dev.read():
                if event.type != ecodes.EV_KEY:
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

                if not check_hotkey(self.pressed_keys):
                    continue

                # Debounce
                now = time.monotonic()
                if now - self.last_trigger < DEBOUNCE_SECONDS:
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
                self.recorder = AudioRecorder()
                self.recorder.start()
                self.set_recording()
                self._recording_timeout_id = GLib.timeout_add_seconds(
                    MAX_RECORDING_SECONDS, self._auto_stop
                )
                notify("Recording", "Speak now...")
            except sd.PortAudioError as e:
                notify("Error", f"Could not start recording: {e}", urgency="critical")
                self.recorder = None
        elif self.state == "RECORDING":
            if self._recording_timeout_id is not None:
                GLib.source_remove(self._recording_timeout_id)
                self._recording_timeout_id = None
            self.set_transcribing()
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
        notify("Ready", "Press Super+Shift+S to dictate")
        print("\nReady. Press Super+Shift+S to start/stop dictation.\n")
        self.loop.run()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    print("Whisper Dictation Tool")
    print("======================")
    print()

    print("Checking prerequisites... ", end="", flush=True)
    check_prerequisites()
    print("OK")

    model = load_model()

    print("Scanning keyboards...")
    keyboards = find_keyboard_devices()
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
