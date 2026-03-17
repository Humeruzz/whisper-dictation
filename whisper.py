"""Audio recording, Whisper transcription, and hotkey utilities."""

import os
import time

import evdev
import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
from evdev import ecodes
from faster_whisper import WhisperModel

load_dotenv()

# ── Configuration (from .env) ─────────────────────────────────────────────────

MODEL_SIZE = os.getenv("MODEL_SIZE", "small")
COMPUTE_TYPE = os.getenv("COMPUTE_TYPE", "int8")
LANGUAGE = os.getenv("WHISPER_LANGUAGE", "en") or None  # empty string → None = auto-detect
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))
CHANNELS = int(os.getenv("CHANNELS", "1"))
MAX_RECORDING_SECONDS = int(os.getenv("MAX_RECORDING_SECONDS", "300"))
DEBOUNCE_SECONDS = float(os.getenv("DEBOUNCE_SECONDS", "0.5"))

# Hotkey: Super + Shift + S — edit these constants to customize the trigger
HOTKEY_SUPER = {ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA}
HOTKEY_SHIFT = {ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT}
HOTKEY_KEY = ecodes.KEY_S


# ── Whisper Model ─────────────────────────────────────────────────────────────

def load_model():
    print(f"Loading Whisper model ({MODEL_SIZE})... ", end="", flush=True)
    start = time.monotonic()
    model = WhisperModel(MODEL_SIZE, device="cpu", compute_type=COMPUTE_TYPE)
    elapsed = time.monotonic() - start
    print(f"done ({elapsed:.1f}s)")
    return model


# ── Keyboard Discovery ────────────────────────────────────────────────────────

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


# ── Hotkey Detection ──────────────────────────────────────────────────────────

def check_hotkey(pressed):
    has_super = bool(pressed & HOTKEY_SUPER)
    has_shift = bool(pressed & HOTKEY_SHIFT)
    has_key = HOTKEY_KEY in pressed
    return has_super and has_shift and has_key


# ── Audio Recorder ────────────────────────────────────────────────────────────

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


# ── Transcription ─────────────────────────────────────────────────────────────

def transcribe_audio(model, audio_data):
    """Transcribe audio with Whisper. Returns the text string (may be empty). Raises on failure."""
    segments, _info = model.transcribe(
        audio_data,
        language=LANGUAGE,
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )
    return " ".join(seg.text.strip() for seg in segments).strip()
