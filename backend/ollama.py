#!/usr/bin/env python3
"""Optional LLM fallback for the Omarchy voice assistant.

When a voice command matches no local rule and Ollama is installed/running,
the transcript is sent to a small local model and its short answer is spoken.
If Ollama is unavailable the caller falls back to a spoken help message.
"""

import json
import shutil
import subprocess

DEFAULT_MODEL = "llama3.2:1b"


def available():
    return shutil.which("ollama") is not None


def ask(question, model=DEFAULT_MODEL, timeout=90):
    """Return a short spoken-style answer, or None on any failure."""
    if not available():
        return None
    prompt = (
        "You are a helpful voice assistant built into a Linux desktop called "
        "Omarchy. Answer the user's question in one or two short, spoken "
        "sentences. Be concise.\n\nQuestion: " + str(question)
    )
    try:
        proc = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            return None
        answer = proc.stdout.decode(errors="replace").strip()
        # Keep single-line, trim reasoning preamble some models emit.
        answer = " ".join(answer.split())
        return answer if answer else None
    except Exception:
        return None
