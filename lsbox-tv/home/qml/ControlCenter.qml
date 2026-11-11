// Menu / X button (or Home again on the first tile): TV power, sleep timer,
// sound, Bluetooth, picture, profiles, phone remote, settings and more.
// Every page is a list: Up/Down to choose, OK to act, Left/Right to change a
// value, Back to go up a page.
import QtQuick

Item {
    id: root
    property bool shown: false
    property int index: 0
    property string page: "main"
    property var mainIndex: 0
    property bool confirmReboot: false
    property string btMac: ""
    anchors.fill: parent
    visible: panel.x < win.width

    readonly property bool kids: home.profile.kids === true
    readonly property var s: home.settings

    function onOff(v) { return v ? "On" : "Off" }
    function hz(r) { return (Math.round(r * 100) / 100) + " Hz" }
    function deg(v) { return v === null || v === undefined ? "-" : v + "°C" }
    function pc(v) { return v === null || v === undefined ? "-" : v + "%" }
    function mins(m) { return m > 0 ? m + " min" : "Never" }

    readonly property var pageTitle: ({
        main: "", sound: "Sound", bluetooth: "Bluetooth", btdev: "Bluetooth device", sleep: "Sleep timer",
        picture: "Picture", health: "Box health", profiles: "Who's watching?", remote: "Phone remote",
        settings: "Home screen settings", update: "Update"
    })

    readonly property var actions: {
        var a = [], d, i
        switch (page) {
        case "main":
            a.push({ id: "tv", label: "Turn off TV", detail: "Box stays on for AirPlay" })
            a.push({ id: "sleep", label: "Sleep timer", value: home.sleepTimer.mode === "off" ? "Off" : home.sleepTimer.label })
            if (home.profiles.length > 1)
                a.push({ id: "profiles", label: "Profile", value: home.profile.name })
            if (kids) return a
            var vol = home.volume.level >= 0 ? (home.volume.muted ? "Muted" : home.volume.level + "%") : ""
            a.push({ id: "sound", label: "Sound", detail: activeSink(), value: vol })
            a.push({ id: "bluetooth", label: "Bluetooth", detail: btSummary() })
            a.push({ id: "switcher", label: "Open apps", detail: home.running.length + " running" })
            a.push({ id: "picture", label: "Picture", detail: pictureSummary() })
            a.push({ id: "remote", label: "Phone remote", value: onOff(s.remote) })
            a.push({ id: "settings", label: "Home screen settings", detail: "Theme, sounds, screensaver, auto-close" })
            a.push({ id: "health", label: "Box health",
                     detail: home.health.warnings && home.health.warnings.length ? home.health.warnings.join(", ") : (home.status.storage || "") })
            a.push({ id: "update", label: "Update home screen", detail: home.update.message || "" })
            a.push({ id: "closeall", label: "Close all apps", detail: "Frees memory. They start fresh next time." })
            if (home.hidden.length)
                a.push({ id: "unhide", label: "Show hidden apps", detail: home.hidden.length + " hidden" })
            a.push({ id: "system", label: "System Settings", detail: "Wi-Fi, users, everything else" })
            a.push({ id: "restart", label: "Restart home screen", detail: "Apps keep running" })
            a.push({ id: "reboot", label: confirmReboot ? "Press OK again to restart" : "Restart box" })
            return a
        case "sound":
            a.push({ id: "vol", label: "Volume", detail: "Left and Right to change, OK to mute",
                     value: home.volume.level < 0 ? "-" : (home.volume.muted ? "Muted" : home.volume.level + "%") })
            for (i = 0; i < home.sinks.length; i++)
                a.push({ id: "sink:" + home.sinks[i].name, label: home.sinks[i].label, on: home.sinks[i].active })
            if (!home.sinks.length) a.push({ id: "", label: "Looking for sound outputs..." })
            return a
        case "bluetooth":
            a.push({ id: "scan", label: home.btBusy !== "" ? home.btBusy : "Pair a new device", detail: home.btBusy !== "" ? "" : "Controllers, headphones, keyboards" })
            for (i = 0; i < home.btDevices.length; i++) {
                d = home.btDevices[i]
                a.push({ id: "dev:" + d.mac, label: d.name, detail: d.connected ? "Connected" : (d.paired ? "Paired" : "New: OK to pair") })
            }
            return a
        case "btdev":
            d = btDevice()
            if (!d) return [{ id: "back", label: "Back" }]
            if (!d.paired) a.push({ id: "pair", label: "Pair", detail: "Put it in pairing mode first" })
            else if (d.connected) a.push({ id: "disconnect", label: "Disconnect" })
            else a.push({ id: "connect", label: "Connect" })
            if (d.paired) a.push({ id: "remove", label: "Forget this device" })
            a.push({ id: "back", label: "Back" })
            return a
        case "sleep":
            var cur = home.sleepTimer.mode
            var opts = [["off", "Off"], ["30", "30 minutes"], ["60", "1 hour"], ["90", "1 hour 30"], ["120", "2 hours"], ["episode", "End of this episode"]]
            for (i = 0; i < opts.length; i++)
                a.push({ id: "sleep:" + opts[i][0], label: opts[i][1], on: cur === opts[i][0],
                         detail: cur === opts[i][0] && home.sleepTimer.endsAt > 0 ? "Ends at " + Qt.formatTime(new Date(home.sleepTimer.endsAt), "h:mm") : "" })
            return a
        case "picture":
            var dp = home.display
            if (dp.hdrCapable) a.push({ id: "hdr", label: "HDR", value: onOff(dp.hdr), detail: "Films switch it as needed" })
            var rates = dp.refreshes || []
            for (i = 0; i < rates.length; i++)
                a.push({ id: "hz:" + rates[i], label: hz(rates[i]), on: Math.abs(rates[i] - dp.refresh) < 0.01,
                         detail: i === 0 ? "Films pick the right rate on their own" : "" })
            var scales = [1.5, 1.7, 2.0]
            for (i = 0; i < scales.length; i++)
                a.push({ id: "scale:" + scales[i], label: "Text size " + ["small", "medium", "large"][i], on: Math.abs(scales[i] - dp.scale) < 0.01 })
            if (!a.length) a.push({ id: "", label: "Reading the display..." })
            return a
        case "health":
            var h = home.health
            a.push({ id: "", label: "Processor", value: deg(h.cpuTemp) })
            a.push({ id: "", label: "Graphics", value: deg(h.gpuTemp) + "  ·  " + pc(h.gpuLoad) })
            a.push({ id: "", label: "Wi-Fi signal", value: pc(h.wifi) })
            a.push({ id: "", label: "Memory used", value: pc(h.ram) })
            a.push({ id: "", label: "Storage used", value: h.diskText || "-" })
            a.push({ id: "", label: (h.warnings && h.warnings.length) ? h.warnings.join(", ") : "Everything looks good" })
            return a
        case "profiles":
            for (i = 0; i < home.profiles.length; i++) {
                d = home.profiles[i]
                a.push({ id: "prof:" + d.name, label: d.name, on: d.active, detail: (d.kids ? "Kids" : "") + (d.hasPin ? (d.kids ? " · " : "") + "PIN" : "") })
            }
            return a
        case "remote":
            var r = home.remote
            a.push({ id: "remote", label: "Phone remote", value: onOff(s.remote), detail: "A remote and keyboard in your phone's browser" })
            if (r.running) {
                a.push({ id: "", label: "Open " + r.url, detail: "On a phone on your home Wi-Fi" })
                a.push({ id: "", label: "Code " + r.pin, detail: "Asked once per phone" })
                a.push({ id: "newpin", label: "New code", detail: "Signs out every phone" })
            }
            return a
        case "settings":
            a.push({ id: "set:theme", label: "Theme", value: { dark: "Dark", light: "Light", artwork: "Artwork colours" }[s.theme] })
            a.push({ id: "set:sounds", label: "Click sounds", value: onOff(s.sounds), detail: "Silent while anything plays" })
            a.push({ id: "set:rumble", label: "Controller rumble", value: onOff(s.rumble) })
            a.push({ id: "set:warmMoonfin", label: "Start Moonfin early", value: onOff(s.warmMoonfin), detail: "First open is instant" })
            a.push({ id: "set:resumeLast", label: "Reopen last app after restart", value: onOff(s.resumeLast) })
            a.push({ id: "set:autoCloseHours", label: "Close unused apps after", value: s.autoCloseHours > 0 ? s.autoCloseHours + " h" : "Never" })
            a.push({ id: "set:screensaverMinutes", label: "Screensaver after", value: mins(s.screensaverMinutes) })
            a.push({ id: "set:saverTvOffMinutes", label: "TV off after screensaver", value: mins(s.saverTvOffMinutes) })
            if (home.profiles.length > 1)
                a.push({ id: "set:askProfile", label: "Ask who's watching at start", value: onOff(s.askProfile) })
            a.push({ id: "set:volumeMode", label: "Volume buttons", value: { auto: "Automatic", cec: "TV or receiver", pipewire: "This box" }[s.volumeMode] })
            return a
        case "update":
            var u = home.update
            if (u.state === "available")
                a.push({ id: "apply", label: "Install update", detail: u.message })
            else
                a.push({ id: "check", label: u.state === "checking" ? "Checking..." : "Check for updates", detail: u.message || "" })
            if (u.state === "available" && u.needs_install)
                a.push({ id: "", label: "This one also needs install.sh", detail: "Run the update command over SSH" })
            return a
        }
        return a
    }

    function activeSink() {
        for (var i = 0; i < home.sinks.length; i++) if (home.sinks[i].active) return home.sinks[i].label
        return ""
    }
    function btSummary() {
        var n = 0
        for (var i = 0; i < home.btDevices.length; i++) if (home.btDevices[i].connected) n++
        return n ? n + " connected" : "Pair controllers and headphones"
    }
    function pictureSummary() {
        var d = home.display
        if (!d.width) return ""
        return (d.width >= 3840 ? "4K" : d.height + "p") + " · " + Math.round(d.refresh) + " Hz" + (d.hdrCapable ? " · HDR " + onOff(d.hdr).toLowerCase() : "")
    }
    function btDevice() {
        for (var i = 0; i < home.btDevices.length; i++) if (home.btDevices[i].mac === btMac) return home.btDevices[i]
        return null
    }

    onShownChanged: {
        confirmReboot = false
        if (shown) {
            page = "main"; index = 0
            home.refreshStatus(); home.refreshSinks(); home.btRefresh(); home.refreshDisplay(); home.refreshHealth()
        }
    }
    onActionsChanged: if (index >= actions.length) index = Math.max(0, actions.length - 1)

    function open(p) {
        if (page === "main") mainIndex = index
        page = p
        index = 0
        if (p === "bluetooth") home.btRefresh()
        if (p === "health") home.refreshHealth()
        if (p === "picture") home.refreshDisplay()
        if (p === "sound") home.refreshSinks()
        if (p === "update" && home.update.state === "idle") home.checkUpdate()
    }
    function back() {
        if (page === "btdev") { page = "bluetooth"; index = 0 }
        else if (page !== "main") { page = "main"; index = mainIndex }
        else win.overlay = ""
    }

    function cycle(key, list, dir) {
        var i = list.indexOf(s[key])
        home.setSetting(key, list[(i + (dir || 1) + list.length) % list.length])
    }
    function change(id, dir) {   // Left / Right on a value
        if (id === "vol") { home.volumeStep(dir * 5); return true }
        if (id.indexOf("set:") !== 0) return false
        var k = id.substr(4)
        if (typeof s[k] === "boolean") { home.setSetting(k, !s[k]); return true }
        if (k === "theme") cycle(k, ["dark", "light", "artwork"], dir)
        else if (k === "autoCloseHours") cycle(k, [0, 2, 4, 8, 12], dir)
        else if (k === "screensaverMinutes") cycle(k, [0, 2, 5, 10, 15, 30], dir)
        else if (k === "saverTvOffMinutes") cycle(k, [0, 15, 30, 60, 120], dir)
        else if (k === "volumeMode") cycle(k, ["auto", "cec", "pipewire"], dir)
        return true
    }

    function run(id) {
        if (id === "") return
        if (id.indexOf("sink:") === 0) { home.setSink(id.substr(5)); return }
        if (id.indexOf("dev:") === 0) {
            btMac = id.substr(4)
            var d = btDevice()
            if (d && !d.paired) home.btAction("pair", btMac)
            else { page = "btdev"; index = 0 }
            return
        }
        if (id.indexOf("sleep:") === 0) { home.setSleepTimer(id.substr(6)); back(); return }
        if (id.indexOf("hz:") === 0) { home.setDisplay("refresh", parseFloat(id.substr(3))); return }
        if (id.indexOf("scale:") === 0) { home.setDisplay("scale", parseFloat(id.substr(6))); return }
        if (id.indexOf("prof:") === 0) { win.chooseProfile(id.substr(5)); return }
        if (id.indexOf("set:") === 0) { change(id, 1); return }
        switch (id) {
        case "tv": win.overlay = ""; home.tvOff(); break
        case "switcher": win.overlay = "switcher"; switcher.index = 0; break
        case "closeall": home.closeAll(); win.overlay = ""; break
        case "system": win.overlay = ""; home.openSettings(); break
        case "unhide": home.unhideAll(); break
        case "restart": home.restartHome(); break
        case "reboot": if (confirmReboot) home.reboot(); else confirmReboot = true; break
        case "vol": home.volumeStep(0); break
        case "scan": home.btScan(); break
        case "pair": case "connect": case "disconnect": case "remove":
            home.btAction(id, btMac); page = "bluetooth"; index = 0; break
        case "back": back(); break
        case "hdr": home.setDisplay("hdr", !home.display.hdr); break
        case "remote": home.setSetting("remote", !s.remote); break
        case "newpin": home.newRemotePin(); break
        case "check": home.checkUpdate(); break
        case "apply": home.applyUpdate(); break
        default: open(id)
        }
    }

    function key(e) {
        var k = e.key
        var a = actions[index]
        if (k === Qt.Key_Up) { index = Math.max(0, index - 1); confirmReboot = false; home.feedback() }
        else if (k === Qt.Key_Down) { index = Math.min(actions.length - 1, index + 1); confirmReboot = false; home.feedback() }
        else if ((k === Qt.Key_Left || k === Qt.Key_Right) && a && change(a.id, k === Qt.Key_Right ? 1 : -1)) {}
        else if (keys.isOk(k) && !e.isAutoRepeat) { if (a) run(a.id) }
        else if (k === Qt.Key_Left || keys.isBack(k)) back()
        else if (keys.isMenu(k)) win.overlay = ""
    }

    Rectangle {
        anchors.fill: parent
        color: "black"
        opacity: root.shown ? 0.45 : 0
        Behavior on opacity { NumberAnimation { duration: 200 } }
    }
    Rectangle {
        id: panel
        width: win.width * 0.32
        height: win.height - 2 * y
        y: 40 * win.u
        x: root.shown ? win.width - width - 40 * win.u : win.width + 20
        Behavior on x { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
        radius: 34 * win.u
        color: theme.panel
        border.color: "#22ffffff"
        border.width: 1

        Column {
            id: panelCol
            x: 36 * win.u; y: 40 * win.u
            width: parent.width - 72 * win.u
            spacing: 26 * win.u
            Column {
                visible: root.page === "main"
                spacing: 4 * win.u
                Text { id: bigTime; color: theme.panelText; font.pixelSize: 64 * win.u; font.weight: Font.Bold }
                Text { id: date; color: theme.panelDim; font.pixelSize: 26 * win.u }
                Timer {
                    interval: 5000; repeat: true; triggeredOnStart: true; running: root.shown
                    onTriggered: { var d = new Date(); bigTime.text = Qt.formatTime(d, "h:mm"); date.text = Qt.formatDate(d, "dddd, MMMM d") }
                }
            }
            Row {
                visible: root.page === "main"
                spacing: 12 * win.u
                Rectangle { width: 14 * win.u; height: width; radius: width / 2; anchors.verticalCenter: parent.verticalCenter
                            color: home.status.airplay === "Ready as LSBox" ? "#34c759" : "#8e8e93" }
                Text { text: "AirPlay: " + (home.status.airplay || "unknown") + (home.profiles.length > 1 ? "   ·   " + home.profile.name : "")
                       color: theme.panelText; font.pixelSize: 24 * win.u }
            }
            Text {
                visible: root.page !== "main"
                text: root.pageTitle[root.page] || ""
                color: theme.panelText; font.pixelSize: 48 * win.u; font.weight: Font.Bold
            }
            MenuList {
                width: parent.width
                items: root.actions
                index: root.index
                maxHeight: panel.height - y - 150 * win.u
            }
        }
        Text {
            anchors.bottom: parent.bottom; anchors.bottomMargin: 26 * win.u
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.page === "main" ? "Back to close" : "Back for the main menu"
            color: theme.panelDim; font.pixelSize: 20 * win.u
        }
    }
}
