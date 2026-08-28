import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "azzen.voice"

  property string state: "idle"
  property var service: null

  function serviceFor() {
    return root.bar && root.bar.shell && root.bar.shell.serviceFor
      ? root.bar.shell.serviceFor("azzen.voice")
      : null
  }

  function syncService() {
    root.service = root.serviceFor()
    root.state = root.service && root.service.listening ? "recording" : "idle"
    // Services can load after the widget; keep trying for a short window.
    if (!root.service && retryTimer.running === false) retryTimer.start()
  }

  onBarChanged: syncService()
  Component.onCompleted: syncService()

  Timer {
    id: retryTimer
    interval: 500
    repeat: true
    onTriggered: {
      if (root.serviceFor()) { root.syncService(); stop() }
    }
  }

  Connections {
    target: root.service
    function onListeningChanged() { root.state = root.service.listening ? "recording" : "idle" }
  }

  visible: true
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.state === "recording" ? "󰍩" : "󰍬"
    active: root.state === "recording"
    slotSize: Style.bar.statusSlot
    fontSize: Style.font.caption
    tooltipText: root.state === "recording"
      ? "Listening - speak your command"
      : "Voice assistant - click or hold Super+Grave to talk"
    onPressed: function() {
      if (root.service && typeof root.service.toggle === "function")
        root.service.toggle()
    }
  }
}
