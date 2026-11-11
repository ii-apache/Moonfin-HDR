// LSBox Home bridge, loaded into KWin by lsbox_home.py at start.
// Tells the home screen which windows are open and which one is in front,
// brings new app windows forward, makes the HomePage key (CEC Home / Clear)
// come back home from any app, sends the volume keys to the home screen,
// and keeps the banner overlay on top without ever giving it focus.
const SELF_PID = __SELF_PID__;
const SERVICE = "__SERVICE__";
const OVERLAY = "LSBox Overlay";

function isOverlay(w) { return !!w && w.pid === SELF_PID && String(w.caption || "") === OVERLAY; }
function isSelf(w) { return !!w && w.pid === SELF_PID && !isOverlay(w); }

function info(w) {
    return {
        id: String(w.internalId),
        cls: String(w.resourceClass || ""),
        name: String(w.resourceName || ""),
        desktop: String(w.desktopFileName || ""),
        caption: String(w.caption || ""),
        pid: w.pid || 0,
        active: workspace.activeWindow === w
    };
}

function push(gone) {
    const list = [];
    for (const w of workspace.windowList()) {
        if (w === gone || !w.normalWindow || w.skipTaskbar || isOverlay(w)) continue;
        list.push(info(w));
    }
    callDBus(SERVICE, "/Home", SERVICE, "windows", JSON.stringify(list));
}

function selfWindow() {
    for (const w of workspace.windowList()) {
        if (isSelf(w) && w.normalWindow) return w;
    }
    return null;
}

function isApp(w) {
    return !!w && w.normalWindow && !w.skipTaskbar && w.pid !== SELF_PID &&
        String(w.resourceClass || "").toLowerCase() !== "moonfin-video";
}

function goHome() {
    const me = selfWindow();
    if (me) { me.minimized = false; workspace.activeWindow = me; }
}

function placeOverlay(w) {
    w.skipTaskbar = true;
    w.skipSwitcher = true;
    w.skipPager = true;
    w.keepAbove = true;
    w.noBorder = true;
    const area = workspace.clientArea(KWin.FullScreenArea, w);
    const g = w.frameGeometry;
    w.frameGeometry = { x: area.x + area.width - g.width, y: area.y, width: g.width, height: g.height };
}

// The home screen is a normal window, so it would sit above Moonfin's video
// layer (a keep-below window). Minimising it while an app is in front keeps
// the movie visible, exactly like the Bigscreen desktop did.
let lastActive = null;
workspace.windowActivated.connect(function (w) {
    if (isOverlay(w)) {
        // The overlay must never take the keyboard from the app.
        if (lastActive && lastActive !== w) workspace.activeWindow = lastActive;
        return;
    }
    if (w) lastActive = w;
    if (isApp(w)) {
        const me = selfWindow();
        if (me && !me.minimized) me.minimized = true;
    }
    push(null);
});

workspace.windowAdded.connect(function (w) {
    if (isOverlay(w)) { placeOverlay(w); return; }
    // New app window (not Moonfin's video layer, not popups): bring it forward.
    if (isApp(w)) workspace.activeWindow = w;
    push(null);
});
workspace.windowRemoved.connect(function (w) {
    if (isOverlay(w)) return;
    // Leaving an app (it quit or crashed) returns to Home, like Apple TV.
    if (w === lastActive && isApp(w)) { lastActive = null; goHome(); }
    push(w);
});

registerShortcut("LSBox Home", "LSBox: go to the home screen", "HomePage", function () {
    const was = isSelf(workspace.activeWindow);
    if (!was) goHome();
    callDBus(SERVICE, "/Home", SERVICE, "homeKey", was);
});
registerShortcut("LSBox Volume Up", "LSBox: volume up", "Volume Up", function () {
    callDBus(SERVICE, "/Home", SERVICE, "volumeKey", "5");
});
registerShortcut("LSBox Volume Down", "LSBox: volume down", "Volume Down", function () {
    callDBus(SERVICE, "/Home", SERVICE, "volumeKey", "-5");
});
registerShortcut("LSBox Mute", "LSBox: mute", "Volume Mute", function () {
    callDBus(SERVICE, "/Home", SERVICE, "volumeKey", "0");
});

for (const w of workspace.windowList()) { if (isOverlay(w)) placeOverlay(w); }
push(null);
