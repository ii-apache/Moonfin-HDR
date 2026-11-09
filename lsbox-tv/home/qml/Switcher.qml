// Home pressed twice: every open app as a big card. OK opens it, Up closes it.
import QtQuick

Item {
    id: root
    property bool shown: false
    property int index: 0
    anchors.fill: parent
    visible: opacity > 0
    opacity: shown ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 200 } }

    readonly property var items: home.running
    onItemsChanged: if (index >= items.length) index = Math.max(0, items.length - 1)

    function key(e) {
        var k = e.key
        if (k === Qt.Key_Left) index = Math.max(0, index - 1)
        else if (k === Qt.Key_Right) index = Math.min(items.length - 1, index + 1)
        else if (k === Qt.Key_Up && items.length) { home.closeWindow(items[index].wid) }
        else if ((k === Qt.Key_Return || k === Qt.Key_Enter || k === Qt.Key_Select || k === Qt.Key_Space) && !e.isAutoRepeat && items.length) {
            win.overlay = ""
            home.activateWindow(items[index].wid)
        }
        else if (k === Qt.Key_Escape || k === Qt.Key_Back || k === Qt.Key_Cancel || k === Qt.Key_Backspace || k === Qt.Key_Down) win.overlay = ""
    }

    Rectangle { anchors.fill: parent; color: "#050507" }

    Text {
        x: win.margin; y: win.height * 0.12
        text: root.items.length ? "Open apps" : "No apps are open"
        color: "white"; font.pixelSize: 52 * win.u; font.weight: Font.Bold
    }
    Text {
        x: win.margin; y: win.height * 0.12 + 72 * win.u
        visible: root.items.length > 0
        text: "OK to open  ·  Up to close  ·  Back to return"
        color: "#b3ffffff"; font.pixelSize: 26 * win.u
    }

    ListView {
        id: list
        y: win.height * 0.33
        width: win.width
        height: win.height * 0.5
        orientation: ListView.Horizontal
        spacing: 50 * win.u
        leftMargin: win.margin; rightMargin: win.margin
        interactive: false
        model: root.items
        currentIndex: root.index
        highlightMoveDuration: 200
        preferredHighlightBegin: win.width / 2 - win.width * 0.14
        preferredHighlightEnd: win.width / 2 + win.width * 0.14
        highlightRangeMode: ListView.ApplyRange
        delegate: Item {
            id: card
            required property var modelData
            required property int index
            readonly property bool on: index === root.index
            width: win.width * 0.28
            height: width * 0.6
            scale: on ? 1.08 : 0.9
            opacity: on ? 1 : 0.6
            Behavior on scale { NumberAnimation { duration: 160 } }
            Tile { anchors.fill: parent; app: card.modelData; focused: false; showDot: false }
            Text {
                anchors.top: parent.bottom; anchors.topMargin: 28 * win.u
                anchors.horizontalCenter: parent.horizontalCenter
                text: card.modelData.name
                color: "white"; font.pixelSize: 30 * win.u; font.weight: Font.DemiBold
            }
        }
    }
}
