// LSBox Home: 10-foot home screen. Everything is driven by the arrow keys,
// Enter, Back, Menu and Home that the CEC remote and the controller send.
import QtQuick
import QtQuick.Window
import QtQuick.Effects

Window {
    id: win
    visible: true
    visibility: home.demo ? Window.Windowed : Window.FullScreen
    width: 1920
    height: 1080
    color: "black"
    title: "LSBox Home"

    readonly property real u: height / 1080
    readonly property int columns: 5
    readonly property real margin: width * 0.068
    readonly property real gap: width * 0.024
    readonly property real tileW: (width - 2 * margin - (columns - 1) * gap) / columns
    readonly property real tileH: tileW * 0.6
    readonly property real rowStep: tileH + 120 * u
    readonly property real gridTop: height * 0.62
    readonly property real cardH: height * 0.2
    readonly property real cardW: cardH * 16 / 9

    property var apps: home.apps_
    property var shelfItems: home.shelf
    property int gridIndex: 0
    property int shelfIndex: 0
    property string mode: "grid"        // grid | shelf
    property string overlay: ""         // "" | control | switcher | menu | move | saver | launch
    property var launching: null
    property bool enterHeld: false

    readonly property var focusedApp: apps.length ? apps[Math.min(gridIndex, apps.length - 1)] : null
    readonly property bool hasShelf: focusedApp !== null && focusedApp.shelf === "jellyfin" && shelfItems.length > 0
    readonly property var heroItem: mode === "shelf" && shelfItems.length ? shelfItems[Math.min(shelfIndex, shelfItems.length - 1)]
                                   : (hasShelf ? shelfItems[0] : null)
    readonly property int gridRow: Math.floor(gridIndex / columns)

    function clampGrid() { gridIndex = Math.max(0, Math.min(gridIndex, apps.length - 1)) }
    onAppsChanged: clampGrid()
    onShelfItemsChanged: { if (shelfIndex >= shelfItems.length) shelfIndex = 0; if (!shelfItems.length && mode === "shelf") mode = "grid" }

    function goHomeRoot() {
        overlay = ""
        mode = "grid"
        gridIndex = 0
        shelfIndex = 0
    }

    function openFocused() {
        if (mode === "shelf") {
            var it = shelfItems[shelfIndex]
            if (it) home.openShelfItem(it.id, false)
            return
        }
        if (!focusedApp) return
        if (!focusedApp.running) {
            launching = focusedApp
            overlay = "launch"
            launchTimer.restart()
        }
        home.launch(focusedApp.key)
    }

    Connections {
        target: home
        function onHomeAgain() {
            if (overlay !== "" && overlay !== "launch") overlay = ""
            else goHomeRoot()
        }
        function onHomeShown() { if (overlay !== "switcher") overlay = ""; idle.restart() }
        function onHomeDouble() { overlay = "switcher"; switcher.index = 0 }
        function onLaunchFailed(key) { overlay = "" }
        function onLauncherActiveChanged() {
            if (!home.launcherActive && overlay === "launch") { overlay = ""; launching = null }
            if (home.launcherActive) idle.restart()
        }
    }

    Timer { id: launchTimer; interval: 9000; onTriggered: if (overlay === "launch") overlay = "" }

    Timer {
        id: idle
        interval: 60000 * Math.max(1, home.saverMinutes)
        running: home.saverMinutes > 0 && home.launcherActive && overlay === "" && home.saver.length > 0
        onTriggered: overlay = "saver"
    }

    Timer { id: holdTimer; interval: 650; onTriggered: { enterHeld = true; if (mode === "grid" && focusedApp) { overlay = "menu"; tileMenu.index = 0 } } }

    // ------------------------------------------------------------ background
    Item {
        id: backdrop
        anchors.fill: parent

        // App mood when no picture: the focused app's colours.
        Rectangle {
            anchors.fill: parent
            opacity: heroItem ? 0 : 1
            Behavior on opacity { NumberAnimation { duration: 350 } }
            gradient: Gradient {
                GradientStop { position: 0.0; color: focusedApp ? Qt.darker(focusedApp.color2, 1.6) : "#111" }
                GradientStop { position: 0.75; color: "#050507" }
            }
            Behavior on gradient { enabled: false }
            Image {
                visible: focusedApp !== null && !heroItem
                source: focusedApp ? "image://icon/" + encodeURIComponent(focusedApp.icon) : ""
                sourceSize: Qt.size(512, 512)
                width: win.height * 0.62; height: width
                x: win.width - width * 0.85; y: -height * 0.12
                opacity: 0.10
                smooth: true
            }
        }

        CrossImage {
            id: heroImage
            anchors.fill: parent
            source: heroItem ? heroItem.backdrop : ""
        }

        // Fade the picture into black where the tiles sit.
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0.0; color: "#55000000" }
                GradientStop { position: 0.30; color: "#10000000" }
                GradientStop { position: 0.52; color: "#b0000000" }
                GradientStop { position: 0.68; color: "#f0000000" }
                GradientStop { position: 1.0; color: "#ff000000" }
            }
        }
        Rectangle {  // left side scrim for the title text
            anchors.left: parent.left; anchors.top: parent.top
            width: parent.width * 0.55; height: parent.height * 0.6
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "#99000000" }
                GradientStop { position: 1.0; color: "#00000000" }
            }
        }
    }

    // ------------------------------------------------------------ page
    Item {
        id: page
        width: win.width
        height: win.height * 2
        y: gridRow > 0 && mode === "grid" ? -(gridTop - win.height * 0.22) - (gridRow - 1) * rowStep : 0
        Behavior on y { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }

        // Hero text
        Column {
            x: margin
            y: win.height * 0.085
            width: win.width * 0.5
            spacing: 14 * u
            opacity: gridRow === 0 || mode === "shelf" ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 200 } }

            Text {
                text: heroItem ? heroItem.group : ""
                visible: text !== ""
                color: "#d9ffffff"
                font.pixelSize: 26 * u
                font.weight: Font.DemiBold
                font.capitalization: Font.AllUppercase
                font.letterSpacing: 2 * u
            }
            Image {
                id: heroLogo
                visible: heroItem !== null && heroItem.logo !== "" && status === Image.Ready
                source: heroItem ? heroItem.logo : ""
                width: Math.min(implicitWidth, win.width * 0.32)
                height: Math.min(win.height * 0.16, width * implicitHeight / Math.max(1, implicitWidth))
                fillMode: Image.PreserveAspectFit
                horizontalAlignment: Image.AlignLeft
                asynchronous: true
            }
            Text {
                visible: !heroLogo.visible
                width: parent.width
                text: heroItem ? heroItem.title : (focusedApp ? focusedApp.name : "")
                color: "white"
                font.pixelSize: 84 * u
                font.weight: Font.Bold
                elide: Text.ElideRight
                maximumLineCount: 2
                wrapMode: Text.WordWrap
                style: Text.Raised; styleColor: "#40000000"
            }
            Text {
                width: parent.width
                text: heroItem ? heroItem.subtitle : (focusedApp ? focusedApp.tagline : "")
                visible: text !== ""
                color: "#e6ffffff"
                font.pixelSize: 32 * u
                elide: Text.ElideRight
            }
            Text {
                visible: focusedApp !== null && focusedApp.shelf === "jellyfin" && shelfItems.length === 0 && home.status.jellyfin !== undefined && home.status.jellyfin !== ""
                text: home.status.jellyfin || ""
                color: "#99ffffff"
                font.pixelSize: 22 * u
            }
        }

        // Top shelf cards (Moonfin focused)
        ListView {
            id: shelfList
            x: 0
            y: win.height * 0.345
            width: win.width
            height: cardH * 1.25
            orientation: ListView.Horizontal
            spacing: 34 * u
            leftMargin: margin
            rightMargin: margin
            clip: false
            interactive: false
            model: shelfItems
            currentIndex: shelfIndex
            highlightMoveDuration: 220
            preferredHighlightBegin: margin
            preferredHighlightEnd: win.width - margin - cardW
            highlightRangeMode: ListView.ApplyRange
            opacity: hasShelf || mode === "shelf" ? 1 : 0
            visible: opacity > 0
            Behavior on opacity { NumberAnimation { duration: 220 } }
            delegate: Item {
                id: card
                required property var modelData
                required property int index
                readonly property bool isFocused: mode === "shelf" && index === shelfIndex
                width: cardW
                height: cardH
                z: isFocused ? 5 : 0
                scale: isFocused ? 1.12 : (mode === "shelf" ? 1.0 : 0.94)
                opacity: mode === "shelf" || index < 6 ? 1 : 0.6
                Behavior on scale { NumberAnimation { duration: 170; easing.type: Easing.OutCubic } }

                Shadow { anchors.fill: art; strong: card.isFocused }
                Item {
                    id: art
                    anchors.fill: parent
                    layer.enabled: true
                    layer.effect: MultiEffect { maskEnabled: true; maskSource: cardMask; maskThresholdMin: 0.5; maskSpreadAtMin: 1.0 }
                    Rectangle { anchors.fill: parent; color: "#1d2230" }
                    Image {
                        anchors.fill: parent
                        source: card.modelData.thumb
                        sourceSize.width: 800
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true
                    }
                    Rectangle {
                        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                        height: parent.height * 0.5
                        gradient: Gradient {
                            GradientStop { position: 0; color: "#00000000" }
                            GradientStop { position: 1; color: "#cc000000" }
                        }
                    }
                    Rectangle {  // progress bar
                        visible: card.modelData.progress > 0.01
                        x: parent.width * 0.06; y: parent.height - 18 * u
                        width: parent.width * 0.88; height: 6 * u; radius: 3 * u
                        color: "#55ffffff"
                        Rectangle { width: parent.width * card.modelData.progress; height: parent.height; radius: parent.radius; color: "white" }
                    }
                    Sheen { active: card.isFocused }
                }
                Rectangle { id: cardMask; anchors.fill: art; radius: 14 * u; visible: false; layer.enabled: true; color: "black" }
                Text {
                    anchors.top: parent.bottom; anchors.topMargin: 16 * u
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text: card.modelData.title
                    color: "white"
                    font.pixelSize: 24 * u
                    elide: Text.ElideRight
                    opacity: card.isFocused ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: 150 } }
                }
            }
        }

        // App tiles
        Repeater {
            model: apps
            delegate: Tile {
                required property var modelData
                required property int index
                app: modelData
                x: margin + (index % columns) * (tileW + gap)
                y: gridTop + Math.floor(index / columns) * rowStep
                width: tileW
                height: tileH
                focused: mode === "grid" && index === gridIndex && overlay !== "saver"
                wiggle: overlay === "move" && index === gridIndex
                dimmed: mode === "shelf"
            }
        }
    }

    // ------------------------------------------------------------ clock
    Text {
        id: clock
        anchors.right: parent.right; anchors.rightMargin: margin
        y: win.height * 0.05
        color: "white"
        font.pixelSize: 34 * u
        font.weight: Font.Medium
        style: Text.Raised; styleColor: "#60000000"
        opacity: (gridRow === 0 || mode === "shelf") && (overlay === "" || overlay === "move") ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 200 } }
        Timer {
            interval: 5000; running: true; repeat: true; triggeredOnStart: true
            onTriggered: clock.text = Qt.formatTime(new Date(), "h:mm")
        }
    }

    // ------------------------------------------------------------ overlays
    LaunchSplash { id: splash; app: launching; shown: overlay === "launch" }
    ControlCenter { id: control; shown: overlay === "control" }
    Switcher { id: switcher; shown: overlay === "switcher" }
    TileMenu { id: tileMenu; shown: overlay === "menu"; app: focusedApp }
    Screensaver { id: saver; shown: overlay === "saver"; items: home.saver }

    Text {  // hint while moving a tile
        visible: overlay === "move"
        anchors.horizontalCenter: parent.horizontalCenter
        y: win.height * 0.93
        text: "Use the arrows to move " + (focusedApp ? focusedApp.name : "") + ". Press OK when done."
        color: "#ccffffff"
        font.pixelSize: 26 * u
    }

    // ------------------------------------------------------------ keys
    Item {
        id: keys
        anchors.fill: parent
        focus: true

        function isOk(k) { return k === Qt.Key_Return || k === Qt.Key_Enter || k === Qt.Key_Select || k === Qt.Key_Space }
        function isBack(k) { return k === Qt.Key_Escape || k === Qt.Key_Back || k === Qt.Key_Cancel || k === Qt.Key_Backspace }
        function isPlay(k) { return k === Qt.Key_MediaPlay || k === Qt.Key_MediaTogglePlayPause || k === Qt.Key_Play }
        function isMenu(k) { return k === Qt.Key_Menu || k === Qt.Key_Info }

        Keys.onPressed: function (e) {
            idle.restart()
            var k = e.key
            e.accepted = true
            if (k === Qt.Key_HomePage) { home.showHome(); return }
            switch (overlay) {
            case "saver": overlay = ""; return
            case "launch": if (isBack(k)) overlay = ""; return
            case "control": control.key(e); return
            case "switcher": switcher.key(e); return
            case "menu": tileMenu.key(e); return
            case "move":
                if (k === Qt.Key_Left || k === Qt.Key_Right || k === Qt.Key_Up || k === Qt.Key_Down) {
                    var d = k === Qt.Key_Left ? -1 : k === Qt.Key_Right ? 1 : k === Qt.Key_Up ? -columns : columns
                    var target = Math.max(0, Math.min(apps.length - 1, gridIndex + d))
                    if (focusedApp && target !== gridIndex) { home.moveApp(focusedApp.key, target - gridIndex); gridIndex = target }
                } else if ((isOk(k) && !e.isAutoRepeat) || isBack(k)) {
                    overlay = ""
                }
                return
            }
            if (isMenu(k)) { overlay = "control"; control.index = 0; home.refreshStatus(); return }
            if (isOk(k)) {
                if (!e.isAutoRepeat) { enterHeld = false; holdTimer.restart() }
                return
            }
            if (isPlay(k) && mode === "shelf") {
                var it = shelfItems[shelfIndex]
                if (it) home.openShelfItem(it.id, true)
                return
            }
            if (mode === "shelf") {
                if (k === Qt.Key_Left) shelfIndex = Math.max(0, shelfIndex - 1)
                else if (k === Qt.Key_Right) shelfIndex = Math.min(shelfItems.length - 1, shelfIndex + 1)
                else if (k === Qt.Key_Down || isBack(k)) mode = "grid"
                return
            }
            // grid
            if (k === Qt.Key_Left) { if (gridIndex % columns > 0) gridIndex-- }
            else if (k === Qt.Key_Right) { if (gridIndex % columns < columns - 1 && gridIndex < apps.length - 1) gridIndex++ }
            else if (k === Qt.Key_Up) {
                if (gridRow > 0) gridIndex -= columns
                else if (hasShelf) { mode = "shelf"; shelfIndex = 0 }
            }
            else if (k === Qt.Key_Down) { if (gridIndex + columns < apps.length) gridIndex += columns; else if (gridRow < Math.floor((apps.length - 1) / columns)) gridIndex = apps.length - 1 }
            else if (isBack(k)) { gridIndex = 0 }
            else if (k === Qt.Key_Tab) { gridIndex = Math.min(apps.length - 1, gridIndex + 1) }
            else if (k === Qt.Key_Backtab) { gridIndex = Math.max(0, gridIndex - 1) }
            else e.accepted = false
        }
        Keys.onReleased: function (e) {
            if (!isOk(e.key) || e.isAutoRepeat) return
            e.accepted = true
            if (overlay === "" && holdTimer.running) { holdTimer.stop(); openFocused() }
            else if (overlay === "control" || overlay === "switcher" || overlay === "menu") { /* acted on press */ }
            holdTimer.stop()
        }
    }
}
