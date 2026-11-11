// A vertical list of big, remote-friendly buttons. Scrolls when it is long.
// Items: {label, detail, value?, on?} - value shows on the right, on = a tick.
import QtQuick

ListView {
    id: root
    property var items: []
    property int index: 0
    property real maxHeight: 7 * (rowH + spacing)
    readonly property int rows: Math.max(1, Math.floor((maxHeight + spacing) / (rowH + spacing)))
    readonly property real rowH: 86 * win.u
    spacing: 14 * win.u
    height: Math.min(items.length, rows) * (rowH + spacing) - spacing
    interactive: false
    clip: true
    model: items
    currentIndex: index
    // Scroll by whole rows so no button is ever cut in half.
    property int first: 0
    onIndexChanged: {
        if (index < first) first = index
        else if (index >= first + rows) first = index - rows + 1
    }
    onItemsChanged: if (first > Math.max(0, items.length - rows)) first = Math.max(0, items.length - rows)
    contentY: first * (rowH + spacing)
    Behavior on contentY { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
    delegate: Rectangle {
        required property var modelData
        required property int index
        readonly property bool sel: index === root.index
        width: root.width
        height: root.rowH
        radius: 18 * win.u
        color: sel ? theme.selBg : theme.rowBg
        Behavior on color { ColorAnimation { duration: 120 } }
        Column {
            anchors.verticalCenter: parent.verticalCenter
            x: 30 * win.u
            width: parent.width - 60 * win.u - valueText.width
            Text {
                text: modelData.label
                color: sel ? theme.selText : theme.panelText
                font.pixelSize: 30 * win.u
                font.weight: Font.DemiBold
                elide: Text.ElideRight
                width: parent.width
            }
            Text {
                visible: (modelData.detail || "") !== ""
                text: modelData.detail || ""
                color: sel ? theme.selDim : theme.panelDim
                font.pixelSize: 21 * win.u
                elide: Text.ElideRight
                width: parent.width
            }
        }
        Text {
            id: valueText
            anchors.right: parent.right; anchors.rightMargin: 30 * win.u
            anchors.verticalCenter: parent.verticalCenter
            text: modelData.on === true ? "✓" : (modelData.value !== undefined ? String(modelData.value) : "")
            color: sel ? theme.selText : theme.panelText
            font.pixelSize: 28 * win.u
            font.weight: Font.DemiBold
        }
    }
}
