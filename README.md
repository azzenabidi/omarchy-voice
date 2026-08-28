# Omarchy Voice

Control Omarchy by voice and hear it talk back.

- **Input (STT):** Voxtype (whisper, local/offline) — `voxtype record start --output-file`
  writes your speech to a transcript file instead of typing it into a window.
- **Interpretation:** a local, offline rule engine maps what you say to Omarchy /
  system / app / plugin actions. Unmatched speech can fall back to an optional
  local Ollama model for general Q&A.
- **Output (TTS):** Piper (local neural TTS) plays a spoken reply via PipeWire.

## Triggering

- **Bar mic button:** click the mic glyph in the Omarchy bar.
- **Push-to-talk hotkey:** optional, bind `omarchy-voice start/stop` (see below).
- **CLI:** `omarchy-voice toggle|start|stop|status|say "<text>"` (symlinked into
  `~/.local/bin` by `install.sh`).

## What it understands

Say a phrase, e.g. "lock the screen", "volume up", "take a screenshot",
"set a reminder to drink water in 10 minutes", "turn on night light",
"open Spotify", or "open the emoji picker". Say "stop listening" or
"that's all" to dismiss it.

The full, human-editable rule catalog is written to
`~/.config/omarchy/voice/rules.json` on first launch. Add a rule name to
`"disabled"` to switch it off, or add your own entries under `"custom"`.

## Layout

```
~/.config/omarchy/plugins/<id>/
├── manifest.json          # kinds: service + bar-widget
├── VoiceService.qml       # headless backend manager + "voice" IPC target
├── VoiceBarWidget.qml     # bar mic button
├── backend/
│   ├── omarchy_voice.py   # main loop: control Voxtype, watch transcript,
│   │                      #   interpret, execute, speak
│   ├── rules.py           # rule engine + bundled defaults
│   ├── tts.py             # Piper TTS wrapper (overlap-safe)
│   └── ollama.py          # optional Q&A fallback
├── bin/omarchy-voice      # CLI -> shell IPC
└── install.sh             # idempotent setup (needs sudo for packages)
```

## Installation

Install the plugin from this repo:

```bash
omarchy plugin add https://github.com/azzenabidi/omarchy-voice.git --enable --section right
```

This places the bar mic button and loads the backend service. It installs only
the plugin itself — next, pull the runtime dependencies and models:

```bash
bash ~/.config/omarchy/plugins/<id>/install.sh
```

`install.sh` installs `voxtype-bin` + `piper-tts`, downloads the Piper
`en_US-lessac-medium` voice and the Voxtype whisper model, enables the Voxtype
user daemon, and reloads the shell.

### Push-to-talk keybinding

The bar mic button works out of the box. For a push-to-talk hotkey, add this to
`~/.config/hypr/bindings.lua`:

```lua
o.bind("SUPER + CTRL + F10", "Voice assistant (start)", "omarchy-voice start")
o.bind("SUPER + CTRL + F10", "Voice assistant (stop)", "omarchy-voice stop", { release = true })
```

## Uninstalling

Disable the plugin (stops the backend service and hides the bar mic button):

```bash
omarchy plugin disable <id>
```

Or fully remove it (disable + delete the plugin folder):

```bash
omarchy plugin remove <id>
```

You can also delete the CLI symlink and, optionally, the runtime config
and models that were set up by `install.sh`:

```bash
rm ~/.local/bin/omarchy-voice
rm -rf ~/.config/omarchy/voice            # rules.json and voice config
rm -rf ~/.cache/omarchy/voice             # transcripts/state
rm -rf ~/.local/share/piper/voices        # downloaded Piper voice
```

If you bound a push-to-talk hotkey, remove the `o.bind` lines for
`omarchy-voice start/stop` from `~/.config/hypr/bindings.lua`.

## Notes

- Requires the Voxtype daemon to be running (`systemctl --user status voxtype`).
- STT and TTS run entirely offline after the one-time model download.
- Configuration lives under `~/.config/omarchy/` and `~/.cache/omarchy/voice/` —
  nothing under `/usr/share/omarchy/` is modified.
