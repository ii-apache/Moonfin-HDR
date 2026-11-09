// Soft drop shadow under a tile or card.
import QtQuick
import QtQuick.Effects

Item {
    id: root
    property bool strong: false
    Rectangle {
        id: src
        anchors.fill: parent
        radius: 16 * win.u
        color: "black"
        visible: false
        layer.enabled: true
    }
    MultiEffect {
        source: src
        anchors.fill: src
        anchors.topMargin: root.strong ? 26 * win.u : 8 * win.u
        anchors.bottomMargin: root.strong ? -26 * win.u : -8 * win.u
        blurEnabled: true
        blur: 1.0
        blurMax: 48
        opacity: root.strong ? 0.75 : 0.35
        Behavior on opacity { NumberAnimation { duration: 160 } }
        Behavior on anchors.topMargin { NumberAnimation { duration: 160 } }
    }
}
