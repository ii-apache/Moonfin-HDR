#!/usr/bin/env python3
"""LSBox Home: a fast, remote-friendly home screen for the living room box.

It replaces the Plasma Bigscreen shell. KWin, the Bigscreen input handler
(CEC remote + game controller -> keys) and every app stay as they are.
See README.md for the feature list. The pieces live in lsboxkit/.

Files:
  ~/.config/lsbox-home/apps.json      which apps are on the home screen
  ~/.config/lsbox-home/state.json     order, hidden apps, settings (written by the app)
  ~/.config/lsbox-home/profiles.json  profiles (see --add-profile)
  ~/.cache/lsbox-home/                artwork + shelf cache (capped)

Commands (run as tv):
  lsbox_home.py --add-profile NAME [--jellyfin-user USER] [--kids] [--pin 1234]
  lsbox_home.py --remove-profile NAME
"""
import argparse
import getpass
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import wave
import math
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # python3 -I drops the script folder from the path

from PySide6.QtCore import (SLOT, ClassInfo, Property, QEvent, QObject, QSize, Qt,  # noqa: E402
                            QTimer, QUrl, Signal, Slot)
from PySide6.QtDBus import (QDBusConnection, QDBusInterface, QDBusMessage,  # noqa: E402
                            QDBusServiceWatcher)
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QImage, QKeyEvent, QPixmap  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickImageProvider  # noqa: E402

from lsboxkit import media, profiles as prof, steam, system, updater  # noqa: E402
from lsboxkit.desktop import App, exec_to_argv, read_desktop  # noqa: E402
from lsboxkit.images import ImageCache  # noqa: E402
from lsboxkit.jellyfin import Jellyfin  # noqa: E402
from lsboxkit.notify import NotificationServer  # noqa: E402
from lsboxkit.remote import RemoteServer  # noqa: E402
from lsboxkit.uinput import VirtualKeyboard  # noqa: E402
from lsboxkit.util import (CACHE_DIR, CONF_DIR, DEMO, RUNTIME_DIR, load_json, log,  # noqa: E402
                           run, save_json)

APP_ID = "lsbox-home"
DBUS_SERVICE = "org.lsbox.Home"
REMOTE_PORT = int(os.environ.get("LSBOX_REMOTE_PORT", "8095"))
JF_CONF = "~/.config/refresh-match/config"

SETTINGS_DEFAULT = {
    "theme": "dark",            # dark | light | artwork
    "sounds": True,             # soft clicks on Home (muted while anything plays)
    "rumble": True,             # tiny controller rumble when focus moves
    "warmMoonfin": True,        # start Moonfin hidden at login
    "resumeLast": False,        # reopen the last app after a reboot
    "autoCloseHours": 4,        # close apps unused this long (0 = never)
    "screensaverMinutes": 5,    # 0 = off
    "saverTvOffMinutes": 60,    # TV standby after this long on the screensaver (0 = never)
    "askProfile": False,        # profile picker at start
    "remote": False,            # phone remote web page
    "volumeMode": "auto",       # auto | cec | pipewire
}

KEYMAP = {"up": Qt.Key_Up, "down": Qt.Key_Down, "left": Qt.Key_Left, "right": Qt.Key_Right,
          "ok": Qt.Key_Return, "back": Qt.Key_Escape, "menu": Qt.Key_Menu,
          "playpause": Qt.Key_MediaTogglePlayPause, "next": Qt.Key_MediaNext,
          "previous": Qt.Key_MediaPrevious}
UINPUT_KEYS = {"ok": "enter", "back": "esc", "menu": "menu", "playpause": "playpause",
               "next": "next", "previous": "previous", "up": "up", "down": "down",
               "left": "left", "right": "right"}


def box_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.50.1", 9))  # no packet is sent for UDP connect
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "this box"


def image_tint(path):
    img = QImage(path)
    if img.isNull():
        return ""
    c = QColor(img.scaled(1, 1, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).pixel(0, 0))
    h, s, v, _ = c.getHsvF()
    c.setHsvF(h, min(1.0, s * 1.2), min(v, 0.45))  # keep it dark enough for white text
    return c.name()


# --------------------------------------------------------------------------
# Icons for QML: image://icon/<theme name or absolute path>
# --------------------------------------------------------------------------

class IconProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Pixmap)

    def requestPixmap(self, id, size, requested):
        name = urllib.parse.unquote(id)
        side = max(requested.width(), requested.height(), 256)
        if name.startswith("/") and os.path.exists(name):
            pm = QPixmap(name)
            if not pm.isNull():
                return pm.scaled(side, side, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon = QIcon.fromTheme(name)
        pm = QPixmap() if icon.isNull() else icon.pixmap(QSize(side, side))
        if pm.isNull():  # QML then shows the app's first letter instead
            pm = QPixmap(1, 1)
            pm.fill(QColor(0, 0, 0, 0))
        return pm


# --------------------------------------------------------------------------
# D-Bus face that KWin's bridge script (and scripts) call
# --------------------------------------------------------------------------

@ClassInfo({"D-Bus Interface": DBUS_SERVICE})
class BusApi(QObject):
    def __init__(self, home):
        super().__init__()
        self.home = home

    @Slot(str)
    def windows(self, payload):
        self.home._on_windows(payload)

    @Slot(bool)
    def homeKey(self, was_active):
        self.home._on_home(from_kwin=True, was_active=was_active)

    @Slot(str)
    def volumeKey(self, delta):  # a string: KWin scripts send numbers as doubles
        try:
            self.home.volumeStep(int(delta))
        except ValueError:
            pass

    @Slot()
    def showHome(self):  # busctl --user call org.lsbox.Home /Home org.lsbox.Home showHome
        self.home._on_home(from_kwin=False, was_active=None)


# --------------------------------------------------------------------------
# The model QML talks to
# --------------------------------------------------------------------------

class Home(QObject):
    appsChanged = Signal()
    shelfChanged = Signal()
    saverChanged = Signal()
    runningChanged = Signal()
    activeChanged = Signal()
    statusChanged = Signal()
    hiddenChanged = Signal()
    settingsChanged = Signal()
    nowPlayingChanged = Signal()
    profilesChanged = Signal()
    sinksChanged = Signal()
    btChanged = Signal()
    displayChanged = Signal()
    healthChanged = Signal()
    sleepChanged = Signal()
    remoteChanged = Signal()
    volumeChanged = Signal()
    searchChanged = Signal()
    updateChanged = Signal()
    homeAgain = Signal()      # Home pressed while already home
    homeShown = Signal()      # came back home from an app
    homeDouble = Signal()     # Home pressed twice: app switcher
    launchFailed = Signal(str)
    banner = Signal(str, str, str)   # title, body, icon
    volumeShown = Signal()
    remoteText = Signal(str)
    _done = Signal(object, object)    # (callback, result) from worker threads
    _remote = Signal(str, str)

    def __init__(self):
        super().__init__()
        os.makedirs(RUNTIME_DIR, exist_ok=True)
        self.window = None
        self.cfg = load_json(os.path.join(CONF_DIR, "apps.json"), None) or load_json(
            os.path.join(HERE, "apps.json"), {"apps": []})
        self.state = load_json(os.path.join(CONF_DIR, "state.json"), {})
        self._migrate_state()
        s = dict(SETTINGS_DEFAULT)
        s["screensaverMinutes"] = int(self.cfg.get("screensaver_minutes", s["screensaverMinutes"]))
        s.update(self.state.get("settings", {}))
        self.state["settings"] = s
        self.apps = {}
        self._build_apps()
        self.profile_list = prof.load()
        if self.state.get("profile") not in [p["name"] for p in self.profile_list]:
            self.state["profile"] = self.profile_list[0]["name"]

        self._windows = []
        self._active = True
        self._last_home = 0.0
        self._rows = load_json(os.path.join(CACHE_DIR, "shelf.json"), {}) if not DEMO else {}
        self._saver = []
        self._status = {"airplay": "", "storage": "", "jellyfin": ""}
        self._np = {"active": False}
        self._sinks, self._bt, self._display, self._health = [], [], {}, {}
        self._bt_busy = ""
        self._sleep = {"mode": "off", "endsAt": 0, "label": "Off"}
        self._volume = {"level": -1, "muted": False, "mode": ""}
        self._search, self._search_busy = [], False
        self._update = {"state": "idle", "message": ""}
        self._script_n = 0
        self._warm_pending = set()
        self._last_used = {}
        self._last_shelf = 0.0
        self._np_tick = 0
        self._seen_windows = set()
        self._battery_warned = set()
        self._sleep_item = None
        self._volume_mode = None
        self.remote_server = None
        self.vkbd = None
        self.click = None

        self.jf = self._jellyfin_for_profile()
        self.cache = ImageCache(self.jf.ctx, image_tint, allowed=[self.jf.url])
        self.spotify_history = media.SpotifyHistory()
        self._done.connect(lambda cb, res: cb(res))
        self._remote.connect(self._on_remote)

        self.bus = QDBusConnection.sessionBus()
        self.api = BusApi(self)
        self.notifications = NotificationServer()
        self.notifications.banner.connect(self.banner)
        if self.bus.isConnected() and not DEMO:
            self.bus.registerObject("/Home", self.api, QDBusConnection.ExportAllSlots)
            if not self.bus.registerService(DBUS_SERVICE):
                log("another LSBox Home already owns", DBUS_SERVICE)
            # Xbox button / CEC menu keys from the Bigscreen input handler
            self.bus.connect("", "/InputHandler", "org.kde.plasma.bigscreen.inputhandler",
                             "homeActionRequested", self, SLOT("_on_input_home()"))
            # Desktop notifications (nothing else shows them without the Plasma shell)
            if self.bus.registerObject("/org/freedesktop/Notifications", self.notifications,
                                       QDBusConnection.ExportAllSlots | QDBusConnection.ExportAllSignals):
                if not self.bus.registerService("org.freedesktop.Notifications"):
                    log("notifications: another server is running, leaving it be")
            # KWin restarted? Load the bridge again.
            self.kwin_watch = QDBusServiceWatcher("org.kde.KWin", self.bus,
                                                  QDBusServiceWatcher.WatchForRegistration, self)
            self.kwin_watch.serviceRegistered.connect(lambda _n: QTimer.singleShot(1500, self._load_bridge))

        QTimer.singleShot(0, self._load_bridge)
        QTimer.singleShot(150, self.refreshShelf)
        QTimer.singleShot(400, self.refreshStatus)
        QTimer.singleShot(20000, self._warm_up)
        QTimer.singleShot(5000, self._resume_last)
        QTimer.singleShot(1000, self._setup_click)
        QTimer.singleShot(30000, self._confirm_update)
        if self.settings_["remote"]:
            QTimer.singleShot(1500, lambda: self._remote_enable(True))
        self._every(10 * 60 * 1000, self._tick)
        self._every(5 * 60 * 1000, self._auto_close)
        self._every(10 * 60 * 1000, self._check_batteries)
        self.np_timer = self._every(2000, self._poll_np)
        if DEMO:
            self._demo_data()

    def _every(self, ms, fn):
        t = QTimer(self)
        t.timeout.connect(fn)
        t.start(ms)
        return t

    def _bg(self, fn, cb=None):
        """Run fn() in a worker thread, then cb(result) back on the UI thread."""
        def work():
            try:
                res = fn()
            except Exception as e:  # never take the home screen down
                log("background task failed:", type(e).__name__, e)
                res = None
            if cb:
                self._done.emit(cb, res)
        threading.Thread(target=work, daemon=True).start()

    # ---------------- state + settings
    def _migrate_state(self):
        st = self.state
        st.setdefault("profiles", {})
        if "order" in st or "hidden" in st:  # version 1 kept these at the top
            st["profiles"].setdefault("Home", {"order": st.pop("order", []), "hidden": st.pop("hidden", [])})

    def _save_state(self):
        try:
            save_json(os.path.join(CONF_DIR, "state.json"), self.state, mode=0o600)
        except OSError as e:
            log("state not saved:", e)

    def _pstate(self):
        return self.state["profiles"].setdefault(self.state["profile"], {"order": [], "hidden": []})

    @property
    def settings_(self):
        return self.state["settings"]

    @Property("QVariantMap", notify=settingsChanged)
    def settings(self):
        return self.settings_

    @Slot(str, "QVariant")
    def setSetting(self, key, value):
        if key not in SETTINGS_DEFAULT:
            return
        if isinstance(SETTINGS_DEFAULT[key], bool):
            value = bool(value)
        elif isinstance(SETTINGS_DEFAULT[key], int):
            value = int(value)
        self.settings_[key] = value
        self._save_state()
        self.settingsChanged.emit()
        if key == "remote":
            self._remote_enable(value)
        if key == "volumeMode":
            self._volume_mode = None

    # ---------------- apps
    def _build_apps(self):
        self.apps = {}
        for c in self.cfg.get("apps", []):
            a = App(c)
            if a.available:
                self.apps[a.key] = a
            else:
                log("not installed, skipped:", a.name)

    def _profile(self):
        return next((p for p in self.profile_list if p["name"] == self.state["profile"]), self.profile_list[0])

    def _allowed(self, key):
        p = self._profile()
        return not p.get("kids") or key in p.get("apps", [])

    def _ordered(self):
        ps = self._pstate()
        keys = [k for k in self.apps if self._allowed(k)]
        order = [k for k in ps.get("order", []) if k in keys]
        order += [k for k in keys if k not in order]
        hidden = set(ps.get("hidden", []))
        return [k for k in order if k not in hidden]

    def _running_keys(self):
        r = set()
        for w in self._windows:
            for a in self.apps.values():
                if a.owns(w):
                    r.add(a.key)
        return r

    def _app_qml(self, a, running):
        art = ""
        rows = self._rows.get(a.key) or []
        if rows and rows[0].get("items"):
            first = rows[0]["items"][0]
            art = first.get("backdrop") or first.get("thumb") or ""
        return {"key": a.key, "name": a.name, "icon": a.icon, "color1": a.color1, "color2": a.color2,
                "image": QUrl.fromLocalFile(os.path.expanduser(a.image)).toString() if a.image else "",
                "art": art, "tagline": a.tagline, "shelf": a.shelf, "builtin": a.builtin,
                "running": running}

    @Property("QVariantList", notify=appsChanged)
    def apps_(self):
        running = self._running_keys()
        return [self._app_qml(self.apps[k], k in running) for k in self._ordered()]

    @Property("QVariantList", notify=hiddenChanged)
    def hidden(self):
        return [self._app_qml(self.apps[k], False) for k in self._pstate().get("hidden", []) if k in self.apps]

    @Property("QVariantList", notify=runningChanged)
    def running(self):
        out = []
        for w in self._windows:
            if w.get("pid") == os.getpid() or w.get("cls", "").lower() == "moonfin-video":
                continue
            owner = next((a for a in self.apps.values() if a.owns(w)), None)
            if owner and any(o.get("key") == owner.key for o in out):
                continue
            d = self._app_qml(owner, True) if owner else {
                "key": "", "name": w.get("caption") or w.get("cls") or "App",
                "icon": w.get("desktop") or w.get("cls") or "application-x-executable",
                "color1": "#2b2f3a", "color2": "#4a5161", "image": "", "art": "", "running": True}
            d["wid"] = w.get("id", "")
            d["pid"] = w.get("pid", 0)
            out.append(d)
        return out

    @Property(bool, notify=activeChanged)
    def launcherActive(self):
        return self._active

    @Property("QVariantMap", notify=shelfChanged)
    def shelfRows(self):
        return self._rows

    @Property("QVariantList", notify=saverChanged)
    def saver(self):
        return self._saver

    @Property("QVariantMap", notify=statusChanged)
    def status(self):
        return self._status

    @Property(bool, constant=True)
    def demo(self):
        return DEMO

    @Property(int, notify=settingsChanged)
    def saverMinutes(self):
        return int(self.settings_.get("screensaverMinutes", 5) or 0)

    @Slot()
    def showHome(self):
        self._on_home(from_kwin=False, was_active=None)

    @Slot(str)
    def launch(self, key):
        a = self.apps.get(key)
        if not a or not self._allowed(key):
            return
        wins = [w for w in self._windows if a.owns(w)]
        if wins:
            self._activate_window(wins[-1]["id"])
            return
        self._spawn(a.argv, a.key)

    @Slot("QVariantMap", bool)
    def openCard(self, card, play):
        kind, cid = card.get("kind"), card.get("id")
        if not cid:
            return
        if kind == "jellyfin":
            moonfin = next((a for a in self.apps.values() if a.shelf == "jellyfin"), None)
            if not moonfin:
                return
            q = {"id": cid}
            uid = self._profile().get("user_id")
            if uid:
                q["userId"] = uid
            url = f"moonfin://{'play' if play else 'item'}?{urllib.parse.urlencode(q)}"
            # Moonfin is single-instance: a running copy gets the link forwarded.
            self._spawn(moonfin.argv + [url], moonfin.key)
            self._raise_app(moonfin)
        elif kind == "spotify":
            sp = self.apps.get("spotify")
            players = [p for p in media.poll() if p["source"] == "spotify"] if not DEMO else []
            if players:
                run(["playerctl", "-p", players[0]["player"], "open", cid], timeout=3)
                if sp:
                    self._raise_app(sp)
            elif sp:
                self._spawn(sp.argv + [f"--uri={cid}"], sp.key)
        elif kind == "steam":
            st = self.apps.get("steam")
            if st:
                argv = [a for a in st.argv if not a.startswith("steam://")] + [f"steam://rungameid/{cid}"]
                self._spawn(argv, st.key)
                self._raise_app(st)

    def _raise_app(self, a):
        wins = [w for w in self._windows if a.owns(w)]
        if wins:
            self._activate_window(wins[-1]["id"])

    def _spawn(self, argv, key):
        if DEMO or not argv:
            log("launch", argv)
            return
        unit = f"lsbox-{key}-{int(time.time() * 1000) % 100000000}"
        if run(["which", "systemd-run"], timeout=2)[0] == 0:
            # Own unit: logs go to the journal and the app survives a restart
            # of the home screen.  journalctl --user -u 'lsbox-<app>-*'
            cmd = ["systemd-run", "--user", "--collect", "--quiet", "--slice=app.slice",
                   f"--unit={unit}", "-p", "ExitType=cgroup", "--"] + argv
        else:
            cmd = argv
        try:
            subprocess.Popen(cmd, start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log("launch", key, argv)
        except OSError as e:
            log("launch failed", key, e)
            self.launchFailed.emit(key)

    @Slot(str)
    def activateWindow(self, wid):
        self._activate_window(wid)

    @Slot(str)
    def closeWindow(self, wid):
        self._kwin(_JS_CLOSE % json.dumps(wid))

    @Slot(str)
    def closeApp(self, key):
        a = self.apps.get(key)
        if not a:
            return
        for w in self._windows:
            if a.owns(w):
                self.closeWindow(w["id"])
        # Units we started for it go too, after a grace period.
        QTimer.singleShot(4000, lambda: self._stop_units(key))

    @Slot(str)
    def forceClose(self, key):
        """For a frozen app: kill it outright."""
        a = self.apps.get(key)
        pids = {w.get("pid") for w in self._windows if a and a.owns(w)}
        for pid in pids:
            if pid and pid != os.getpid():
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
        run(["systemctl", "--user", "kill", "-s", "KILL", f"lsbox-{key}-*.service"], timeout=3)
        self.banner.emit("Closed " + (a.name if a else key), "", "")

    @Slot(int)
    def forceClosePid(self, pid):
        if pid and pid != os.getpid():
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    @Slot()
    def closeAll(self):
        for w in list(self._windows):
            if w.get("pid") != os.getpid() and w.get("cls", "").lower() != "moonfin-video":
                self.closeWindow(w["id"])

    def _stop_units(self, key):
        a = self.apps.get(key)
        if a and any(a.owns(w) for w in self._windows):
            subprocess.Popen(["systemctl", "--user", "stop", f"lsbox-{key}-*.service"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @Slot(str, int)
    def moveApp(self, key, delta):
        order = self._ordered()
        if key not in order:
            return
        i = order.index(key)
        j = max(0, min(len(order) - 1, i + delta))
        if i == j:
            return
        order.insert(j, order.pop(i))
        ps = self._pstate()
        ps["order"] = order + [k for k in ps.get("order", []) if k not in order]
        self._save_state()
        self.appsChanged.emit()

    @Slot(str)
    def hideApp(self, key):
        h = self._pstate().setdefault("hidden", [])
        if key not in h:
            h.append(key)
        self._save_state()
        self.appsChanged.emit()
        self.hiddenChanged.emit()

    @Slot()
    def unhideAll(self):
        self._pstate()["hidden"] = []
        self._save_state()
        self.appsChanged.emit()
        self.hiddenChanged.emit()

    # ---------------- system actions
    def _inputhandler(self, method, *args, asynchronous=False):
        if DEMO or not self.bus.isConnected():
            return None
        iface = QDBusInterface("org.kde.plasma.bigscreen.inputhandler", "/InputHandler",
                               "org.kde.plasma.bigscreen.inputhandler", self.bus)
        if not iface.isValid():
            return None
        if asynchronous:
            iface.asyncCall(method, *args)
            return None
        r = iface.call(method, *args)
        return r.arguments()[0] if r.type() == QDBusMessage.ReplyMessage and r.arguments() else None

    @Slot()
    def tvOff(self):
        self._inputhandler("sendStandby", 0)

    @Slot()
    def openSettings(self):
        if "settings" in self.apps:
            self.launch("settings")
            return
        for cand in ("org.kde.plasma.bigscreen.settings", "systemsettings"):
            e = read_desktop(cand)
            if e:
                self._spawn(exec_to_argv(e.get("Exec", "")), "settings")
                return

    @Slot()
    def reboot(self):
        self._spawn(["systemctl", "reboot"], "reboot")

    @Slot()
    def restartHome(self):
        if DEMO:
            return
        # systemd restarts us (Restart=always); apps live in their own units.
        QGuiApplication.quit()

    @Slot()
    def refreshStatus(self):
        def work():
            st = {}
            h = system.health() if not DEMO else {}
            if h:
                st["storage"] = h.get("diskText", "") + " used"
            if DEMO:
                st["airplay"] = "Ready as LSBox"
            else:
                code, out = run(["systemctl", "--user", "is-active", "uxplay.service"], timeout=2)
                st["airplay"] = "Ready as LSBox" if out.strip() == "active" else "Off"
            return st

        def done(st):
            if st:
                self._status.update(st)
                self.statusChanged.emit()
        self._bg(work, done)

    # ---------------- profiles
    def _jellyfin_for_profile(self):
        p = self._profile()
        return Jellyfin(self.cfg.get("jellyfin_config", JF_CONF), p.get("token_file"))

    @Property("QVariantList", notify=profilesChanged)
    def profiles(self):
        return [prof.public(p, p["name"] == self.state["profile"]) for p in self.profile_list]

    @Property("QVariantMap", notify=profilesChanged)
    def profile(self):
        p = self._profile()
        return prof.public(p, True)

    @Slot(str, str, result=bool)
    def switchProfile(self, name, pin):
        target = next((p for p in self.profile_list if p["name"] == name), None)
        if not target:
            return False
        # A PIN is needed to go to a protected profile, unless you are leaving
        # a grown-up profile for a kids one.
        if target.get("pin") and not prof.check_pin(target["pin"], pin):
            return False
        self.state["profile"] = name
        self._save_state()
        self.jf = self._jellyfin_for_profile()
        self.cache.allowed = [self.jf.url.rstrip("/") + "/"] if self.jf.url else []
        self._rows, self._saver, self._last_shelf = {}, [], 0.0
        self.profilesChanged.emit()
        self.appsChanged.emit()
        self.hiddenChanged.emit()
        self.shelfChanged.emit()
        self.refreshShelf()
        return True

    # ---------------- shelf
    @Slot()
    def refreshShelf(self, force=False):
        if DEMO:
            return
        if time.monotonic() - self._last_shelf < 60 and self._rows and not force:
            return
        self._last_shelf = time.monotonic()
        jf_ok = self.jf.ok
        if not jf_ok:
            self._status["jellyfin"] = "Top shelf off: no ~/.config/refresh-match/config"
            self.statusChanged.emit()
        keys = {a.shelf: a.key for a in self.apps.values() if a.shelf}

        def work():
            rows = {}
            if jf_ok and "jellyfin" in keys:
                try:
                    r = self.jf.rows()
                    for row in r:
                        row["items"] = [self.cache.localize(c) for c in row["items"]]
                    rows[keys["jellyfin"]] = r
                except Exception as e:
                    log("jellyfin:", type(e).__name__, e)
            if "spotify" in keys:
                r = self.spotify_history.rows()
                for row in r:
                    row["items"] = [self.cache.localize(c) for c in row["items"]]
                rows[keys["spotify"]] = r
            if "steam" in keys:
                r = steam.rows()
                for row in r:
                    row["items"] = [self.cache.localize(c) for c in row["items"]]
                rows[keys["steam"]] = r
            saver = []
            if jf_ok and not self._saver:
                try:
                    saver = [self.cache.localize(c, ("backdrop", "logo")) for c in self.jf.saver()]
                    saver = [c for c in saver if c["backdrop"]]
                except Exception as e:
                    log("jellyfin saver:", type(e).__name__, e)
            self.cache.prune()
            return rows, saver

        self._bg(work, self._set_shelf)

    def _set_shelf(self, res):
        if not res:
            return
        rows, saver = res
        moonfin = next((a.key for a in self.apps.values() if a.shelf == "jellyfin"), None)
        if moonfin and moonfin in rows:
            self._note_new_items(rows[moonfin])
        if rows:
            self._rows.update(rows)
            self.shelfChanged.emit()
            self.appsChanged.emit()  # live tile art
            try:
                save_json(os.path.join(CACHE_DIR, "shelf.json"), self._rows)
            except OSError:
                pass
        if saver:
            self._saver = saver
            self.saverChanged.emit()

    def _note_new_items(self, rows):
        recent = next((r for r in rows if r["title"] == "Recently Added"), None)
        if not recent:
            return
        ids = [c["id"] for c in recent["items"]]
        seen = self.state.get("seenRecent")
        self.state["seenRecent"] = ids[:40]
        self._save_state()
        if seen is None:
            return  # first run: nothing is "new"
        new = [c for c in recent["items"] if c["id"] not in seen][:3]
        for c in new:
            self.banner.emit("New in Jellyfin", c["title"], "")

    def _tick(self):
        self._saver = []  # new random set next time
        self.refreshShelf(force=True)
        self.refreshStatus()

    # ---------------- search
    @Property("QVariantList", notify=searchChanged)
    def searchResults(self):
        return self._search

    @Property(bool, notify=searchChanged)
    def searchBusy(self):
        return self._search_busy

    @Slot(str)
    def search(self, text):
        text = text.strip()
        if not text:
            self._search = []
            self.searchChanged.emit()
            return
        if DEMO:
            self._search = [dict(c, group="Search") for c in self._rows.get("moonfin", [{}])[0].get("items", [])
                            if text.lower() in c["title"].lower()]
            self.searchChanged.emit()
            return
        if not self.jf.ok:
            return
        self._search_busy = True
        self.searchChanged.emit()
        query = text

        def work():
            return query, [self.cache.localize(c, ("thumb", "backdrop")) for c in self.jf.search(query)]

        def done(res):
            self._search_busy = False
            if res:
                self._search = res[1]
            self.searchChanged.emit()
        self._bg(work, done)

    # ---------------- now playing
    @Property("QVariantMap", notify=nowPlayingChanged)
    def nowPlaying(self):
        return self._np

    def _poll_np(self):
        self._np_tick += 1
        # Every 2 s on Home, every 10 s behind an app (auto-close + sleep timer).
        if not self._active and self._np_tick % 5:
            return
        if DEMO:
            return
        want_jf = self.jf.ok and (self._active or self._sleep["mode"] == "episode")

        def work():
            players = media.poll()
            sess = None
            if want_jf:
                try:
                    s = self.jf.box_session()
                    sess = self.jf.session_info(s) if s else None
                    if sess:
                        sess["art"] = self.cache.local(sess["art"])
                except Exception:
                    sess = None
            for p in players:
                if p["art"].startswith("http"):
                    p["art"] = self.cache.local(p["art"])
            return players, sess

        self._bg(work, self._set_np)

    def _set_np(self, res):
        if not res:
            return
        players, sess = res
        for p in players:
            if p["source"] == "spotify" and self.spotify_history.note(p):
                self._last_shelf = 0.0
        pick = sess if sess and sess["playing"] else (media.pick(players) or sess)
        np = pick or {"active": False}
        if np.get("appKey"):
            self._last_used[np["appKey"]] = time.time()  # playing counts as in use
        # Sleep timer "end of episode": the item changed or playback stopped.
        if self._sleep["mode"] == "episode":
            cur = sess["itemId"] if sess else None
            if self._sleep_item is None and cur:
                self._sleep_item = cur
            elif self._sleep_item and cur != self._sleep_item:
                self._sleep_fire()
        if np != self._np:
            self._np = np
            self.nowPlayingChanged.emit()

    @Slot(str)
    def npControl(self, action):
        """toggle, next, previous"""
        np = self._np
        if not np.get("active") or DEMO:
            if DEMO and np.get("active"):
                self._np = dict(np, playing=not np["playing"]) if action == "toggle" else np
                self.nowPlayingChanged.emit()
            return
        if np.get("source") == "moonfin" and np.get("sessionId"):
            cmd = {"toggle": "PlayPause", "next": "FastForward", "previous": "Rewind"}[action]
            sid = np["sessionId"]
            self._bg(lambda: self.jf.playstate(sid, cmd), lambda _r: self._poll_np())
        elif np.get("player"):
            act = {"toggle": "play-pause", "next": "next", "previous": "previous"}[action]
            player = np["player"]
            self._bg(lambda: media.control(player, act), lambda _r: self._poll_np())

    @Slot()
    def npOpen(self):
        key = self._np.get("appKey")
        if key in self.apps:
            self.launch(key)

    def _pause_everything(self):
        if DEMO:
            return
        run(["playerctl", "-a", "pause"], timeout=3)
        np = self._np
        if np.get("source") == "moonfin" and np.get("sessionId") and np.get("playing"):
            try:
                self.jf.playstate(np["sessionId"], "Pause")
            except Exception:
                pass

    # ---------------- sleep timer
    @Property("QVariantMap", notify=sleepChanged)
    def sleepTimer(self):
        return self._sleep

    @Slot(str)
    def setSleepTimer(self, mode):
        if not hasattr(self, "_sleep_timer"):
            self._sleep_timer = QTimer(self)
            self._sleep_timer.setSingleShot(True)
            self._sleep_timer.timeout.connect(self._sleep_fire)
        self._sleep_timer.stop()
        self._sleep_item = None
        if mode in ("30", "60", "90", "120"):
            mins = int(mode)
            self._sleep_timer.start(mins * 60000)
            self._sleep = {"mode": mode, "endsAt": int((time.time() + mins * 60) * 1000),
                           "label": f"{mins} minutes"}
        elif mode == "episode":
            self._sleep = {"mode": "episode", "endsAt": 0, "label": "End of this episode"}
        else:
            self._sleep = {"mode": "off", "endsAt": 0, "label": "Off"}
        self.sleepChanged.emit()

    def _sleep_fire(self):
        log("sleep timer: pausing and turning the TV off")
        self._bg(self._pause_everything)
        self.tvOff()
        self._sleep = {"mode": "off", "endsAt": 0, "label": "Off"}
        self._sleep_item = None
        self.sleepChanged.emit()

    # ---------------- volume
    @Property("QVariantMap", notify=volumeChanged)
    def volume(self):
        return self._volume

    def _pick_volume_mode(self):
        if self._volume_mode:
            return self._volume_mode
        mode = self.settings_.get("volumeMode", "auto")
        if mode == "auto":
            status = self._inputhandler("queryAudioStatus")
            mode = "cec" if system.cec_status_to_volume(status) else "pipewire"
        self._volume_mode = mode
        return mode

    @Slot(int)
    def volumeStep(self, delta):
        """delta in percent; 0 toggles mute."""
        if DEMO:
            lvl = self._volume.get("level", 40)
            lvl = 40 if lvl < 0 else lvl
            self._volume = {"level": max(0, min(100, lvl + delta)), "muted": delta == 0 and not self._volume.get("muted"),
                            "mode": "pipewire"}
            self.volumeChanged.emit()
            self.volumeShown.emit()
            return
        mode = self._pick_volume_mode()
        if mode == "cec":
            method = "sendMuteToggle" if delta == 0 else ("sendVolumeUp" if delta > 0 else "sendVolumeDown")
            v = system.cec_status_to_volume(self._inputhandler(method))
            if v:
                self._volume = dict(v, mode="cec")
                self.volumeChanged.emit()
            self.volumeShown.emit()
            return

        def done(v):
            if v:
                self._volume = dict(v, mode="pipewire")
                self.volumeChanged.emit()
            self.volumeShown.emit()
        self._bg(lambda: system.pw_step(delta), done)

    # ---------------- sound output
    @Property("QVariantList", notify=sinksChanged)
    def sinks(self):
        return self._sinks

    @Slot()
    def refreshSinks(self):
        if DEMO:
            return

        def done(s):
            self._sinks = s or []
            self.sinksChanged.emit()
        self._bg(system.sinks, done)

    @Slot(str)
    def setSink(self, name):
        if DEMO:
            self._sinks = [dict(s, active=s["name"] == name) for s in self._sinks]
            self.sinksChanged.emit()
            return
        self._bg(lambda: system.set_sink(name), lambda _r: self.refreshSinks())

    # ---------------- bluetooth
    @Property("QVariantList", notify=btChanged)
    def btDevices(self):
        return self._bt

    @Property(str, notify=btChanged)
    def btBusy(self):
        return self._bt_busy

    def _bt_set(self, devs):
        self._bt = devs or []
        self._bt_busy = ""
        self.btChanged.emit()

    @Slot()
    def btRefresh(self):
        if not DEMO:
            self._bg(system.bt_devices, self._bt_set)

    @Slot()
    def btScan(self):
        if DEMO or self._bt_busy:
            return
        self._bt_busy = "Looking for devices. Put yours in pairing mode."
        self.btChanged.emit()
        # show results as they arrive
        self._bg(lambda: (system.bt_scan(15), system.bt_devices())[1], self._bt_set)
        QTimer.singleShot(5000, self.btRefresh)
        QTimer.singleShot(10000, self.btRefresh)

    @Slot(str, str)
    def btAction(self, action, mac):
        """pair, connect, disconnect, remove"""
        if DEMO:
            return
        name = next((d["name"] for d in self._bt if d["mac"] == mac), mac)
        self._bt_busy = {"pair": "Pairing", "connect": "Connecting", "disconnect": "Disconnecting",
                         "remove": "Forgetting"}.get(action, "Working") + " " + name + "..."
        self.btChanged.emit()

        def work():
            if action == "pair":
                ok = system.bt_pair(mac)
                self._done.emit(lambda _r: self.banner.emit(
                    "Bluetooth", (name + (" connected" if ok else " did not pair. Try again in pairing mode.")), ""), None)
            else:
                system.bt_action(action, mac)
            return system.bt_devices()
        self._bg(work, self._bt_set)

    # ---------------- picture
    @Property("QVariantMap", notify=displayChanged)
    def display(self):
        return self._display

    @Slot()
    def refreshDisplay(self):
        if DEMO:
            return

        def done(d):
            self._display = d or {}
            self.displayChanged.emit()
        self._bg(system.display, done)

    @Slot(str, "QVariant")
    def setDisplay(self, what, value):
        if DEMO:
            self._display = dict(self._display, **{what: value})
            self.displayChanged.emit()
            return
        d = dict(self._display)
        self._bg(lambda: system.set_display(d, what, value), lambda _r: QTimer.singleShot(800, self.refreshDisplay))

    # ---------------- health
    @Property("QVariantMap", notify=healthChanged)
    def health(self):
        return self._health

    @Slot()
    def refreshHealth(self):
        if DEMO:
            return

        def done(h):
            self._health = h or {}
            self.healthChanged.emit()
        self._bg(system.health, done)

    def _check_batteries(self):
        if DEMO:
            return

        def done(bats):
            for name, pct in bats or []:
                if pct <= 20 and name not in self._battery_warned:
                    self._battery_warned.add(name)
                    self.banner.emit("Battery low", f"{name}: {pct}%", "battery-low")
                elif pct > 30:
                    self._battery_warned.discard(name)
        self._bg(system.controller_batteries, done)

    # ---------------- feedback (rumble + click)
    def _setup_click(self):
        if not self.settings_.get("sounds"):
            return
        try:
            from PySide6.QtMultimedia import QSoundEffect
        except ImportError:
            log("click sounds need QtMultimedia; skipped")
            return
        path = os.path.join(CACHE_DIR, "click.wav")
        if not os.path.exists(path):
            os.makedirs(CACHE_DIR, exist_ok=True)
            rate, n = 48000, 1300
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(rate)
                frames = b"".join(struct.pack("<h", int(5200 * math.sin(2 * math.pi * 1900 * i / rate)
                                                        * math.exp(-i / 180))) for i in range(n))
                w.writeframes(frames)
        self.click = QSoundEffect(self)
        self.click.setSource(QUrl.fromLocalFile(path))
        self.click.setVolume(0.35)

    @Slot()
    def feedback(self):
        if self.settings_.get("rumble"):
            self._inputhandler("sendSdlControllerRumble", 0, 9000, 18, asynchronous=True)
        # Never click while anything is playing or paused: a sound could take
        # the HDMI audio device away from Moonfin's passthrough.
        if self.click and self.settings_.get("sounds") and not self._np.get("active"):
            self.click.play()

    # ---------------- phone remote
    @Property("QVariantMap", notify=remoteChanged)
    def remote(self):
        on = bool(self.remote_server and self.remote_server.httpd)
        return {"enabled": bool(self.settings_.get("remote")), "running": on,
                "url": f"http://{box_ip()}:{REMOTE_PORT}" if on or DEMO else "",
                "pin": self.state.get("remotePin", "") if on or DEMO else "",
                "keyboard": bool(self.vkbd and self.vkbd.ok)}

    def _remote_enable(self, on):
        if on and not self.remote_server:
            if not self.state.get("remotePin"):
                self.state["remotePin"] = f"{secrets.randbelow(10000):04d}"
                self._save_state()
            if DEMO:
                self.remoteChanged.emit()
                return
            self.vkbd = VirtualKeyboard()
            self.remote_server = RemoteServer(
                REMOTE_PORT, self.state["remotePin"], self.state.get("remoteTokens", []),
                handler=lambda k, v: self._remote.emit(k, v),
                state=self._remote_state, save_tokens=self._save_tokens)
            if not self.remote_server.start():
                log("phone remote: port", REMOTE_PORT, "busy")
        elif not on and self.remote_server:
            self.remote_server.stop()
            self.remote_server = None
            if self.vkbd:
                self.vkbd.close()
                self.vkbd = None
        self.remoteChanged.emit()

    @Slot()
    def newRemotePin(self):
        """New code and forget every paired phone."""
        self.state["remotePin"] = f"{secrets.randbelow(10000):04d}"
        self.state["remoteTokens"] = []
        self._save_state()
        if self.remote_server:
            self.remote_server.pin = self.state["remotePin"]
            self.remote_server.tokens = set()
            self.remote_server.total_fails = 0
        self.remoteChanged.emit()

    def _save_tokens(self, tokens):
        self.state["remoteTokens"] = tokens[-10:]
        self._done.emit(lambda _r: self._save_state(), None)

    def _remote_state(self):
        return {"apps": [{"key": k, "name": self.apps[k].name} for k in self._ordered()],
                "nowPlaying": {k: self._np.get(k) for k in ("active", "title", "artist", "playing")},
                "home": self._active}

    def _on_remote(self, kind, value):
        if kind == "app":
            self.launch(value)
        elif kind == "text":
            if self._active:
                self.remoteText.emit(value)
            elif self.vkbd and self.vkbd.ok:
                self.vkbd.type_text(value)
        elif kind == "key":
            if value == "home":
                self.showHome()
            elif value in ("volumeup", "volumedown", "mute"):
                self.volumeStep({"volumeup": 5, "volumedown": -5, "mute": 0}[value])
            elif self._active and self.window is not None:
                k = KEYMAP[value]
                target = self.window.activeFocusItem() or self.window
                QGuiApplication.sendEvent(target, QKeyEvent(QEvent.KeyPress, k, Qt.NoModifier))
                QGuiApplication.sendEvent(target, QKeyEvent(QEvent.KeyRelease, k, Qt.NoModifier))
            elif self.vkbd and self.vkbd.ok:
                self.vkbd.tap(UINPUT_KEYS.get(value, value))

    # ---------------- updates
    @Property("QVariantMap", notify=updateChanged)
    def update(self):
        return self._update

    @Slot()
    def checkUpdate(self):
        if DEMO:
            self._update = {"state": "uptodate", "message": "Up to date"}
            self.updateChanged.emit()
            return
        self._update = {"state": "checking", "message": "Checking..."}
        self.updateChanged.emit()

        def done(r):
            self._update = r or {"state": "error", "message": "Check failed"}
            self.updateChanged.emit()
        self._bg(updater.check, done)

    @Slot()
    def applyUpdate(self):
        if DEMO or self._update.get("state") != "available":
            return
        self._update = dict(self._update, state="updating", message="Updating...")
        self.updateChanged.emit()

        def done(r):
            ok, msg = r or (False, "update failed")
            if ok:
                log("update applied, restarting")
                QTimer.singleShot(300, QGuiApplication.quit)
            else:
                self._update = {"state": "error", "message": msg}
                self.updateChanged.emit()
        self._bg(updater.apply, done)

    def _confirm_update(self):
        if not DEMO and os.path.exists(updater.PENDING):
            updater.confirm_good()
            log("update confirmed good")
            self.banner.emit("Home screen updated", self._update.get("message", ""), "")

    # ---------------- auto close + resume + warm
    def _auto_close(self):
        hours = self.settings_.get("autoCloseHours", 0)
        if not hours or DEMO:
            return
        now = time.time()
        keep = {a.key for a in self.apps.values() if a.keep_warm}
        active = next((w for w in self._windows if w.get("active")), None)
        for key in self._running_keys():
            a = self.apps[key]
            if key in keep or (active and a.owns(active)) or self._np.get("appKey") == key:
                continue
            last = self._last_used.setdefault(key, now)
            if now - last > hours * 3600:
                log("auto-close (unused", hours, "h):", key)
                self.closeApp(key)

    def _resume_last(self):
        key = self.state.get("lastApp")
        if self.settings_.get("resumeLast") and key in self.apps and key not in self._running_keys():
            self.launch(key)

    def _warm_up(self):
        if not self.settings_.get("warmMoonfin"):
            return
        for a in self.apps.values():
            if a.keep_warm and not any(a.owns(w) for w in self._windows):
                self._warm_pending.add(a.key)
                self._spawn(a.argv, a.key)
        if self._warm_pending:
            QTimer.singleShot(60000, self._warm_pending.clear)

    # ---------------- KWin
    def _kwin(self, js, keep=False, name=None):
        if DEMO or not self.bus.isConnected():
            return None
        self._script_n += 1
        name = name or f"lsbox-cmd-{os.getpid()}-{self._script_n}"
        path = os.path.join(RUNTIME_DIR, name + ".js")
        with open(path, "w") as f:
            f.write(js)
        scripting = QDBusInterface("org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting", self.bus)
        if keep:
            scripting.call("unloadScript", name)
        r = scripting.call("loadScript", path, name)
        if r.type() != QDBusMessage.ReplyMessage or not r.arguments():
            log("kwin loadScript failed:", r.errorMessage())
            return None
        sid = r.arguments()[0]
        ok = False
        for obj in (f"/Scripting/Script{sid}", f"/{sid}"):
            s = QDBusInterface("org.kde.KWin", obj, "org.kde.kwin.Script", self.bus)
            if s.isValid() and s.call("run").type() == QDBusMessage.ReplyMessage:
                ok = True
                break
        if not ok:
            log("kwin script did not run")
        if not keep:
            def done():
                scripting.call("unloadScript", name)
                try:
                    os.remove(path)
                except OSError:
                    pass
            QTimer.singleShot(1500, done)
        return sid

    def _load_bridge(self, attempt=0):
        with open(os.path.join(HERE, "kwin-bridge.js")) as f:
            js = f.read()
        js = js.replace("__SELF_PID__", str(os.getpid())).replace("__SERVICE__", DBUS_SERVICE)
        if self._kwin(js, keep=True, name="lsbox-bridge") is None and not DEMO and attempt < 15:
            # KWin may still be starting at login.
            QTimer.singleShot(2000, lambda: self._load_bridge(attempt + 1))

    def _activate_window(self, wid):
        self._kwin(_JS_ACTIVATE % json.dumps(wid))

    def _activate_self(self):
        self._kwin(_JS_ACTIVATE_PID % os.getpid())

    def _on_windows(self, payload):
        try:
            wins = json.loads(payload)
        except ValueError:
            return
        before_running = self._running_keys()
        self._windows = [w for w in wins if isinstance(w, dict)]
        active = next((w for w in self._windows if w.get("active")), None)
        is_self = active is None or active.get("pid") == os.getpid()
        now = time.time()
        for w in self._windows:
            for a in self.apps.values():
                if a.owns(w) and (w.get("active") or a.key not in self._last_used):
                    self._last_used[a.key] = now
        if active and not is_self:
            owner = next((a for a in self.apps.values() if a.owns(active)), None)
            if owner and self.state.get("lastApp") != owner.key:
                self.state["lastApp"] = owner.key
                self._save_state()
        # AirPlay started: say so (UxPlay opens its own window).
        for w in self._windows:
            if w["id"] not in self._seen_windows and "uxplay" in (w.get("cls", "") + w.get("name", "")).lower():
                self.banner.emit("AirPlay", "Mirroring to LSBox", "")
        self._seen_windows = {w["id"] for w in self._windows}
        # Keep-warm apps: hide their first window and stay home.
        for w in self._windows:
            for key in list(self._warm_pending):
                if self.apps[key].owns(w):
                    self._warm_pending.discard(key)
                    self._kwin(_JS_MINIMIZE % json.dumps(w["id"]))
                    self._activate_self()
        if is_self != self._active:
            self._active = is_self
            self.activeChanged.emit()
            if is_self:
                self.homeShown.emit()
                self.refreshShelf()
                self.refreshStatus()
                self._poll_np()
        self.runningChanged.emit()
        if self._running_keys() != before_running:
            self.appsChanged.emit()

    @Slot()
    def _on_input_home(self):
        self._on_home(from_kwin=False, was_active=None)

    def _on_home(self, from_kwin, was_active):
        now = time.monotonic()
        double = now - self._last_home < 0.5
        self._last_home = now
        if was_active is None:
            was_active = self._active
        if not was_active and not from_kwin:
            self._activate_self()  # the bridge already did it for the key
        if not was_active:
            self._active = True
            self.activeChanged.emit()
        if double:
            self.homeDouble.emit()
        elif was_active:
            self.homeAgain.emit()
        else:
            self.homeShown.emit()

    # ---------------- demo data for screenshots and tests
    def _demo_data(self):
        demo_dir = os.environ.get("LSBOX_DEMO_ART", "")
        imgs = sorted(os.path.join(demo_dir, n) for n in os.listdir(demo_dir)) if os.path.isdir(demo_dir) else []

        def u(i):
            return QUrl.fromLocalFile(imgs[i % len(imgs)]).toString() if imgs else ""

        def card(i, t, s, g, p=0.0, kind="jellyfin"):
            return {"kind": kind, "id": f"demo{i}", "title": t, "subtitle": s, "group": g, "progress": p,
                    "backdrop": u(i), "thumb": u(i), "logo": "", "tint": image_tint(imgs[i % len(imgs)]) if imgs else ""}
        self._rows = {
            "moonfin": [
                {"title": "Continue Watching", "items": [card(0, "The Long Coast", "S2 E4 · Low Tide", "Continue Watching", 0.42),
                                                         card(1, "Night Market", "2025 · PG-13", "Continue Watching", 0.71)]},
                {"title": "Up Next", "items": [card(2, "Glass Harbor", "S1 E1 · Pilot", "Up Next")]},
                {"title": "Recently Added", "items": [card(3, "Copper Hills", "2024 · R", "Recently Added"),
                                                      card(4, "Orbit Nine", "2026 · PG", "Recently Added"),
                                                      card(5, "Field Notes", "S3 E2 · Fog", "Recently Added")]},
                {"title": "Tonight's Picks", "items": [card(4, "Orbit Nine", "2026 · PG", "Tonight's Picks"),
                                                       card(1, "Night Market", "2025", "Tonight's Picks")]}],
            "spotify": [{"title": "Recently Played", "items": [card(2, "Tidal Lines", "Harbor Lights", "Recently Played", kind="spotify"),
                                                               card(5, "Paper Moons", "The Fieldworks", "Recently Played", kind="spotify")]}],
            "steam": [{"title": "Recently Played", "items": [card(3, "Copper Run", "Steam", "Recently Played", kind="steam"),
                                                             card(0, "Starfall Tactics", "Steam", "Recently Played", kind="steam")]}],
        }
        self._saver = [c for r in self._rows["moonfin"] for c in r["items"]]
        if os.environ.get("LSBOX_DEMO_PLAYING") == "1":
            self._np = {"active": True, "source": "spotify", "appKey": "spotify", "player": "spotify",
                        "title": "Tidal Lines", "artist": "Harbor Lights", "art": u(2),
                        "position": 83.0, "length": 214.0, "playing": True, "video": False}
        self._sinks = [{"name": "hdmi", "label": "TV (HDMI)", "active": True},
                       {"name": "avr", "label": "Receiver (HDMI passthrough)", "active": False},
                       {"name": "bt", "label": "Headphones (Bluetooth)", "active": False}]
        self._bt = [{"mac": "AA:BB:CC:00:11:22", "name": "Xbox Wireless Controller", "paired": True, "connected": True},
                    {"mac": "AA:BB:CC:00:11:33", "name": "Living Room Headphones", "paired": True, "connected": False}]
        self._display = {"output": "HDMI-A-5", "width": 3840, "height": 2160, "refresh": 143.857,
                         "refreshes": [23.976, 59.94, 60.0, 119.88, 143.857], "scale": 1.7,
                         "hdr": True, "hdrCapable": True}
        self._health = {"cpuTemp": 52, "gpuTemp": 47, "gpuLoad": 8, "wifi": 78, "ram": 31, "disk": 8,
                        "diskText": "18 of 236 GB", "warnings": []}
        self._volume = {"level": 40, "muted": False, "mode": "pipewire"}
        if os.environ.get("LSBOX_DEMO_PROFILES") == "1":
            self.profile_list = [{"name": "Trevor", "color": "#5a3fd6", "kids": False},
                                 {"name": "Guest", "color": "#2a6db0", "kids": False, "pin": prof.hash_pin("1234")},
                                 {"name": "Kids", "color": "#e08a1e", "kids": True, "apps": prof.DEFAULT_KIDS_APPS}]
            self.state["profile"] = "Trevor"
        if os.environ.get("LSBOX_DEMO_THEME"):
            self.settings_["theme"] = os.environ["LSBOX_DEMO_THEME"]
        if os.environ.get("LSBOX_DEMO_BANNER"):
            QTimer.singleShot(1200, lambda: self.banner.emit("Battery low", os.environ["LSBOX_DEMO_BANNER"], ""))
            QTimer.singleShot(1300, lambda: self.volumeStep(5))
        if os.environ.get("LSBOX_DEMO_RUNNING") == "1":
            self._windows = [
                {"id": "w1", "cls": "moonfin", "pid": 11, "caption": "Moonfin"},
                {"id": "w2", "cls": "spotify", "pid": 12, "caption": "Spotify"},
                {"id": "w3", "cls": "steam", "pid": 13, "caption": "Steam"}]
            for a in self.apps.values():  # demo apps have no .desktop file
                a.match.append(a.key)


_JS_ACTIVATE = """
(function () {
  const id = %s;
  for (const w of workspace.windowList()) {
    if (String(w.internalId) === id) { w.minimized = false; workspace.activeWindow = w; }
  }
})();
"""
_JS_ACTIVATE_PID = """
(function () {
  for (const w of workspace.windowList()) {
    if (w.pid === %d && w.normalWindow && String(w.caption) !== "LSBox Overlay") {
      w.minimized = false; workspace.activeWindow = w;
    }
  }
})();
"""
_JS_CLOSE = """
(function () {
  const id = %s;
  for (const w of workspace.windowList()) { if (String(w.internalId) === id) w.closeWindow(); }
})();
"""
_JS_MINIMIZE = """
(function () {
  const id = %s;
  for (const w of workspace.windowList()) { if (String(w.internalId) === id) w.minimized = true; }
})();
"""


# --------------------------------------------------------------------------
# Profile commands (run over SSH as tv)
# --------------------------------------------------------------------------

def cli(argv):
    ap = argparse.ArgumentParser(prog="lsbox_home.py")
    ap.add_argument("--add-profile", metavar="NAME")
    ap.add_argument("--remove-profile", metavar="NAME")
    ap.add_argument("--jellyfin-user", metavar="USER", help="sign this Jellyfin user in for the profile's shelf")
    ap.add_argument("--kids", action="store_true", help="Kids mode: only some apps, short Control Center")
    ap.add_argument("--pin", metavar="1234", help="4-digit PIN needed to switch to this profile")
    a = ap.parse_args(argv)
    profiles = [p for p in load_json(prof.PATH, []) if isinstance(p, dict)]
    if a.remove_profile:
        profiles = [p for p in profiles if p.get("name") != a.remove_profile]
        prof.save(profiles)
        print("removed", a.remove_profile)
        return 0
    if not a.add_profile:
        ap.print_help()
        return 1
    if not profiles:
        profiles = [{"name": "Home"}]  # the profile you have today keeps its layout
    p = next((x for x in profiles if x.get("name") == a.add_profile), None)
    if not p:
        p = {"name": a.add_profile}
        profiles.append(p)
    p["kids"] = bool(a.kids)
    if a.kids:
        p.setdefault("apps", prof.DEFAULT_KIDS_APPS)
    if a.pin:
        if not (a.pin.isdigit() and len(a.pin) == 4):
            print("PIN must be 4 digits")
            return 1
        p["pin"] = prof.hash_pin(a.pin)
    if a.jellyfin_user:
        jf = Jellyfin(JF_CONF)
        if not jf.url:
            print("no JELLYFIN_URL in", JF_CONF)
            return 1
        pw = getpass.getpass(f"Jellyfin password for {a.jellyfin_user}: ")
        token, uid = jf.authenticate(a.jellyfin_user, pw)
        tf = os.path.join(CONF_DIR, "profiles", a.add_profile.replace("/", "_") + ".token")
        os.makedirs(os.path.dirname(tf), mode=0o700, exist_ok=True)
        with open(tf, "w") as f:
            f.write(token)
        os.chmod(tf, 0o600)
        p["token_file"], p["user_id"] = tf, uid
    prof.save(profiles)
    print("saved profile", a.add_profile, "(restart the home screen to see it)")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1].startswith("--"):
        return cli(sys.argv[1:])
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    QGuiApplication.setDesktopFileName(APP_ID)
    QGuiApplication.setApplicationName("LSBox Home")
    app = QGuiApplication(sys.argv)
    app.setOverrideCursor(Qt.BlankCursor)
    home = Home()
    engine = QQmlApplicationEngine()
    engine.addImageProvider("icon", IconProvider())
    engine.rootContext().setContextProperty("home", home)
    engine.load(QUrl.fromLocalFile(os.path.join(HERE, "qml", "Main.qml")))
    if not engine.rootObjects():
        log("QML failed to load")
        return 1
    win = engine.rootObjects()[0]
    home.window = win
    if os.environ.get("LSBOX_PRECOMPILE") == "1":  # installer: fill the QML cache, then quit
        QTimer.singleShot(500, app.quit)
    keys = [k for k in os.environ.get("LSBOX_KEYS", "").split(",") if k]
    if keys:  # testing: press these keys (Qt key names without Key_), 300 ms apart
        win.requestActivate()

        def press(i=0):
            if i >= len(keys):
                return
            name = keys[i]
            if name.startswith("@"):  # "@text" = phone remote typing
                home._on_remote("text", name[1:])
                QTimer.singleShot(300, lambda: press(i + 1))
                return
            hold = name.endswith("~")  # "Return~" = long press
            k = getattr(Qt.Key, "Key_" + name.rstrip("~"))
            QGuiApplication.sendEvent(win.activeFocusItem() or win, QKeyEvent(QEvent.KeyPress, k, Qt.NoModifier))
            QTimer.singleShot(900 if hold else 60, lambda: QGuiApplication.sendEvent(
                win.activeFocusItem() or win, QKeyEvent(QEvent.KeyRelease, k, Qt.NoModifier)))
            QTimer.singleShot(1100 if hold else 300, lambda: press(i + 1))
        QTimer.singleShot(800, press)
    shot = os.environ.get("LSBOX_SCREENSHOT")
    if shot:  # testing: save a picture of the screen and quit
        def grab():
            win.grabWindow().save(shot)
            app.quit()
        QTimer.singleShot(int(os.environ.get("LSBOX_SCREENSHOT_DELAY", "2500")), grab)
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
