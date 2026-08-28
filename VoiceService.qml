import QtQuick
import Quickshell
import Quickshell.Io

// Headless service that owns the voice assistant backend process and exposes
// a "voice" IPC target. The bar widget and external keybindings (via the
// omarchy-voice CLI) both land here.
//
// The backend speaks JSON lines on stdout; we parse them and update listening
// state / surface transcripts and replies. The bar widget reflects `listening`
// and calls toggle()/say().
Item {
  id: root

  property string omarchyPath: Quickshell.env("OMARCHY_PATH")
  property var shell: null
  property var manifest: null

  readonly property string pluginDir: Quickshell.env("HOME")
    + "/.config/omarchy/plugins/azzen.voice"
  readonly property string backendScript: pluginDir + "/backend/omarchy_voice.py"
  readonly property string disabledIcon: "󰍬"
  readonly property string listeningIcon: "󰍩"

  property bool listening: false
  property string lastTranscript: ""
  property string lastReply: ""
  property bool backendRunning: backendProc.running

  // listeningChanged is auto-generated from the `listening` property; the
  // bar widget connects to it to track state.

  // ------------------------------------------------------------ backend pipe

  function send(msg) {
    if (backendProc.running) backendProc.write(JSON.stringify(msg) + "\n")
  }

  function handleLine(line) {
    var text = String(line || "").trim()
    if (text === "") return
    var obj
    try {
      obj = JSON.parse(text)
    } catch (e) {
      console.warn("voice: bad backend line", text)
      return
    }
    switch (obj.type) {
      case "state":
        root.listening = !!obj.listening
        break
      case "transcript":
        root.lastTranscript = obj.text || ""
        break
      case "reply":
        root.lastReply = obj.text || ""
        break
      case "log":
        if (obj.message) console.log("voice:", obj.message)
        break
      case "ready":
        console.log("voice: backend ready")
        break
    }
  }

  Process {
    id: backendProc
    running: true
    stdinEnabled: true
    command: [backendScript]

    environment: ({
      "OMARCHY_VOICE_DIR": Quickshell.env("HOME") + "/.config/omarchy/voice",
      "OMARCHY_VOICE_STATE": Quickshell.env("HOME") + "/.cache/omarchy/voice"
    })

    stdout: SplitParser {
      onRead: function(data) { root.handleLine(data) }
    }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: console.warn("voice backend stderr:", text)
    }

    onExited: function(code) {
      console.log("voice: backend exited", code)
    }
  }

  // ------------------------------------------------------------ public API

  function startListening() { root.send({ cmd: "start" }) }
  function stopListening() { root.send({ cmd: "stop" }) }
  function toggle() { root.send({ cmd: "toggle" }) }
  function status() { root.send({ cmd: "status" }) }
  function say(text) { root.send({ cmd: "say", text: String(text || "") }) }

  function icon() { return root.listening ? root.listeningIcon : root.disabledIcon }

  IpcHandler {
    target: "voice"

    function ping(): string { return "ok" }
    function start(): void { root.startListening() }
    function stop(): void { root.stopListening() }
    function toggle(): void { root.toggle() }
    function status(): string { return root.listening ? "listening" : "idle" }
    function say(text: string): void { root.say(text) }
  }

  Component.onCompleted: {
    root.send({ cmd: "status" })
  }
}
