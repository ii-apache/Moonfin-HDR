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
    property int gridIndex: 0
    property int shelfIndex: 0
    property int rowIndex: 0
    property string mode: "grid"        // grid | shelf | np (Now Playing pill)
    property string overlay: ""         // "" | control | switcher | menu | move | saver | launch | search | profiles
    property var launching: null
    property bool enterHeld: false

    readonly property var focusedApp: apps.length ? apps[Math.min(gridIndex, apps.length - 1)] : null
    readonly property var rows: focusedApp && home.shelfRows[focusedApp.key] ? home.shelfRows[focusedApp.key].filter(function (r) { return r.items && r.items.length }) : []
    readonly property var curRow: rows.length ? rows[Math.min(rowIndex, rows.length - 1)] : null
    readonly property var shelfItems: curRow ? curRow.items : []
    readonly property bool hasShelf: rows.length > 0
    readonly property var heroItem: mode === "shelf" && shelfItems.length ? shelfItems[Math.min(shelfIndex, shelfItems.length - 1)]
                                   : (hasShelf ? rows[0].items[0] : null)
    readonly property int gridRow: Math.floor(gridIndex / columns)
    readonly property bool npActive: home.nowPlaying.active === true

    // ------------------------------------------------------------ theme
    QtObject {
        id: theme
        readonly property string name: home.settings.theme || "dark"
        readonly property bool light: name === "light"
        readonly property color tint: name === "artwork" && heroItem && heroItem.tint ? heroItem.tint
                                      : (focusedApp ? Qt.darker(focusedApp.color2, 1.6) : "#111111")
        readonly property bool overPicture: heroItem !== null
        // page text (over the background or a picture)
        readonly property color text: light && !overPicture ? "#111111" : "white"
        readonly property color dim: light && !overPicture ? "#99000000" : "#ccffffff"
        // solid full-screen pages (search, profiles)
        readonly property color bgSolid: light ? "#eceef2" : (name === "artwork" ? Qt.darker(tint, 2.2) : "#050507")
        readonly property color ink: light ? "#111111" : "white"
        readonly property color inkDim: light ? "#8c000000" : "#b3ffffff"
        // side panels and menus
        readonly property color panel: light ? "#f2f4f4f7" : (name === "artwork" ? Qt.rgba(Qt.darker(tint, 1.8).r, Qt.darker(tint, 1.8).g, Qt.darker(tint, 1.8).b, 0.93) : "#e01c1d22")
        readonly property color panelText: light ? "#111111" : "white"
        readonly property color panelDim: light ? "#8c000000" : "#b3ffffff"
        readonly property color rowBg: light ? "#14000000" : "#26ffffff"
        readonly property color selBg: light ? "#1c1d22" : "white"
        readonly property color selText: light ? "white" : "#111111"
        readonly property color selDim: light ? "#ccffffff" : "#555555"
    }

    function clampGrid() { gridIndex = Math.max(0, Math.min(gridIndex, apps.length - 1)) }
    onAppsChanged: clampGrid()
    onRowsChanged: {
        if (rowIndex >= rows.length) rowIndex = 0
        if (!rows.length && mode === "shelf") mode = "grid"
    }
    onShelfItemsChanged: if (shelfIndex >= shelfItems.length) shelfIndex = Math.max(0, shelfItems.length - 1)
    onNpActiveChanged: if (!npActive && mode === "np") mode = "grid"
    onGridIndexChanged: { rowIndex = 0; shelfIndex = 0 }

    function chooseProfile(name) {
        overlay = "profiles"
        profiles.choose(name)
    }

    function goHomeRoot() {
        overlay = ""
        mode = "grid"
        gridIndex = 0
        rowIndex = 0
        shelfIndex = 0
    }

    function openFocused() {
        if (mode === "np") { home.npControl("toggle"); return }
        if (mode === "shelf") {
            var it = shelfItems[shelfIndex]
            if (it) home.openCard(it, false)
            return
        }
        if (!focusedApp) return
        if (focusedApp.builtin === "search") { overlay = "search"; return }
        if (!focusedApp.running) {
            launching = focusedApp
            overlay = "launch"
            launchTimer.restart()
        }
        home.launch(focusedApp.key)
    }

    function openControl() { overlay = "control" }

    Component.onCompleted: {
        if (home.settings.askProfile && home.profiles.length > 1) { overlay = "profiles"; profiles.start("") }
    }

    Connections {
        target: home
        function onHomeAgain() {
            if (overlay !== "" && overlay !== "launch") overlay = ""
            else if (mode === "grid" && gridIndex === 0) openControl()   // Home again on the first tile
            else goHomeRoot()
        }
        function onHomeShown() { if (overlay !== "switcher") overlay = ""; idle.restart() }
        function onHomeDouble() { overlay = "switcher"; switcher.index = 0 }
        function onLaunchFailed(key) { overlay = "" }
        function onLauncherActiveChanged() {
            if (!home.launcherActive && overlay === "launch") { overlay = ""; launching = null }
            if (home.launcherActive) idle.restart()
        }
        function onRemoteText(t) {
            if (overlay !== "search") { overlay = "search" }
            search.append(t)
        }
    }

    Timer { id: launchTimer; interval: 9000; onTriggered: if (overlay === "launch") overlay = "" }

    Timer {
        id: idle
        interval: 60000 * Math.max(1, home.saverMinutes)
        running: home.saverMinutes > 0 && home.launcherActive && overlay === "" && (home.saver.length > 0 || screensaverMusic)
        onTriggered: overlay = "saver"
    }

    readonly property bool screensaverMusic: npActive && home.nowPlaying.video !== true && (home.nowPlaying.art || "") !== ""

    // Hold OK: tile menu on an app, play on a shelf card, open the app on Now Playing.
    Timer {
        id: holdTimer; interval: 650
        onTriggered: {
            enterHeld = true
            if (mode === "np") home.npOpen()
            else if (mode === "shelf") { var it = shelfItems[shelfIndex]; if (it) home.openCard(it, true) }
            else if (mode === "grid" && focusedApp && !home.profile.kids) { overlay = "menu"; tileMenu.index = 0 }
        }
    }

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
                GradientStop { position: 0.0; color: theme.light ? "#f4f5f8" : theme.tint }
                GradientStop { position: 0.75; color: theme.light ? "#c9ccd4" : "#050507" }
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
            visible: heroItem !== null || !theme.light
            gradient: Gradient {
                GradientStop { position: 0.0; color: "#55000000" }
                GradientStop { position: 0.30; color: "#10000000" }
                GradientStop { position: 0.52; color: "#b0000000" }
                GradientStop { position: 0.68; color: "#f0000000" }
                GradientStop { position: 1.0; color: "#ff000000" }
            }
        }
        Rectangle {  // left side scrim for the title text
            visible: heroItem !== null
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
                color: theme.dim
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
                color: theme.text
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
                color: theme.dim
                font.pixelSize: 32 * u
                elide: Text.ElideRight
            }
            Text {
                visible: focusedApp !== null && focusedApp.shelf === "jellyfin" && !hasShelf && (home.status.jellyfin || "") !== ""
                text: home.status.jellyfin || ""
                color: theme.dim
                font.pixelSize: 22 * u
            }
        }

        // Row names above the cards: Up/Down moves between them.
        Row {
            x: margin
            y: win.height * 0.345 - 62 * u
            spacing: 34 * u
            opacity: mode === "shelf" && rows.length > 1 ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 200 } }
            Repeater {
                model: rows
                Text {
                    required property var modelData
                    required property int index
                    text: modelData.title
                    color: index === rowIndex ? "white" : "#80ffffff"
                    font.pixelSize: 26 * u
                    font.weight: index === rowIndex ? Font.Bold : Font.Normal
                }
            }
        }

        // Top shelf cards for the focused app (Moonfin, Spotify, Steam)
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
            delegate: Card {
                required property var modelData
                required property int index
                item: modelData
                focused: mode === "shelf" && index === shelfIndex
                dim: mode !== "shelf"
                textColor: "white"
                opacity: mode === "shelf" || index < 6 ? 1 : 0.6
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
        color: theme.text
        font.pixelSize: 34 * u
        font.weight: Font.Medium
        style: Text.Raised; styleColor: theme.light && !theme.overPicture ? "transparent" : "#60000000"
        opacity: (gridRow === 0 || mode === "shelf") && (overlay === "" || overlay === "move") ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 200 } }
        Timer {
            interval: 5000; running: true; repeat: true; triggeredOnStart: true
            onTriggered: clock.text = Qt.formatTime(new Date(), "h:mm")
        }
    }

    NowPlaying {
        id: nowPlaying
        anchors.right: clock.left; anchors.rightMargin: 34 * u
        anchors.verticalCenter: clock.verticalCenter
        focused: mode === "np" && overlay === ""
        opacity: npActive && (gridRow === 0 || mode !== "grid") && (overlay === "" || overlay === "move") ? 1 : 0
    }

    // ------------------------------------------------------------ overlays
    LaunchSplash { id: splash; app: launching; shown: overlay === "launch" }
    ControlCenter { id: control; shown: overlay === "control" }
    Switcher { id: switcher; shown: overlay === "switcher" }
    TileMenu { id: tileMenu; shown: overlay === "menu"; app: focusedApp }
    Screensaver { id: saver; shown: overlay === "saver"; items: home.saver }
    Search { id: search; shown: overlay === "search" }
    ProfilePicker { id: profiles; shown: overlay === "profiles" }
    Toasts { anchors.fill: parent; active: home.launcherActive || home.demo; z: 100 }
    OverlayWindow { id: overlayWindow }

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
        function isMenu(k) { return k === Qt.Key_Menu || k === Qt.Key_Info || k === Qt.Key_MenuKB || k === Qt.Key_Game || k === Qt.Key_Settings }
        function isNav(k) { return k === Qt.Key_Left || k === Qt.Key_Right || k === Qt.Key_Up || k === Qt.Key_Down }

        Keys.onPressed: function (e) {
            idle.restart()
            var k = e.key
            e.accepted = true
            if (k === Qt.Key_HomePage) { home.showHome(); return }
            if (k === Qt.Key_VolumeUp) { home.volumeStep(5); return }
            if (k === Qt.Key_VolumeDown) { home.volumeStep(-5); return }
            if (k === Qt.Key_VolumeMute) { home.volumeStep(0); return }
            if (overlay === "" && (k === Qt.Key_MediaNext || k === Qt.Key_MediaPrevious)) {
                home.npControl(k === Qt.Key_MediaNext ? "next" : "previous"); return
            }
            switch (overlay) {
            case "saver": overlay = ""; return
            case "launch": if (isBack(k)) overlay = ""; return
            case "control": control.key(e); return
            case "switcher": switcher.key(e); return
            case "menu": tileMenu.key(e); return
            case "search": search.key(e); return
            case "profiles": profiles.key(e); return
            case "move":
                if (isNav(k)) {
                    var d = k === Qt.Key_Left ? -1 : k === Qt.Key_Right ? 1 : k === Qt.Key_Up ? -columns : columns
                    var target = Math.max(0, Math.min(apps.length - 1, gridIndex + d))
                    if (focusedApp && target !== gridIndex) { var key = focusedApp.key; home.moveApp(key, target - gridIndex); gridIndex = target }
                } else if ((isOk(k) && !e.isAutoRepeat) || isBack(k)) {
                    overlay = ""
                }
                return
            }
            if (isMenu(k)) { openControl(); return }
            if (isOk(k)) {
                if (!e.isAutoRepeat) { enterHeld = false; holdTimer.restart() }
                return
            }
            if (isPlay(k)) {
                if (mode === "shelf") { var it = shelfItems[shelfIndex]; if (it) home.openCard(it, true) }
                else if (npActive) home.npControl("toggle")
                return
            }
            if (isNav(k)) home.feedback()
            if (mode === "np") {
                if (k === Qt.Key_Left) home.npControl("previous")
                else if (k === Qt.Key_Right) home.npControl("next")
                else if (k === Qt.Key_Down || isBack(k)) mode = hasShelf ? "shelf" : "grid"
                return
            }
            if (mode === "shelf") {
                if (k === Qt.Key_Left) shelfIndex = Math.max(0, shelfIndex - 1)
                else if (k === Qt.Key_Right) shelfIndex = Math.min(shelfItems.length - 1, shelfIndex + 1)
                else if (k === Qt.Key_Up) {
                    if (rowIndex < rows.length - 1) { rowIndex++; shelfIndex = 0 }
                    else if (npActive) mode = "np"
                }
                else if (k === Qt.Key_Down) {
                    if (rowIndex > 0) { rowIndex--; shelfIndex = 0 }
                    else mode = "grid"
                }
                else if (isBack(k)) { mode = "grid"; rowIndex = 0 }
                return
            }
            // grid
            if (k === Qt.Key_Left) { if (gridIndex % columns > 0) gridIndex-- }
            else if (k === Qt.Key_Right) { if (gridIndex % columns < columns - 1 && gridIndex < apps.length - 1) gridIndex++ }
            else if (k === Qt.Key_Up) {
                if (gridRow > 0) gridIndex -= columns
                else if (hasShelf) { mode = "shelf"; rowIndex = 0; shelfIndex = 0 }
                else if (npActive) mode = "np"
            }
            else if (k === Qt.Key_Down) { if (gridIndex + columns < apps.length) gridIndex += columns; else if (gridRow < Math.floor((apps.length - 1) / columns)) gridIndex = apps.length - 1 }
            else if (isBack(k)) { gridIndex = 0 }
            else if (k === Qt.Key_Tab) { gridIndex = Math.min(apps.length - 1, gridIndex + 1) }
            else if (k === Qt.Key_Backtab) { gridIndex = Math.max(0, gridIndex - 1) }
            else if (k === Qt.Key_Search) { overlay = "search" }
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
