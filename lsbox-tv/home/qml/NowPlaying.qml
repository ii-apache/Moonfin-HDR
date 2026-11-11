// What's playing (Spotify, YouTube, Moonfin...) as a small pill at the top.
// Up from the top row focuses it: OK pauses or plays, Left/Right skip,
// hold OK opens the app.
import QtQuick

Rectangle {
    id: root
    property bool focused: false
    readonly property var np: home.nowPlaying
    readonly property real maxText: win.width * 0.34 - 190 * win.u
    visible: opacity > 0
    opacity: np.active === true ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 250 } }
    height: 76 * win.u
    width: Math.min(win.width * 0.34, row.implicitWidth + 40 * win.u)
    radius: height / 2
    color: focused ? "white" : "#a0151518"
    border.color: "#30ffffff"
    border.width: focused ? 0 : 1
    scale: focused ? 1.08 : 1
    Behavior on scale { NumberAnimation { duration: 150 } }
    Behavior on color { ColorAnimation { duration: 150 } }

    Row {
        id: row
        x: 14 * win.u
        anchors.verticalCenter: parent.verticalCenter
        spacing: 16 * win.u
        Rectangle {
            width: 52 * win.u; height: width; radius: 10 * win.u
            color: "#33ffffff"
            clip: true
            Image {
                anchors.fill: parent
                source: root.np.art || ""
                sourceSize.width: 128
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
            }
        }
        Column {
            anchors.verticalCenter: parent.verticalCenter
            Text {
                text: root.np.title || ""
                width: Math.min(implicitWidth, root.maxText)
                color: root.focused ? "#111" : "white"
                font.pixelSize: 24 * win.u; font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
            Text {
                text: root.np.artist || ""
                visible: text !== ""
                width: Math.min(implicitWidth, root.maxText)
                color: root.focused ? "#555" : "#bfffffff"
                font.pixelSize: 19 * win.u
                elide: Text.ElideRight
            }
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.np.playing ? "❚❚" : "▶"
            color: root.focused ? "#111" : "white"
            font.pixelSize: 24 * win.u
            rightPadding: 10 * win.u
        }
    }
    Rectangle {  // progress
        visible: (root.np.length || 0) > 0
        anchors.bottom: parent.bottom; anchors.bottomMargin: 7 * win.u
        x: parent.radius; width: parent.width - 2 * parent.radius; height: 3 * win.u; radius: height
        color: root.focused ? "#22000000" : "#30ffffff"
        Rectangle {
            height: parent.height; radius: height
            width: parent.width * Math.min(1, (root.np.position || 0) / Math.max(1, root.np.length || 1))
            color: root.focused ? "#111" : "white"
        }
    }
}
