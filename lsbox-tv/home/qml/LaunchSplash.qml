// Shown the moment an app is opened, until its window covers the screen,
// so there is never a blank pause.
import QtQuick

Rectangle {
    id: root
    property var app
    property bool shown: false
    anchors.fill: parent
    visible: opacity > 0
    opacity: shown ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: shown ? 140 : 250 } }
    gradient: Gradient {
        GradientStop { position: 0.0; color: root.app ? root.app.color2 : "#222" }
        GradientStop { position: 1.0; color: root.app ? Qt.darker(root.app.color1, 1.5) : "#000" }
    }
    Image {
        id: icon
        anchors.centerIn: parent
        width: win.height * 0.22; height: width
        source: root.app ? "image://icon/" + encodeURIComponent(root.app.icon) : ""
        sourceSize: Qt.size(256, 256)
        smooth: true
        scale: root.shown ? 1.0 : 0.6
        Behavior on scale { NumberAnimation { duration: 260; easing.type: Easing.OutBack } }
    }
    Text {
        anchors.top: icon.bottom; anchors.topMargin: 30 * win.u
        anchors.horizontalCenter: parent.horizontalCenter
        text: root.app ? root.app.name : ""
        color: "white"
        font.pixelSize: 40 * win.u
        font.weight: Font.DemiBold
    }
    Row {
        anchors.bottom: parent.bottom; anchors.bottomMargin: win.height * 0.12
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 16 * win.u
        Repeater {
            model: 3
            Rectangle {
                required property int index
                width: 12 * win.u; height: width; radius: width / 2; color: "white"
                SequentialAnimation on opacity {
                    running: root.shown; loops: Animation.Infinite
                    PauseAnimation { duration: index * 160 }
                    NumberAnimation { from: 0.25; to: 1; duration: 320 }
                    NumberAnimation { from: 1; to: 0.25; duration: 320 }
                    PauseAnimation { duration: (2 - index) * 160 }
                }
            }
        }
    }
}
