// One app on the home screen.
import QtQuick
import QtQuick.Effects

Item {
    id: t
    property var app
    property bool focused: false
    property bool wiggle: false
    property bool dimmed: false
    property bool showDot: true
    z: focused ? 10 : 0
    scale: focused ? 1.15 : 1.0
    opacity: dimmed ? 0.55 : 1
    Behavior on scale { NumberAnimation { duration: 170; easing.type: Easing.OutCubic } }
    Behavior on opacity { NumberAnimation { duration: 180 } }

    Shadow { anchors.fill: art; strong: t.focused }

    Item {
        id: art
        anchors.fill: parent
        rotation: 0
        layer.enabled: true
        layer.effect: MultiEffect { maskEnabled: true; maskSource: mask; maskThresholdMin: 0.5; maskSpreadAtMin: 1.0 }

        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0.0; color: t.app ? t.app.color2 : "#444" }
                GradientStop { position: 1.0; color: t.app ? t.app.color1 : "#222" }
            }
        }
        Rectangle {  // soft light from the top left
            width: parent.width * 1.2; height: width; radius: width / 2
            x: -width * 0.45; y: -height * 0.62
            gradient: Gradient {
                GradientStop { position: 0.6; color: "#00ffffff" }
                GradientStop { position: 1.0; color: "#1affffff" }
            }
        }
        Image {
            visible: t.app && t.app.image !== ""
            anchors.fill: parent
            source: t.app ? t.app.image : ""
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
        }
        Text {  // no icon found: big first letter
            visible: (!t.app || t.app.image === "") && appIcon.implicitWidth <= 1
            anchors.centerIn: parent
            text: t.app ? t.app.name.charAt(0) : ""
            color: "white"
            font.pixelSize: parent.height * 0.5
            font.weight: Font.Bold
        }
        Image {
            id: appIcon
            visible: !t.app || t.app.image === ""
            anchors.centerIn: parent
            height: parent.height * 0.52
            width: height
            source: t.app ? "image://icon/" + encodeURIComponent(t.app.icon) : ""
            sourceSize: Qt.size(256, 256)
            smooth: true
            mipmap: true
        }
        Sheen { active: t.focused }
    }
    Rectangle { id: mask; anchors.fill: art; radius: 16 * win.u; visible: false; layer.enabled: true; color: "black" }

    SequentialAnimation on rotation {
        running: t.wiggle
        loops: Animation.Infinite
        NumberAnimation { to: -1.6; duration: 110 }
        NumberAnimation { to: 1.6; duration: 110 }
        onRunningChanged: if (!running) t.rotation = 0
    }

    Text {
        anchors.top: parent.bottom
        anchors.topMargin: 22 * win.u
        anchors.horizontalCenter: parent.horizontalCenter
        text: t.app ? t.app.name : ""
        color: "white"
        font.pixelSize: 26 * win.u
        font.weight: Font.Medium
        opacity: t.focused ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 150 } }
    }
    Rectangle {  // small dot: app is open in the background
        visible: t.showDot && t.app && t.app.running && !t.focused
        anchors.top: parent.bottom
        anchors.topMargin: 14 * win.u
        anchors.horizontalCenter: parent.horizontalCenter
        width: 8 * win.u; height: width; radius: width / 2
        color: "#ccffffff"
    }
}
