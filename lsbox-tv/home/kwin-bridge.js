// LSBox Home bridge, loaded into KWin by lsbox_home.py at start.
// Tells the home screen which windows are open and which one is in front,
// brings new app windows forward, and makes the HomePage key (CEC Home /
// Clear) come back home from any app.
const SELF_PID = __SELF_PID__;
const SERVICE = "__SERVICE__";

function isSelf(w) { return !!w && w.pid === SELF_PID; }

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
        if (w === gone || !w.normalWindow || w.skipTaskbar) continue;
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
    return !!w && w.normalWindow && !w.skipTaskbar && !isSelf(w) &&
        String(w.resourceClass || "").toLowerCase() !== "moonfin-video";
}

function goHome() {
    const me = selfWindow();
    if (me) { me.minimized = false; workspace.activeWindow = me; }
}

// The home screen is a normal window, so it would sit above Moonfin's video
// layer (a keep-below window). Minimising it while an app is in front keeps
// the movie visible, exactly like the Bigscreen desktop did.
let lastActive = null;
workspace.windowActivated.connect(function (w) {
    if (w) lastActive = w;
    if (isApp(w)) {
        const me = selfWindow();
        if (me && !me.minimized) me.minimized = true;
    }
});

workspace.windowAdded.connect(function (w) {
    // New app window (not Moonfin's video layer, not popups): bring it forward.
    if (w.normalWindow && !w.skipTaskbar && !isSelf(w) &&
        String(w.resourceClass || "").toLowerCase() !== "moonfin-video") {
        workspace.activeWindow = w;
    }
    push(null);
});
workspace.windowRemoved.connect(function (w) {
    // Leaving an app (it quit or crashed) returns to Home, like Apple TV.
    if (w === lastActive && isApp(w)) { lastActive = null; goHome(); }
    push(w);
});
workspace.windowActivated.connect(function () { push(null); });

registerShortcut("LSBox Home", "LSBox: go to the home screen", "HomePage", function () {
    const was = isSelf(workspace.activeWindow);
    if (!was) goHome();
    callDBus(SERVICE, "/Home", SERVICE, "homeKey", was);
});

push(null);
