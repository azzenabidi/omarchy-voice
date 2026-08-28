#!/usr/bin/env python3
"""Text-to-speech for the Omarchy voice assistant.

Uses Piper (piper-tts) to synthesize speech locally and PipeWire (pw-play)
to play it. If neither piper nor a voice model is available, degrades to a
notification so the assistant still communicates.
"""

import os
import shutil
import subprocess
import tempfile
import threading

HOME = os.path.expanduser("~")
VOICE_DIR = os.environ.get("OMARCHY_VOICE_DIR", os.path.join(HOME, ".config", "omarchy", "voice"))
MODEL_PATH = os.environ.get(
    "OMARCHY_VOICE_MODEL",
    os.path.join(HOME, ".local", "share", "piper", "voices", "en_US-lessac-medium.onnx"),
)
CONFIG_PATH = os.environ.get(
    "OMARCHY_VOICE_CONFIG",
    os.path.join(HOME, ".local", "share", "piper", "voices", "en_US-lessac-medium.onnx.json"),
)


class Speaker:
    """Synthesize and play speech, guaranteeing no overlapping utterances."""

    def __init__(self, notify=None):
        self._lock = threading.Lock()
        self._piper = shutil.which("piper") or shutil.which("piper-tts")
        self._pwplay = shutil.which("pw-play") or shutil.which("paplay")
        self.notify = notify
        self._model_ready = os.path.isfile(MODEL_PATH) and os.path.isfile(CONFIG_PATH)

    @property
    def available(self):
        return self._piper and self._pwplay and self._model_ready

    def say(self, text):
        if not text:
            return
        text = str(text).strip()
        if not text:
            return

        if not self.available:
            if self.notify:
                self.notify(text, title="Voice")
            return

        with self._lock:
            try:
                with tempfile.TemporaryDirectory() as d:
                    wav = os.path.join(d, "speech.wav")
                    synth = subprocess.run(
                        [self._piper, "--model", MODEL_PATH, "--config", CONFIG_PATH,
                         "--output_file", wav],
                        input=text.encode("utf-8"),
                        capture_output=True,
                        timeout=60,
                    )
                    if synth.returncode != 0 or not os.path.isfile(wav):
                        raise RuntimeError("piper failed: " + synth.stderr.decode(errors="replace")[-500:])
                    play = subprocess.run(
                        [self._pwplay, wav],
                        capture_output=True,
                        timeout=300,
                    )
            except Exception as e:
                if self.notify:
                    self.notify("Could not speak: " + str(e), title="Voice")
