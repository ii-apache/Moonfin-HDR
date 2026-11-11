// After a few idle minutes on Home: slow pans across artwork from your
// own Jellyfin library (no internet services). Any button wakes it.
import QtQuick

Rectangle {
    id: root
    property bool shown: false
    property var items: []
    property int idx: 0
    property bool flip: false
    anchors.fill: parent
    color: "black"
    visible: opacity > 0
    opacity: shown ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 1200 } }

    function next() {
        if (!items.length) return
        idx = (idx + 1) % items.length
        var layer = flip ? a : b
        layer.show(items[idx])
        flip = !flip
    }
    onShownChanged: if (shown) { idx = Math.floor(Math.random() * Math.max(1, items.length)); next() }
    Timer { interval: 12000; repeat: true; running: root.shown && !root.music; onTriggered: root.next() }

    // Music playing (Spotify etc.): show the album instead of the library.
    readonly property bool music: home.nowPlaying.active === true && home.nowPlaying.video !== true && (home.nowPlaying.art || "") !== ""

    // Left on the screensaver a long time: turn the TV off over CEC.
    Timer {
        interval: 60000 * Math.max(1, home.settings.saverTvOffMinutes || 0)
        running: root.shown && (home.settings.saverTvOffMinutes || 0) > 0 && !(home.nowPlaying.playing === true)
        onTriggered: home.tvOff()
    }

    component Pan: Item {
        id: p
        property var item: null
        property bool live: false
        anchors.fill: parent
        opacity: live ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 2000 } }
        function show(it) { item = it; img.source = it.backdrop; live = true; (p === a ? b : a).live = false; zoom.restart() }
        Image {
            id: img
            width: parent.width * 1.12; height: parent.height * 1.12
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            sourceSize.width: 1920
            NumberAnimation on x { id: zoom; from: 0; to: -root.width * 0.1; duration: 14000; running: false }
        }
        Rectangle {
            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
            height: parent.height * 0.35
            gradient: Gradient {
                GradientStop { position: 0; color: "#00000000" }
                GradientStop { position: 1; color: "#a0000000" }
            }
        }
        Text {
            x: win.margin; anchors.bottom: parent.bottom; anchors.bottomMargin: win.height * 0.08
            text: p.item ? p.item.title + (p.item.subtitle ? "  ·  " + p.item.subtitle : "") : ""
            color: "#e6ffffff"; font.pixelSize: 30 * win.u
        }
    }
    Pan { id: a; visible: !root.music }
    Pan { id: b; visible: !root.music }

    Item {
        anchors.fill: parent
        visible: root.music
        Image {  // big blurred-looking backdrop: the album, scaled way up and dimmed
            anchors.fill: parent
            source: root.music ? home.nowPlaying.art : ""
            sourceSize.width: 64
            fillMode: Image.PreserveAspectCrop
            smooth: true
            opacity: 0.45
        }
        Rectangle { anchors.fill: parent; color: "#80000000" }
        Row {
            anchors.centerIn: parent
            spacing: 70 * win.u
            Image {
                width: win.height * 0.42; height: width
                source: root.music ? home.nowPlaying.art : ""
                sourceSize.width: 640
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 14 * win.u
                width: win.width * 0.36
                Text { width: parent.width; text: home.nowPlaying.title || ""; color: "white"; font.pixelSize: 58 * win.u
                       font.weight: Font.Bold; wrapMode: Text.WordWrap; maximumLineCount: 3; elide: Text.ElideRight }
                Text { width: parent.width; text: home.nowPlaying.artist || ""; color: "#ccffffff"; font.pixelSize: 36 * win.u; elide: Text.ElideRight }
            }
        }
    }

    Text {
        id: t
        anchors.right: parent.right; anchors.rightMargin: win.margin
        anchors.bottom: parent.bottom; anchors.bottomMargin: win.height * 0.075
        color: "white"; font.pixelSize: 64 * win.u; font.weight: Font.Light
        Timer { interval: 5000; repeat: true; running: root.shown; triggeredOnStart: true
                onTriggered: t.text = Qt.formatTime(new Date(), "h:mm") }
    }
}
