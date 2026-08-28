#!/usr/bin/env python3
"""Rule engine for the Omarchy voice assistant.

Matches a transcribed voice command against an ordered list of intents and
returns an action plan: a shell command to run plus a spoken confirmation.
Rules are split between bundled defaults (here) and a user-editable table on
disk (~/.config/omarchy/voice/rules.json) which is merged over the defaults.
"""

import json
import os
import re

HOME = os.path.expanduser("~")
VOICE_DIR = os.environ.get("OMARCHY_VOICE_DIR", os.path.join(HOME, ".config", "omarchy", "voice"))
RULES_PATH = os.path.join(VOICE_DIR, "rules.json")


# --------------------------------------------------------------------------
# Bitmask flags to let a default rule be toggled off by the user table entry
# with the same name without having to reproduce its whole command.
# --------------------------------------------------------------------------
class F:
    LISTEN = 1 << 0
    SYS = 1 << 1
    OMARCHY = 1 << 2
    APP = 1 << 3
    PLUGIN = 1 << 4
    QA = 1 << 5
    ALL = LISTEN | SYS | OMARCHY | APP | PLUGIN | QA


# --------------------------------------------------------------------------
# Bundled default rules.
#
# Each rule: { name, words, flags, run (callable or "command"), reply }
#   - words: list of phrases any of which (case-insensitive, substring) trigger.
#   - run:   a shell command string, OR a callable(text, args) -> (cmd, reply).
#   - reply: spoken confirmation (overridable by returning one from run()).
#   - args:  named capture groups optionally extracted in run().
# --------------------------------------------------------------------------
DEFAULT_RULES = []


def R(name, words, command, reply, flags=F.ALL, args=None, dynamic=None):
    DEFAULT_RULES.append({
        "name": name,
        "words": words,
        "command": command,
        "reply": reply,
        "flags": flags,
        "args": args or {},
        "dynamic": dynamic,
    })


# --- system state ----------------------------------------------------------
R("volume-up", ["volume up", "turn it up", "louder", "raise the volume"],
  "pactl set-sink-volume @DEFAULT_SINK@ +5%", "Turning the volume up", F.SYS)
R("volume-down", ["volume down", "turn it down", "softer", "lower the volume"],
  "pactl set-sink-volume @DEFAULT_SINK@ -5%", "Turning the volume down", F.SYS)
R("volume-mute", ["mute audio", "mute the volume", "mute my volume", "turn off the sound"],
  "pactl set-sink-mute @DEFAULT_SINK@ toggle", "Muting the audio", F.SYS)
R("volume-max", ["full volume", "max volume", "loudest"],
  "pactl set-sink-volume @DEFAULT_SINK@ 100%", "Setting volume to maximum", F.SYS)
R("brightness-up", ["brightness up", "brighten", "brighter"],
  "omarchy-brightness-display +5", "Increasing the brightness", F.SYS)
R("brightness-down", ["brightness down", "dim the screen", "dimmer"],
  "omarchy-brightness-display -5", "Decreasing the brightness", F.SYS)
R("nightlight-on", ["night light on", "enable night light", "turn on night light"],
  "hyprctl dispatch exec omarchy-toggle-nightlight", "Turning on the night light", F.SYS)
R("nightlight-off", ["night light off", "disable night light", "turn off night light"],
  "hyprctl dispatch exec omarchy-toggle-nightlight", "Turning off the night light", F.SYS)
R("dnd-on", ["do not disturb", "turn on do not disturb", "d n d on", "silence notifications"],
  "omarchy-toggle-dnd", "Turning on do not disturb", F.SYS)
R("lock", ["lock the screen", "lock screen", "lock my computer", "screen lock"],
  "omarchy system lock", "Locking the screen", F.SYS)
R("suspend", ["suspend", "go to sleep", "put the computer to sleep"],
  "systemctl suspend", "Suspending the computer", F.SYS)

# --- omarchy commands ------------------------------------------------------
R("screenshot", ["take a screenshot", "grab a screenshot", "screenshot"],
  "omarchy capture screenshot", "Taking a screenshot", F.OMARCHY)
R("screenrecord", ["start recording", "record the screen", "screen recording"],
  "omarchy screenrecord --fullscreen", "Starting a screen recording", F.OMARCHY)
R("open-menu", ["open the menu", "open menu", "show the launcher", "open launcher"],
  "omarchy-menu-toggle", "Opening the menu", F.OMARCHY)
R("restart-shell", ["restart the shell", "restart the bar", "reload the shell"],
  "omarchy restart shell", "Restarting the shell", F.OMARCHY)
R("theme-dark", ["dark theme", "set theme to dark", "switch to dark"],
  "omarchy theme set dark", "Switching to the dark theme", F.OMARCHY)
R("theme-light", ["light theme", "set theme to light", "switch to light"],
  "omarchy theme set light", "Switching to the light theme", F.OMARCHY)

# reminder: dynamic (extract number + message)
R("reminder", ["remind me", "set a reminder", "reminder"],
  None, "Setting a reminder", F.OMARCHY,
  dynamic=lambda text, args: reminder_action(text))

# --- apps ------------------------------------------------------------------
def app_action(text):
    apps = [
        ("firefox", "firefox", "Firefox"), ("browser", "firefox", "Firefox"),
        ("neovim", "alacritty -e nvim", "Neovim"), ("nvim", "alacritty -e nvim", "Neovim"),
        ("terminal", "alacritty", "terminal"),
        ("spotify", "spotify", "Spotify"), ("vlc", "vlc", "VLC"),
        ("obsidian", "obsidian", "Obsidian"),
        ("file manager", "thunar", "file manager"), ("files", "thunar", "file manager"),
        ("discord", "discord", "Discord"), ("slack", "slack", "Slack"),
        ("settings panel", "omarchy-settings", "settings"), ("settings", "omarchy-settings", "settings"),
        ("code", "code", "VS Code"), ("calculator", "gnome-calculator", "calculator"),
    ]
    for key, cmd, display in apps:
        # Match at a word boundary so "vscode" doesn't trip "code" etc.
        if re.search(r"(^|\s)" + re.escape(key) + r"(\s|$)", text.strip()):
            return cmd, "Opening " + display
    return None

R("app", ["open the", "open ", "launch ", "start "],
  None, None, F.APP, dynamic=lambda text, args: app_action(text))

# --- shell plugins (overlays/panels toggled via shell IPC) -----------------
def plugin_action(text):
    plugins = [
        ("omarchy.emojis", ["emoji", "emojis"]),
        ("omarchy.clipboard", ["clipboard"]),
        ("omarchy.image-picker", ["image picker"]),
    ]
    for pid, keys in plugins:
        for key in keys:
            if key in text:
                return f"omarchy-shell shell toggle {pid}", f"Opening the {pid.split('.')[-1].replace('-', ' ')} picker"
    return None

R("plugin", ["show the emoji", "open the emoji", "open clipboard",
             "show clipboard", "image picker", "open the menu"],
  None, None, F.PLUGIN, dynamic=lambda text, args: plugin_action(text))

# --- listen / assistant control --------------------------------------------
R("stop-listening", ["stop listening", "that's all", "never mind", "cancel"],
  "__STOP__", "Stopping", F.LISTEN)
R("help", ["what can you do", "help", "what do you control", "commands"],
  None, None, F.QA, dynamic=lambda text, args: help_action())


# --------------------------------------------------------------------------
# dynamic action builders
# --------------------------------------------------------------------------
def reminder_action(text):
    m = re.search(r"(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|s|m|h)?", text)
    if not m:
        return None
    amount = int(m.group(1))
    unit = (m.group(2) or "minutes").lower()
    scale = {"seconds": 1, "second": 1, "sec": 1, "secs": 1, "s": 1,
             "minute": 60, "minutes": 60, "min": 60, "mins": 60, "m": 60,
             "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600, "h": 3600}
    minutes = amount * scale.get(unit, 60) // 60
    # Message is the words between the reminder trigger and the duration.
    mildly = re.search(r"(remind me to|remind me|set a reminder|set an? reminder|reminder)\s+(to\s+)?", text)
    message = ""
    if mildly:
        after = text[mildly.end():]
        # Strip the trailing duration clause (e.g. "in 10 minutes" / "for 5 m").
        chop = re.search(
            r"(?:in|for|after|about\s+)?\d+\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|s|m|h)?\s*(?:from now|from)?\s*$",
            after)
        if chop and chop.start() > 0:
            after = after[:chop.start()]
        message = after.strip().strip(".,!?;:")
        # Fall back to anything before "in X" if the above left junk.
        message = re.sub(r"\s+(?:in|for|after)\s*$", "", message).strip()
        if len(message) < 3:
            message = ""
    cmd = f"omarchy reminder {minutes} \"{message}\"" if message else f"omarchy reminder {minutes} Voice reminder"
    reply = f"Reminder set for {amount} {unit}" + (f" to {message}" if message else "")
    return cmd, reply


def help_action():
    return None, "I can control system volume, brightness, night light, do not disturb, and lock screen. I can take screenshots, set reminders, open applications, and open plugins like the emoji picker. Say stop listening to turn me off."


# --------------------------------------------------------------------------
# matching
# --------------------------------------------------------------------------
def matches_rule(rule, text):
    words = rule.get("words") or []
    for word in words:
        if word in text:
            return True
    return False


def find_rule(text):
    """Return (command, reply) for the first matching rule, or (None, None)."""
    lower = text.lower()
    text_l = " " + lower + " "
    clean = lower.strip()
    enabled = load_enabled_flags()
    for rule in DEFAULT_RULES:
        if not (rule["flags"] & enabled):
            continue
        if not matches_rule(rule, text_l):
            continue
        if rule.get("dynamic"):
            result = rule["dynamic"](clean, rule["args"])
            if result is None:
                continue
            if isinstance(result, tuple):
                return result
            return result, rule["reply"]
        return rule["command"], rule["reply"]
    return None, None


# --------------------------------------------------------------------------
# user overrides on disk
# --------------------------------------------------------------------------
def load_enabled_flags():
    flags = F.ALL
    try:
        with open(RULES_PATH) as fh:
            data = json.load(fh)
    except Exception:
        return flags
    disabled = data.get("disabled", [])
    for name in disabled:
        for rule in DEFAULT_RULES:
            if rule["name"] == name:
                flags &= ~rule["flags"]
    # Re-enable anything explicitly enabled.
    for name in data.get("enabled", []):
        for rule in DEFAULT_RULES:
            if rule["name"] == name:
                flags |= rule["flags"]
    return flags


def write_defaults():
    """Write a human-editable copy of the rule catalog (without dynamic fns)."""
    summary = []
    for rule in DEFAULT_RULES:
        summary.append({
            "name": rule["name"],
            "words": rule["words"],
            "reply": rule["reply"],
            "flags": rule["flags"],
            "dynamic": rule.get("dynamic") is not None,
        })
    payload = {
        "_comment": "Edit this file to tune the voice assistant. "
                    "Add rule names to 'disabled' to turn them off, or roll "
                    "your own in 'custom' (name/words/command/reply).",
        "disabled": [],
        "enabled": [],
        "custom": [],
    }
    payload["catalog"] = summary
    try:
        os.makedirs(os.path.dirname(RULES_PATH), exist_ok=True)
        with open(RULES_PATH, "w") as fh:
            json.dump(payload, fh, indent=2)
    except Exception:
        pass
    return payload


if __name__ == "__main__":
    write_defaults()
    print("rules.json written to", RULES_PATH)
