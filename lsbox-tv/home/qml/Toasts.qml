// Banners (notifications, AirPlay, low controller battery, new in Jellyfin)
// and the volume bar. Shown on the home screen itself, or in the small
// overlay window above apps.
import QtQuick

Item {
    id: root
    property bool active: true          // this copy is the one that shows things
    property var queue: []
    property var current: null
    property bool volumeOn: false
    readonly property bool busy: current !== null || volumeOn
    readonly property real u: win.u

    function push(title, body, icon) {
        var q = queue.slice()
        q.push({ title: title, body: body, icon: icon })
        queue = q.slice(-4)
        if (!current) next()
    }
    function next() {
        if (!queue.length) { current = null; return }
        current = queue[0]
        queue = queue.slice(1)
        bannerTimer.restart()
    }

    Connections {
        target: home
        function onBanner(title, body, icon) { if (root.active) root.push(title, body, icon) }
        function onVolumeShown() { if (root.active) { root.volumeOn = true; volTimer.restart() } }
    }
    Timer { id: bannerTimer; interval: 5000; onTriggered: root.next() }
    Timer { id: volTimer; interval: 2200; onTriggered: root.volumeOn = false }

    Rectangle {
        id: banner
        anchors.right: parent.right; anchors.rightMargin: 40 * root.u
        y: root.current ? 40 * root.u : -height - 20
        Behavior on y { NumberAnimation { duration: 280; easing.type: Easing.OutCubic } }
        width: Math.min(parent.width - 80 * root.u, 620 * root.u)
        height: col.implicitHeight + 44 * root.u
        radius: 26 * root.u
        color: "#ee1c1d22"
        border.color: "#26ffffff"
        Row {
            x: 26 * root.u
            anchors.verticalCenter: parent.verticalCenter
            spacing: 20 * root.u
            Image {
                visible: status === Image.Ready && root.current && (root.current.icon || "") !== ""
                source: root.current && root.current.icon ? (root.current.icon.indexOf("/") === 0 || root.current.icon.indexOf("file:") === 0
                        ? root.current.icon : "image://icon/" + encodeURIComponent(root.current.icon)) : ""
                width: 56 * root.u; height: width
                sourceSize: Qt.size(112, 112)
                anchors.verticalCenter: parent.verticalCenter
            }
            Column {
                id: col
                width: banner.width - 130 * root.u
                spacing: 4 * root.u
                Text { width: parent.width; text: root.current ? root.current.title : ""; color: "white"
                       font.pixelSize: 27 * root.u; font.weight: Font.DemiBold; elide: Text.ElideRight }
                Text { width: parent.width; text: root.current ? root.current.body : ""; visible: text !== ""
                       color: "#ccffffff"; font.pixelSize: 23 * root.u; wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight }
            }
        }
    }

    Rectangle {
        id: vol
        anchors.horizontalCenter: parent.horizontalCenter
        y: root.volumeOn ? (root.current ? banner.y + banner.height + 20 * root.u : 40 * root.u) : -height - 20
        Behavior on y { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
        width: 460 * root.u; height: 70 * root.u; radius: height / 2
        color: "#ee1c1d22"
        border.color: "#26ffffff"
        Text {
            id: volIcon
            x: 26 * root.u; anchors.verticalCenter: parent.verticalCenter
            text: home.volume.muted || home.volume.level === 0 ? "🔇" : "🔊"
            color: "white"; font.pixelSize: 28 * root.u
        }
        Rectangle {
            anchors.left: volIcon.right; anchors.leftMargin: 20 * root.u
            anchors.right: volText.left; anchors.rightMargin: 20 * root.u
            anchors.verticalCenter: parent.verticalCenter
            height: 10 * root.u; radius: height / 2
            color: "#40ffffff"
            Rectangle {
                height: parent.height; radius: parent.radius
                width: parent.width * Math.max(0, Math.min(1, (home.volume.muted ? 0 : home.volume.level) / 100))
                color: "white"
                Behavior on width { NumberAnimation { duration: 120 } }
            }
        }
        Text {
            id: volText
            anchors.right: parent.right; anchors.rightMargin: 28 * root.u
            anchors.verticalCenter: parent.verticalCenter
            text: home.volume.level < 0 ? (home.volume.mode === "cec" ? "TV" : "") : (home.volume.muted ? "Muted" : home.volume.level)
            color: "white"; font.pixelSize: 26 * root.u; font.weight: Font.DemiBold
        }
    }
}
