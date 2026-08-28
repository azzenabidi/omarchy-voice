#!/usr/bin/env python3
"""Omarchy voice assistant backend.

Long-running process spawned by the VoiceService QML plugin. It speaks a
tiny JSON-lines protocol over stdio with the shell:

  in :  {"cmd":"start"} | {"cmd":"stop"} | {"cmd":"toggle"}
        | {"cmd":"status"} | {"cmd":"say","text":"..."}
  out:  {"type":"state","listening":bool}
        {"type":"transcript","text":"..."}
        {"type":"reply","text":"..."}
        {"type":"log","message":"..."}

Voice capture is delegated to the Voxtype daemon with an output FILE (so the
transcription does not get typed into a window). On playback, Piper synthesizes
and PipeWire plays the spoken reply.

Command execution spawns short-lived subprocesses detached from this process
so they survive backend restarts / are not killed when this exits.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HOME = os.path.expanduser("~")
STATE_DIR = os.environ.get("OMARCHY_VOICE_STATE", os.path.join(HOME, ".cache", "omarchy", "voice"))
os.makedirs(STATE_DIR, exist_ok=True)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rules  # noqa: E402
import tts  # noqa: E402
import ollama  # noqa: E402

VOXTYPE = shutil.which("voxtype") or "voxtype"
TRANSCRIPT_FILE = os.path.join(STATE_DIR, "transcript.txt")


def emit(obj):
    try:
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()
    except Exception:
        pass


def log(message):
    emit({"type": "log", "message": str(message)})


class VoxtypeController:
    """Wrap the voxtype command-line daemon control (record start/stop)."""

    def __init__(self):
        self.listening = False
        self._lock = threading.Lock()

    @property
    def daemon_running(self):
        try:
            probe = subprocess.run(
                ["systemctl", "--user", "is-active", "voxtype"],
                capture_output=True, timeout=10,
            )
            return probe.returncode == 0 and probe.stdout.decode(errors="replace").strip() == "active"
        except Exception:
            # Fall back: poke the daemon via a no-op status query.
            try:
                subprocess.run([VOXTYPE, "status"], capture_output=True, timeout=10)
                return True
            except Exception:
                return False

    def start(self):
        with self._lock:
            if self.listening:
                return "already-listening"
            try:
                # Fresh file each time so a stale transcript is not re-read.
                if os.path.exists(TRANSCRIPT_FILE):
                    os.remove(TRANSCRIPT_FILE)
                proc = subprocess.run(
                    [VOXTYPE, "record", "start", "--file", TRANSCRIPT_FILE],
                    capture_output=True, timeout=15,
                )
                if proc.returncode != 0:
                    log("voxtype start failed: " + proc.stderr.decode(errors="replace")[-500:])
                    return "failed"
                self.listening = True
                return "started"
            except Exception as e:
                log("voxtype start exception: " + str(e))
                return "failed"

    def stop(self):
        with self._lock:
            if not self.listening:
                return "not-listening"
            try:
                proc = subprocess.run(
                    [VOXTYPE, "record", "stop"],
                    capture_output=True, timeout=300,
                )
                self.listening = False
                if proc.returncode != 0:
                    log("voxtype stop warning: " + proc.stderr.decode(errors="replace")[-500:])
                return "stopped"
            except Exception as e:
                self.listening = False
                log("voxtype stop exception: " + str(e))
                return "stopped"

    def toggle(self):
        if self.listening:
            return self.stop()
        return self.start()


def wait_for_transcript(timeout=15.0):
    """Wait until the transcript file is present and non-empty."""
    deadline = time.time() + timeout
    last = 0.0
    while time.time() < deadline:
        if os.path.exists(TRANSCRIPT_FILE):
            try:
                size = os.path.getsize(TRANSCRIPT_FILE)
            except OSError:
                size = 0
            if size > 0:
                # Ensure transcription finished writing (size stabilizes).
                if time.time() - last > 0.6:
                    with open(TRANSCRIPT_FILE, encoding="utf-8", errors="replace") as fh:
                        text = fh.read().strip()
                    if text:
                        return text
                else:
                    last = time.time()
                    time.sleep(0.2)
                    continue
            else:
                last = time.time()
        time.sleep(0.2)
    return ""


def run_command(cmd):
    """Run a shell command detached (survives this process exit)."""
    if not cmd:
        return False
    try:
        subprocess.Popen(
            cmd, shell=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except Exception as e:
        log("command execution failed: " + str(e))
        return False


def notify(text, title="Voice"):
    """Fall back to an Omarchy notification if speech is impossible."""
    send = shutil.which("omarchy-notification-send")
    if not send:
        return
    subprocess.Popen(
        [send, "-g", "󰍬", "-u", "normal", title, text],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def process_transcript(text):
    """Interpret a transcribed command, execute it, and reply out loud."""
    emit({"type": "transcript", "text": text})
    if not text:
        emit({"type": "reply", "text": ""})
        return

    text_l = text.lower()
    if "stop listening" in text_l or "that's all" in text_l:
        emit({"type": "reply", "text": "Stopped"})
        speaker.say("Stopped listening")
        return

    command, reply = rules.find_rule(text)
    if command == "__STOP__":
        emit({"type": "reply", "text": "Stopped"})
        speaker.say("Stopped listening")
        return

    if command:
        emit({"type": "log", "message": "Running: " + command})
        ok = run_command(command)
        spoken = reply or "I heard you"
        if not ok:
            spoken = "Sorry, I could not run that."
        emit({"type": "reply", "text": spoken})
        speaker.say(spoken)
        return

    # No rule matched: try an optional local LLM, else offer help.
    if ollama.available():
        answer = ollama.ask(text)
        if answer:
            emit({"type": "reply", "text": answer})
            speaker.say(answer)
            return

    help_reply = rules.help_action()[1]
    emit({"type": "reply", "text": help_reply})
    speaker.say(help_reply)


def handle(msg):
    cmd = msg.get("cmd")
    if cmd == "start":
        result = voxtype.start()
        if result == "started":
            emit({"type": "state", "listening": True})
        elif result == "failed":
            emit({"type": "state", "listening": False})
            speaker.say("I could not start listening. Is Voxtype running?")
    elif cmd == "stop":
        result = voxtype.stop()
        emit({"type": "state", "listening": False})
        if result in ("stopped", "already-stopped"):
            transcript = wait_for_transcript()
            process_transcript(transcript)
    elif cmd == "toggle":
        result = voxtype.toggle()
        if voxtype.listening:
            emit({"type": "state", "listening": True})
        else:
            emit({"type": "state", "listening": False})
            if result in ("stopped",):
                transcript = wait_for_transcript()
                process_transcript(transcript)
    elif cmd == "status":
        emit({"type": "state", "listening": voxtype.listening})
    elif cmd == "say":
        text = msg.get("text", "")
        if text:
            speaker.say(text)


def main():
    global speaker, voxtype
    rules.write_defaults()
    speaker = tts.Speaker(notify=notify)
    voxtype = VoxtypeController()
    emit({"type": "ready"})
    emit({"type": "state", "listening": False})
    if not speaker.available:
        log("Piper voice model not found at " + tts.MODEL_PATH)
    if not voxtype.daemon_running:
        log("Voxtype daemon is not running; voice capture is disabled.")

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            continue
        handle(msg)


if __name__ == "__main__":
    main()
