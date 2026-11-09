// A light glint that sweeps across a tile when it gets focus.
import QtQuick

Item {
    id: root
    property bool active: false
    anchors.fill: parent
    clip: true
    Rectangle {
        id: bar
        width: root.width * 0.45
        height: root.height * 3
        y: -root.height
        x: -width * 2
        rotation: 18
        opacity: root.active ? 1 : 0
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: "#00ffffff" }
            GradientStop { position: 0.5; color: "#30ffffff" }
            GradientStop { position: 1.0; color: "#00ffffff" }
        }
    }
    NumberAnimation {
        id: sweep
        target: bar; property: "x"
        from: -bar.width * 2; to: root.width + bar.width
        duration: 850
        easing.type: Easing.OutQuad
    }
    onActiveChanged: if (active) sweep.restart()
    // Top edge light on the focused tile.
    Rectangle {
        anchors.fill: parent
        opacity: root.active ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 160 } }
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#26ffffff" }
            GradientStop { position: 0.35; color: "#00ffffff" }
        }
    }
}
