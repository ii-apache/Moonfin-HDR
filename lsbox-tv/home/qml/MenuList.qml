// A vertical list of big, remote-friendly buttons.
import QtQuick

Column {
    id: root
    property var items: []      // [{label, detail}]
    property int index: 0
    spacing: 14 * win.u
    Repeater {
        model: root.items
        Rectangle {
            required property var modelData
            required property int index
            readonly property bool on: index === root.index
            width: root.width
            height: 86 * win.u
            radius: 18 * win.u
            color: on ? "white" : "#26ffffff"
            scale: on ? 1.03 : 1
            Behavior on scale { NumberAnimation { duration: 120 } }
            Behavior on color { ColorAnimation { duration: 120 } }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                x: 30 * win.u
                width: parent.width - 60 * win.u
                Text {
                    text: modelData.label
                    color: on ? "#111" : "white"
                    font.pixelSize: 30 * win.u
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                    width: parent.width
                }
                Text {
                    visible: (modelData.detail || "") !== ""
                    text: modelData.detail || ""
                    color: on ? "#555" : "#b3ffffff"
                    font.pixelSize: 21 * win.u
                    elide: Text.ElideRight
                    width: parent.width
                }
            }
        }
    }
}
