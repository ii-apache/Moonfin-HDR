// Hold OK on an app: move it, hide it, or close it.
import QtQuick

Item {
    id: root
    property bool shown: false
    property var app
    property int index: 0
    anchors.fill: parent
    visible: opacity > 0
    opacity: shown ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 160 } }

    readonly property var actions: {
        var a = [{ id: "move", label: "Move", detail: "Change where it sits on the home screen" }]
        if (app && app.running) a.push({ id: "close", label: "Close " + app.name, detail: "Quit the app" })
        a.push({ id: "hide", label: "Hide from Home", detail: "Bring it back from Control Center" })
        a.push({ id: "cancel", label: "Cancel", detail: "" })
        return a
    }
    onShownChanged: if (shown) index = 0

    function key(e) {
        var k = e.key
        if (k === Qt.Key_Up) index = Math.max(0, index - 1)
        else if (k === Qt.Key_Down) index = Math.min(actions.length - 1, index + 1)
        else if ((k === Qt.Key_Return || k === Qt.Key_Enter || k === Qt.Key_Select || k === Qt.Key_Space) && !e.isAutoRepeat) {
            var id = actions[index].id
            if (id === "move") { win.overlay = "move"; return }
            win.overlay = ""
            if (id === "close") home.closeApp(app.key)
            else if (id === "hide") home.hideApp(app.key)
        }
        else if (k === Qt.Key_Escape || k === Qt.Key_Back || k === Qt.Key_Cancel || k === Qt.Key_Backspace) win.overlay = ""
    }

    Rectangle { anchors.fill: parent; color: "#b3000000" }
    Rectangle {
        anchors.centerIn: parent
        width: win.width * 0.32
        height: col.height + 80 * win.u
        radius: 34 * win.u
        color: "#f01c1d22"
        border.color: "#22ffffff"
        Column {
            id: col
            x: 40 * win.u; y: 40 * win.u
            width: parent.width - 80 * win.u
            spacing: 24 * win.u
            Text { text: root.app ? root.app.name : ""; color: "white"; font.pixelSize: 42 * win.u; font.weight: Font.Bold }
            MenuList { width: parent.width; items: root.actions; index: root.index }
        }
    }
}
