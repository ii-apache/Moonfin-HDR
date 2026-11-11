// "Who's watching?": pick a profile. Profiles with a PIN ask for it on a
// number pad (arrows + OK, or the number keys if the remote has them).
import QtQuick

Rectangle {
    id: root
    property bool shown: false
    property int index: 0
    property string pinFor: ""      // profile name while the PIN pad is up
    property string pin: ""
    property int padIndex: 0
    property bool wrong: false
    readonly property var list: home.profiles
    readonly property var pad: ["1", "2", "3", "4", "5", "6", "7", "8", "9", "back", "0", "cancel"]
    anchors.fill: parent
    color: theme.bgSolid
    visible: opacity > 0
    opacity: shown ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 200 } }

    function start(askPinFor) {
        pin = ""; wrong = false; padIndex = 0
        pinFor = askPinFor || ""
        if (!pinFor) {
            index = 0
            for (var i = 0; i < list.length; i++) if (list[i].active) index = i
        }
    }

    function choose(name) {
        var p = null
        for (var i = 0; i < list.length; i++) if (list[i].name === name) p = list[i]
        if (!p) return
        if (p.active) { win.overlay = ""; return }
        if (p.hasPin) { start(name); return }
        if (home.switchProfile(name, "")) win.overlay = ""
    }

    function digit(d) {
        if (pin.length >= 4) return
        wrong = false
        pin += d
        if (pin.length === 4) {
            if (home.switchProfile(pinFor, pin)) { pinFor = ""; win.overlay = "" }
            else { wrong = true; pin = ""; shake.restart() }
        }
    }

    function key(e) {
        var k = e.key
        if (k >= Qt.Key_0 && k <= Qt.Key_9 && pinFor) { digit(String(k - Qt.Key_0)); return }
        if (pinFor) {
            if (k === Qt.Key_Left) { if (padIndex % 3 > 0) padIndex-- }
            else if (k === Qt.Key_Right) { if (padIndex % 3 < 2) padIndex++ }
            else if (k === Qt.Key_Up) { if (padIndex >= 3) padIndex -= 3 }
            else if (k === Qt.Key_Down) { if (padIndex < 9) padIndex += 3 }
            else if (keys.isOk(k) && !e.isAutoRepeat) {
                var p = pad[padIndex]
                if (p === "back") pin = pin.slice(0, -1)
                else if (p === "cancel") pinFor = ""
                else digit(p)
            }
            else if (keys.isBack(k)) pinFor = ""
            return
        }
        if (k === Qt.Key_Left) index = Math.max(0, index - 1)
        else if (k === Qt.Key_Right) index = Math.min(list.length - 1, index + 1)
        else if (keys.isOk(k) && !e.isAutoRepeat) choose(list[index].name)
        else if (keys.isBack(k)) win.overlay = ""
        else return
        home.feedback()
    }

    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        y: win.height * 0.16
        text: root.pinFor ? "Enter the PIN for " + root.pinFor : "Who's watching?"
        color: theme.ink; font.pixelSize: 60 * win.u; font.weight: Font.Bold
    }

    Row {
        visible: !root.pinFor
        anchors.horizontalCenter: parent.horizontalCenter
        y: win.height * 0.36
        spacing: 70 * win.u
        Repeater {
            model: root.list
            Column {
                required property var modelData
                required property int index
                readonly property bool sel: index === root.index
                spacing: 26 * win.u
                Rectangle {
                    width: 220 * win.u; height: width; radius: width / 2
                    color: modelData.color
                    scale: parent.sel ? 1.14 : 1
                    border.color: "white"; border.width: parent.sel ? 6 * win.u : 0
                    Behavior on scale { NumberAnimation { duration: 150 } }
                    Text { anchors.centerIn: parent; text: modelData.name.charAt(0).toUpperCase(); color: "white"
                           font.pixelSize: 100 * win.u; font.weight: Font.Bold }
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: modelData.name + (modelData.hasPin ? "  🔒" : "")
                    color: parent.sel ? theme.ink : theme.inkDim
                    font.pixelSize: 32 * win.u; font.weight: Font.DemiBold
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: modelData.kids
                    text: "Kids"
                    color: theme.inkDim; font.pixelSize: 24 * win.u
                }
            }
        }
    }

    Column {
        visible: root.pinFor !== ""
        anchors.horizontalCenter: parent.horizontalCenter
        y: win.height * 0.3
        spacing: 40 * win.u
        Row {
            id: dots
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 30 * win.u
            Repeater {
                model: 4
                Rectangle {
                    required property int index
                    width: 30 * win.u; height: width; radius: width / 2
                    color: index < root.pin.length ? theme.ink : "transparent"
                    border.color: root.wrong ? "#ff453a" : theme.ink; border.width: 3 * win.u
                }
            }
            transform: Translate { id: shakeT }
            SequentialAnimation {
                id: shake
                NumberAnimation { target: shakeT; property: "x"; to: 24; duration: 50 }
                NumberAnimation { target: shakeT; property: "x"; to: -24; duration: 100 }
                NumberAnimation { target: shakeT; property: "x"; to: 0; duration: 50 }
            }
        }
        Grid {
            anchors.horizontalCenter: parent.horizontalCenter
            columns: 3
            spacing: 20 * win.u
            Repeater {
                model: root.pad
                Rectangle {
                    required property var modelData
                    required property int index
                    readonly property bool sel: index === root.padIndex
                    width: 150 * win.u; height: 100 * win.u; radius: 20 * win.u
                    color: sel ? theme.selBg : theme.rowBg
                    Text {
                        anchors.centerIn: parent
                        text: modelData === "back" ? "Delete" : modelData === "cancel" ? "Cancel" : modelData
                        color: parent.sel ? theme.selText : theme.ink
                        font.pixelSize: (modelData.length > 1 ? 26 : 44) * win.u; font.weight: Font.DemiBold
                    }
                }
            }
        }
    }
}
