// Runs kwin-bridge.js against a fake KWin workspace: node kwin_bridge_test.js
const fs = require("fs");
const path = require("path");
const assert = require("assert");

function signal() { const fns = []; return { connect: f => fns.push(f), emit: (...a) => fns.forEach(f => f(...a)) }; }
const wins = [];
const calls = [];
const shortcuts = {};
const workspace = {
    windowAdded: signal(), windowRemoved: signal(), windowActivated: signal(),
    windowList: () => wins.slice(),
    clientArea: () => ({ x: 0, y: 0, width: 3840, height: 2160 }),
    _active: null,
    get activeWindow() { return this._active; },
    set activeWindow(w) { this._active = w; this.windowActivated.emit(w); },
};
let n = 0;
function win(cls, pid, extra) {
    return Object.assign({ internalId: "{" + (++n) + "}", resourceClass: cls, resourceName: cls, desktopFileName: cls,
        caption: cls, pid, normalWindow: true, skipTaskbar: false, minimized: false }, extra || {});
}
const SELF = 4242;
const src = fs.readFileSync(path.join(__dirname, "../home/kwin-bridge.js"), "utf8")
    .replace("__SELF_PID__", String(SELF)).replace("__SERVICE__", "org.lsbox.Home");
const callDBus = (...a) => calls.push(a);
const registerShortcut = (name, text, keys, fn) => { shortcuts[keys] = fn; };
const KWin = { FullScreenArea: 2 };
new Function("workspace", "callDBus", "registerShortcut", "KWin", src)(workspace, callDBus, registerShortcut, KWin);
const shortcut = { fn: shortcuts["HomePage"] };

function add(w) { wins.push(w); workspace.windowAdded.emit(w); }
function remove(w) { wins.splice(wins.indexOf(w), 1); workspace.windowRemoved.emit(w); }
const lastList = () => JSON.parse(calls.filter(c => c[3] === "windows").pop()[4]);

const home = win("lsbox-home", SELF);
add(home);
workspace.activeWindow = home; // KWin focuses the home screen at login
assert.ok(shortcut.fn, "HomePage shortcut registered");

const moon = win("org.moonfin.linux", 100);
add(moon);
assert.strictEqual(workspace.activeWindow, moon, "new app comes forward");
assert.strictEqual(home.minimized, true, "home hides behind apps (keeps HDR video visible)");

const video = win("moonfin-video", 100);
add(video);
assert.strictEqual(workspace.activeWindow, moon, "video layer never takes focus");
assert.ok(lastList().some(w => w.cls === "moonfin-video"), "video window still reported");

shortcut.fn();
assert.strictEqual(workspace.activeWindow, home, "HomePage key goes home");
assert.strictEqual(home.minimized, false);
const hk = calls.filter(c => c[3] === "homeKey").pop();
assert.strictEqual(hk[4], false, "reports it was not home before");

workspace.activeWindow = moon;
assert.strictEqual(home.minimized, true);
remove(video);
assert.strictEqual(workspace.activeWindow, moon, "video window closing stays in Moonfin");
remove(moon);
assert.strictEqual(workspace.activeWindow, home, "app quitting returns home");
assert.strictEqual(home.minimized, false);
assert.ok(!lastList().some(w => w.cls === "org.moonfin.linux"), "closed window not reported");

const popup = win("steam", 7, { skipTaskbar: true });
add(popup);
assert.strictEqual(workspace.activeWindow, home, "skip-taskbar popups ignored");

// Volume keys go to the home screen as strings.
shortcuts["Volume Up"]();
shortcuts["Volume Mute"]();
const vk = calls.filter(c => c[3] === "volumeKey").map(c => c[4]);
assert.deepStrictEqual(vk, ["5", "0"], "volume keys forwarded");

// Banner overlay: kept on top, top right, never reported, never focused.
const moon2 = win("org.moonfin.linux", 100);
add(moon2);
assert.strictEqual(workspace.activeWindow, moon2);
const overlay = win("lsbox-home", SELF, { caption: "LSBox Overlay", frameGeometry: { x: 0, y: 0, width: 700, height: 360 } });
add(overlay);
assert.strictEqual(overlay.keepAbove, true, "overlay kept above");
assert.strictEqual(overlay.frameGeometry.x, 3840 - 700, "overlay at the top right");
assert.strictEqual(workspace.activeWindow, moon2, "overlay does not take focus when added");
workspace.activeWindow = overlay;  // KWin focuses it anyway
assert.strictEqual(workspace.activeWindow, moon2, "focus handed straight back to the app");
assert.strictEqual(home.minimized, true, "home stays hidden behind the app");
assert.ok(!lastList().some(w => w.caption === "LSBox Overlay"), "overlay not in the window list");
shortcut.fn();
assert.strictEqual(workspace.activeWindow, home, "Home key picks the home window, not the overlay");
remove(overlay);
assert.strictEqual(workspace.activeWindow, home, "overlay closing changes nothing");
console.log("kwin bridge: all checks passed");
