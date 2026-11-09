// Menu / X button on the home screen: TV power, apps, settings, box.
import QtQuick

Item {
    id: root
    property bool shown: false
    property int index: 0
    property bool confirmReboot: false
    anchors.fill: parent
    visible: panel.x < win.width

    readonly property var actions: {
        var a = [
            { id: "tv", label: "Turn off TV", detail: "Box stays on for AirPlay" },
            { id: "switcher", label: "Open apps", detail: home.running.length + " running" },
            { id: "closeall", label: "Close all apps", detail: "Frees memory. They start fresh next time." },
            { id: "settings", label: "Settings", detail: "Wi-Fi, Bluetooth, sound and display" }
        ]
        if (home.hidden.length)
            a.push({ id: "unhide", label: "Show hidden apps", detail: home.hidden.length + " hidden" })
        a.push({ id: "restart", label: "Restart home screen", detail: "Apps keep running" })
        a.push({ id: "reboot", label: root.confirmReboot ? "Press OK again to restart" : "Restart box",
                 detail: home.status.storage || "" })
        return a
    }

    onShownChanged: { confirmReboot = false; if (shown) index = 0 }

    function run(id) {
        switch (id) {
        case "tv": win.overlay = ""; home.tvOff(); break
        case "switcher": win.overlay = "switcher"; switcher.index = 0; break
        case "closeall": home.closeAll(); win.overlay = ""; break
        case "settings": win.overlay = ""; home.openSettings(); break
        case "unhide": home.unhideAll(); break
        case "restart": home.restartHome(); break
        case "reboot":
            if (confirmReboot) home.reboot()
            else confirmReboot = true
            break
        }
    }

    function key(e) {
        var k = e.key
        if (k === Qt.Key_Up) { index = Math.max(0, index - 1); confirmReboot = false }
        else if (k === Qt.Key_Down) { index = Math.min(actions.length - 1, index + 1); confirmReboot = false }
        else if ((k === Qt.Key_Return || k === Qt.Key_Enter || k === Qt.Key_Select || k === Qt.Key_Space) && !e.isAutoRepeat) run(actions[index].id)
        else if (k === Qt.Key_Escape || k === Qt.Key_Back || k === Qt.Key_Cancel || k === Qt.Key_Backspace || k === Qt.Key_Menu || k === Qt.Key_Left) win.overlay = ""
    }

    Rectangle {
        anchors.fill: parent
        color: "black"
        opacity: root.shown ? 0.45 : 0
        Behavior on opacity { NumberAnimation { duration: 200 } }
    }
    Rectangle {
        id: panel
        width: win.width * 0.3
        height: win.height - 2 * y
        y: 40 * win.u
        x: root.shown ? win.width - width - 40 * win.u : win.width + 20
        Behavior on x { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
        radius: 34 * win.u
        color: "#e01c1d22"
        border.color: "#22ffffff"
        border.width: 1

        Column {
            x: 36 * win.u; y: 40 * win.u
            width: parent.width - 72 * win.u
            spacing: 26 * win.u
            Column {
                spacing: 4 * win.u
                Text { id: bigTime; color: "white"; font.pixelSize: 64 * win.u; font.weight: Font.Bold }
                Text { id: date; color: "#ccffffff"; font.pixelSize: 26 * win.u }
                Timer {
                    interval: 5000; repeat: true; triggeredOnStart: true; running: root.shown
                    onTriggered: { var d = new Date(); bigTime.text = Qt.formatTime(d, "h:mm"); date.text = Qt.formatDate(d, "dddd, MMMM d") }
                }
            }
            Row {
                spacing: 12 * win.u
                Rectangle { width: 14 * win.u; height: width; radius: width / 2; anchors.verticalCenter: parent.verticalCenter
                            color: home.status.airplay === "Ready as LSBox" ? "#34c759" : "#8e8e93" }
                Text { text: "AirPlay: " + (home.status.airplay || "unknown"); color: "#e6ffffff"; font.pixelSize: 24 * win.u }
            }
            MenuList { width: parent.width; items: root.actions; index: root.index }
        }
    }
}
