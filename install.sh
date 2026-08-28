#!/bin/bash
# Installer for the Omarchy Voice assistant plugin (azzen.voice).
#
# This script needs sudo for package installation. Run it when you want to
# pull in voxtype-bin + piper-tts and download the models:
#
#   bash ~/.config/omarchy/plugins/azzen.voice/install.sh
#
# It is idempotent: safe to re-run.
set -euo pipefail

VOICE_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ID="azzen.voice"
HOME_DIR="$HOME"
CONFIG_DIR="$HOME_DIR/.config/omarchy/plugins/$PLUGIN_ID"

PIPER_VOICES_DIR="$HOME_DIR/.local/share/piper/voices"
PIPER_MODEL="$PIPER_VOICES_DIR/en_US-lessac-medium.onnx"
PIPER_CONFIG="$PIPER_VOICES_DIR/en_US-lessac-medium.onnx.json"

github_voice() {
  # Piper 1.x voice download helper.
  local file="$1" out="$2"
  local url="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/$file"
  curl -L --fail --retry 3 -o "$out" "$url"
}

ensure_models() {
  echo ">> Ensuring Piper voice model..."
  mkdir -p "$PIPER_VOICES_DIR"
  if [[ ! -f "$PIPER_MODEL" ]]; then
    github_voice "en_US-lessac-medium.onnx" "$PIPER_MODEL"
  fi
  if [[ ! -f "$PIPER_CONFIG" ]]; then
    github_voice "en_US-lessac-medium.onnx.json" "$PIPER_CONFIG"
  fi
  echo "   Piper voice model ready."
}

main() {
  echo "== Omarchy Voice plugin installer =="

  # 1. Packages (needs sudo).
  echo ">> Installing voxtype-bin (Omarchy/Arch repo)..."
  sudo pacman -S --noconfirm --needed voxtype-bin
  echo ">> Installing piper-tts (AUR)..."
  if ! command -v paru >/dev/null 2>&1; then
    echo "   paru (AUR helper) not found; installing piper-tts via omarchy pkg"
    omarchy pkg aur add piper-tts --yes || true
  else
    paru -S --noconfirm --needed piper-tts
  fi

  ensure_models

  # 2. Voxtype setup: download whisper model + enable user daemon.
  echo ">> Configuring Voxtype (whisper model + daemon)..."
  if ! command -v voxtype >/dev/null 2>&1; then
    echo "   voxtype not on PATH after install; skipping model/daemon setup."
  else
    voxtype setup --download || true
    voxtype setup systemd || true
    systemctl --user enable --now voxtype 2>/dev/null || true
  fi

  # 3. Make the CLI available on PATH.
  if [[ -d "$HOME_DIR/.local/bin" ]]; then
    ln -sf "$CONFIG_DIR/bin/omarchy-voice" "$HOME_DIR/.local/bin/omarchy-voice" 2>/dev/null || true
  fi

  # 4. Enable the plugin (places the bar button; also loads the service).
  echo ">> Enabling plugin $PLUGIN_ID..."
  omarchy plugin enable "$PLUGIN_ID" --section right 2>/dev/null \
    || omarchy plugin enable "$PLUGIN_ID" --yes 2>/dev/null \
    || true

  # 5. Apply shell + hypr reloads.
  omarchy-shell shell rescanPlugins 2>/dev/null || true
  omarchy restart shell 2>/dev/null || true
  hyprctl reload >/dev/null 2>&1 || true

  echo
  echo "== Done. =="
  echo "Voice assistant enabled."
  echo "  - Push-to-talk: hold Super+Grave to talk, release to stop (bound in"
  echo "    ~/.config/hypr/bindings.lua)"
  echo "  - Or click the mic button in the bar."
  echo "  - Test: omarchy-voice say 'Hello from Omarchy'"
}

main "$@"
