#!/usr/bin/env python3
"""LSBox Home: a fast, remote-friendly home screen for the living room box.

It replaces the Plasma Bigscreen shell. KWin, the Bigscreen input handler
(CEC remote + game controller -> keys) and every app stay as they are.

  * Apps open once and stay running; opening them again just brings the
    window back, so a second open is instant.
  * The top shelf shows Continue Watching / Next Up / Latest from Jellyfin,
    read with the token refresh-match already uses. Selecting one opens it
    in Moonfin through a moonfin:// link.
  * Home (CEC Home, Xbox button, HomePage key) comes back here from any app.
    Press it twice quickly for the app switcher.

Files:
  ~/.config/lsbox-home/apps.json   which apps are on the home screen (edit me)
  ~/.config/lsbox-home/state.json  order + hidden apps (written by the app)
  ~/.cache/lsbox-home/             Jellyfin artwork cache (capped)
"""
import hashlib
import json
import os
import re
import shlex
import shutil
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

from PySide6.QtCore import (SLOT, ClassInfo, Property, QObject, QSize, Qt, QTimer,
                            QUrl, Signal, Slot)
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPixmap
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
CONF_DIR = os.environ.get("LSBOX_CONF_DIR", os.path.join(HOME, ".config", "lsbox-home"))
CACHE_DIR = os.environ.get("LSBOX_CACHE_DIR", os.path.join(HOME, ".cache", "lsbox-home"))
RUNTIME_DIR = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "lsbox-home")
APP_ID = "lsbox-home"
DBUS_SERVICE = "org.lsbox.Home"
CACHE_LIMIT_BYTES = 150 * 1024 * 1024  # small drive: keep artwork cache small
DEMO = os.environ.get("LSBOX_DEMO") == "1"  # screenshots / testing without a box


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# --------------------------------------------------------------------------
# Desktop entries
# --------------------------------------------------------------------------

def app_dirs():
    dirs = [os.path.join(HOME, ".local/share/applications"),
            os.path.join(HOME, ".local/share/flatpak/exports/share/applications"),
            "/var/lib/flatpak/exports/share/applications"]
    for d in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":"):
        if d:
            dirs.append(os.path.join(d, "applications"))
    seen, out = set(), []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def read_desktop(desktop_id):
    """Return the [Desktop Entry] keys of <desktop_id>.desktop, user dir first."""
    for d in app_dirs():
        path = os.path.join(d, desktop_id + ".desktop")
        if not os.path.isfile(path):
            continue
        entry, in_main = {}, False
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("["):
                        in_main = line == "[Desktop Entry]"
                        continue
                    if in_main and "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        entry.setdefault(k.strip(), v.strip())
        except OSError:
            continue
        entry["_path"] = path
        return entry
    return None


_FIELD_CODE = re.compile(r"%[fFuUdDnNickvm]")


def exec_to_argv(exec_line):
    exec_line = _FIELD_CODE.sub("", exec_line).replace("%%", "%")
    try:
        return [a for a in shlex.split(exec_line) if a]
    except ValueError:
        return exec_line.split()


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


class App:
    def __init__(self, cfg):
        self.cfg = cfg
        self.name = cfg.get("name", "App")
        self.key = cfg.get("key") or re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")
        self.desktop_id = None
        self.entry = None
        for cand in cfg.get("desktop", []):
            e = read_desktop(cand)
            if e:
                self.desktop_id, self.entry = cand, e
                break
        self.argv = cfg.get("exec") and exec_to_argv(cfg["exec"]) or (
            exec_to_argv(self.entry.get("Exec", "")) if self.entry else [])
        self.icon = cfg.get("icon") or (self.entry or {}).get("Icon", "application-x-executable")
        colors = cfg.get("color") or ["#2b2f3a", "#4a5161"]
        self.color1, self.color2 = colors[0], colors[-1]
        self.image = cfg.get("image", "")
        self.tagline = cfg.get("tagline", "")
        self.shelf = cfg.get("shelf", "")
        self.keep_warm = bool(cfg.get("keep_warm", False))
        m = [x.lower() for x in cfg.get("match", [])]
        if self.desktop_id:
            m.append(self.desktop_id.lower())
        wm = (self.entry or {}).get("StartupWMClass")
        if wm:
            m.append(wm.lower())
        self.match = [x for x in m if x]

    @property
    def available(self):
        return DEMO or bool(self.argv)

    def owns(self, win):
        if win.get("cls", "").lower() in ("moonfin-video",):
            return False
        keys = {win.get("cls", "").lower(), win.get("name", "").lower(), win.get("desktop", "").lower()}
        keys.discard("")
        return any(m in keys for m in self.match)

    def to_qml(self, running):
        icon = self.icon
        return {"key": self.key, "name": self.name, "icon": icon,
                "color1": self.color1, "color2": self.color2,
                "image": QUrl.fromLocalFile(os.path.expanduser(self.image)).toString() if self.image else "",
                "tagline": self.tagline, "shelf": self.shelf, "running": running}


# --------------------------------------------------------------------------
# Jellyfin (top shelf + screensaver)
# --------------------------------------------------------------------------

class Jellyfin:
    HEADER = ('MediaBrowser Client="LSBox Home", Device="LSBox", '
              'DeviceId="lsbox-home-1", Version="1.0"')

    def __init__(self, conf_path):
        self.url = None
        self.token = None
        self.user_id = None
        # Same reason as refresh-match: the old Home CA has no keyUsage
        # extension and Python 3.13+ rejects that by default. Certificates
        # and host names are still checked.
        self.ctx = ssl.create_default_context()
        self.ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
        conf = {}
        try:
            with open(os.path.expanduser(conf_path)) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        conf[k.strip()] = v.strip()
        except OSError:
            return
        self.url = conf.get("JELLYFIN_URL", "").rstrip("/") or None
        token_file = conf.get("TOKEN_FILE", os.path.join(os.path.dirname(os.path.expanduser(conf_path)), "token"))
        try:
            with open(os.path.expanduser(token_file)) as f:
                self.token = f.read().strip() or None
        except OSError:
            self.token = None

    @property
    def ok(self):
        return bool(self.url and self.token)

    def get(self, path, params=None):
        q = ("?" + urllib.parse.urlencode(params)) if params else ""
        req = urllib.request.Request(self.url + path + q, headers={
            "Authorization": self.HEADER + f', Token="{self.token}"',
            "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=8, context=self.ctx) as r:
            return json.load(r)

    def me(self):
        if not self.user_id:
            self.user_id = self.get("/Users/Me")["Id"]
        return self.user_id

    FIELDS = "ParentId,SeriesName,ParentBackdropImageTags,ParentLogoImageTag,UserData,ProductionYear,RunTimeTicks"

    def _items(self, new_path, old_path, params):
        try:
            res = self.get(new_path, params)
        except Exception:
            res = self.get(old_path, {k: v for k, v in params.items() if k != "userId"})
        return res if isinstance(res, list) else res.get("Items", [])

    def shelf(self):
        uid = self.me()
        base = {"userId": uid, "fields": self.FIELDS, "enableImageTypes": "Primary,Backdrop,Logo,Thumb",
                "imageTypeLimit": 1}
        resume = self._items("/UserItems/Resume", f"/Users/{uid}/Items/Resume",
                             dict(base, limit=12, mediaTypes="Video"))
        nextup = self._items("/Shows/NextUp", "/Shows/NextUp", dict(base, limit=12))
        latest = self._items("/Items/Latest", f"/Users/{uid}/Items/Latest",
                             dict(base, limit=16, includeItemTypes="Movie,Episode,Series", groupItems="true"))
        out, seen = [], set()
        for group, items in (("Continue Watching", resume), ("Up Next", nextup), ("Recently Added", latest)):
            for it in items:
                key = it.get("SeriesId") if it.get("Type") == "Episode" and group == "Recently Added" else it.get("Id")
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append(self._card(it, group))
        return out[:30]

    def saver(self):
        uid = self.me()
        res = self._items("/Items", f"/Users/{uid}/Items", {
            "userId": uid, "recursive": "true", "includeItemTypes": "Movie,Series",
            "imageTypes": "Backdrop", "sortBy": "Random", "limit": 40,
            "fields": "ProductionYear", "enableImageTypes": "Backdrop,Logo", "imageTypeLimit": 1})
        return [self._card(it, "") for it in res]

    def _img(self, item_id, kind, tag, width):
        if not item_id or not tag:
            return ""
        return f"{self.url}/Items/{item_id}/Images/{kind}?maxWidth={width}&quality=88&tag={tag}"

    def _card(self, it, group):
        tags = it.get("ImageTags") or {}
        backdrop = ""
        if it.get("BackdropImageTags"):
            backdrop = self._img(it["Id"], "Backdrop", it["BackdropImageTags"][0], 1920)
        elif it.get("ParentBackdropImageTags"):
            backdrop = self._img(it.get("ParentBackdropItemId"), "Backdrop", it["ParentBackdropImageTags"][0], 1920)
        thumb = ""
        if it.get("Type") == "Episode" and tags.get("Primary"):
            thumb = self._img(it["Id"], "Primary", tags["Primary"], 800)
        elif tags.get("Thumb"):
            thumb = self._img(it["Id"], "Thumb", tags["Thumb"], 800)
        elif backdrop:
            thumb = backdrop.replace("maxWidth=1920", "maxWidth=800")
        elif tags.get("Primary"):
            thumb = self._img(it["Id"], "Primary", tags["Primary"], 800)
        logo = ""
        if tags.get("Logo"):
            logo = self._img(it["Id"], "Logo", tags["Logo"], 900)
        elif it.get("ParentLogoImageTag"):
            logo = self._img(it.get("ParentLogoItemId"), "Logo", it["ParentLogoImageTag"], 900)
        ud = it.get("UserData") or {}
        if it.get("Type") == "Episode":
            title = it.get("SeriesName") or it.get("Name", "")
            s, e = it.get("ParentIndexNumber"), it.get("IndexNumber")
            sub = (f"S{s} E{e} · " if s is not None and e is not None else "") + it.get("Name", "")
        else:
            title = it.get("Name", "")
            sub = str(it.get("ProductionYear") or "")
        return {"id": it.get("Id", ""), "title": title, "subtitle": sub, "group": group,
                "backdrop": backdrop or thumb, "thumb": thumb or backdrop, "logo": logo,
                "progress": float(ud.get("PlayedPercentage") or 0) / 100.0}


class ImageCache:
    """Downloads Jellyfin artwork once; QML loads it from disk (instant)."""

    def __init__(self, ctx):
        self.dir = os.path.join(CACHE_DIR, "img")
        os.makedirs(self.dir, exist_ok=True)
        self.ctx = ctx

    def local(self, url):
        if not url:
            return ""
        if not url.startswith("http"):
            return url
        name = hashlib.sha1(url.encode()).hexdigest() + ".jpg"
        path = os.path.join(self.dir, name)
        if not os.path.exists(path):
            try:
                with urllib.request.urlopen(url, timeout=10, context=self.ctx) as r:
                    data = r.read()
                with open(path + ".part", "wb") as f:
                    f.write(data)
                os.replace(path + ".part", path)
            except Exception as e:  # keep going without that picture
                log("image failed:", type(e).__name__)
                return ""
        else:
            os.utime(path, None)
        return QUrl.fromLocalFile(path).toString()

    def prune(self):
        files = []
        for n in os.listdir(self.dir):
            p = os.path.join(self.dir, n)
            try:
                st = os.stat(p)
                files.append((st.st_mtime, st.st_size, p))
            except OSError:
                pass
        total = sum(f[1] for f in files)
        for _, size, p in sorted(files):
            if total <= CACHE_LIMIT_BYTES:
                break
            try:
                os.remove(p)
                total -= size
            except OSError:
                pass


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
# D-Bus face that KWin's bridge script calls
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

    @Slot()
    def showHome(self):  # for scripts: busctl --user call org.lsbox.Home /Home org.lsbox.Home showHome
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
    homeAgain = Signal()      # Home pressed while already home
    homeShown = Signal()      # came back home from an app
    homeDouble = Signal()     # Home pressed twice: app switcher
    launchFailed = Signal(str)
    _shelfReady = Signal(list, list)

    def __init__(self):
        super().__init__()
        os.makedirs(RUNTIME_DIR, exist_ok=True)
        self.cfg = load_json(os.path.join(CONF_DIR, "apps.json"), None) or load_json(
            os.path.join(HERE, "apps.json"), {"apps": []})
        self.state = load_json(os.path.join(CONF_DIR, "state.json"), {"order": [], "hidden": []})
        self.apps = {}
        self._build_apps()
        self._windows = []
        self._active = True
        self._last_home = 0.0
        self._shelf, self._saver = [], []
        self._status = {"airplay": "", "storage": "", "jellyfin": ""}
        self._script_n = 0
        self._warm_pending = set()
        self.jf = Jellyfin(self.cfg.get("jellyfin_config", "~/.config/refresh-match/config"))
        self.cache = ImageCache(self.jf.ctx)
        self._shelfReady.connect(self._set_shelf)
        self._last_shelf = 0.0

        self.bus = QDBusConnection.sessionBus()
        self.api = BusApi(self)
        if self.bus.isConnected():
            self.bus.registerObject("/Home", self.api, QDBusConnection.ExportAllSlots)
            if not self.bus.registerService(DBUS_SERVICE):
                log("another LSBox Home already owns", DBUS_SERVICE)
            # Xbox button / CEC menu keys from the Bigscreen input handler
            self.bus.connect("", "/InputHandler", "org.kde.plasma.bigscreen.inputhandler",
                             "homeActionRequested", self, SLOT("_on_input_home()"))
        QTimer.singleShot(0, self._load_bridge)
        QTimer.singleShot(200, self.refreshShelf)
        QTimer.singleShot(400, self.refreshStatus)
        QTimer.singleShot(20000, self._warm_up)
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(10 * 60 * 1000)
        self._tick_timer = t
        if DEMO:
            self._demo_data()

    # ---------------- apps
    def _build_apps(self):
        self.apps = {}
        for c in self.cfg.get("apps", []):
            a = App(c)
            if a.available:
                self.apps[a.key] = a
            else:
                log("not installed, skipped:", a.name)

    def _ordered(self):
        keys = list(self.apps)
        order = [k for k in self.state.get("order", []) if k in self.apps]
        order += [k for k in keys if k not in order]
        hidden = set(self.state.get("hidden", []))
        return [k for k in order if k not in hidden]

    def _running_keys(self):
        r = set()
        for w in self._windows:
            for a in self.apps.values():
                if a.owns(w):
                    r.add(a.key)
        return r

    @Property("QVariantList", notify=appsChanged)
    def apps_(self):
        running = self._running_keys()
        return [self.apps[k].to_qml(k in running) for k in self._ordered()]

    @Property("QVariantList", notify=hiddenChanged)
    def hidden(self):
        return [self.apps[k].to_qml(False) for k in self.state.get("hidden", []) if k in self.apps]

    @Property("QVariantList", notify=runningChanged)
    def running(self):
        out = []
        for w in self._windows:
            if w.get("pid") == os.getpid() or w.get("cls", "").lower() == "moonfin-video":
                continue
            owner = next((a for a in self.apps.values() if a.owns(w)), None)
            if owner and any(o.get("key") == owner.key for o in out):
                continue
            d = owner.to_qml(True) if owner else {
                "key": "", "name": w.get("caption") or w.get("cls") or "App",
                "icon": w.get("desktop") or w.get("cls") or "application-x-executable",
                "color1": "#2b2f3a", "color2": "#4a5161", "image": "", "running": True}
            d["wid"] = w.get("id", "")
            out.append(d)
        return out

    @Property(bool, notify=activeChanged)
    def launcherActive(self):
        return self._active

    @Property("QVariantList", notify=shelfChanged)
    def shelf(self):
        return self._shelf

    @Property("QVariantList", notify=saverChanged)
    def saver(self):
        return self._saver

    @Property("QVariantMap", notify=statusChanged)
    def status(self):
        return self._status

    @Property(bool, constant=True)
    def demo(self):
        return DEMO

    @Property(int, constant=True)
    def saverMinutes(self):
        return int(self.cfg.get("screensaver_minutes", 5) or 0)

    @Slot()
    def showHome(self):
        self._on_home(from_kwin=False, was_active=None)

    @Slot(str)
    def launch(self, key):
        a = self.apps.get(key)
        if not a:
            return
        wins = [w for w in self._windows if a.owns(w)]
        if wins:
            self._activate_window(wins[-1]["id"])
            return
        self._spawn(a.argv, a.key)

    @Slot(str, bool)
    def openShelfItem(self, item_id, play):
        moonfin = next((a for a in self.apps.values() if a.shelf == "jellyfin"), None)
        if not moonfin or not item_id:
            return
        url = f"moonfin://{'play' if play else 'item'}?id={urllib.parse.quote(item_id)}"
        # Moonfin is single-instance: a running copy gets the link forwarded.
        self._spawn(moonfin.argv + [url], moonfin.key)
        wins = [w for w in self._windows if moonfin.owns(w)]
        if wins:
            self._activate_window(wins[-1]["id"])

    def _spawn(self, argv, key):
        if DEMO or not argv:
            log("launch", argv)
            return
        unit = f"lsbox-{key}-{int(time.time() * 1000) % 100000000}"
        if shutil.which("systemd-run"):
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
        self.state["order"] = order + [k for k in self.state.get("order", []) if k not in order]
        self._save_state()
        self.appsChanged.emit()

    @Slot(str)
    def hideApp(self, key):
        h = self.state.setdefault("hidden", [])
        if key not in h:
            h.append(key)
        self._save_state()
        self.appsChanged.emit()
        self.hiddenChanged.emit()

    @Slot()
    def unhideAll(self):
        self.state["hidden"] = []
        self._save_state()
        self.appsChanged.emit()
        self.hiddenChanged.emit()

    def _save_state(self):
        try:
            save_json(os.path.join(CONF_DIR, "state.json"), self.state)
        except OSError as e:
            log("state not saved:", e)

    # ---------------- system actions (Control Center)
    def _inputhandler(self, method, *args):
        if DEMO:
            log("inputhandler", method, args)
            return None
        iface = QDBusInterface("org.kde.plasma.bigscreen.inputhandler", "/InputHandler",
                               "org.kde.plasma.bigscreen.inputhandler", self.bus)
        if not iface.isValid():
            return None
        r = iface.call(method, *args)
        return r.arguments()[0] if r.type() == QDBusMessage.ReplyMessage and r.arguments() else None

    @Slot()
    def tvOff(self):
        self._inputhandler("sendStandby", 0)

    @Slot()
    def openSettings(self):
        a = self.apps.get("settings")
        if a:
            self.launch("settings")
        else:
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
        st = dict(self._status)
        try:
            du = shutil.disk_usage("/")
            st["storage"] = f"{du.used / 1e9:.0f} GB used of {du.total / 1e9:.0f} GB"
        except OSError:
            pass
        if DEMO:
            st["airplay"] = "Ready as LSBox"
        else:
            try:
                r = subprocess.run(["systemctl", "--user", "is-active", "uxplay.service"],
                                   capture_output=True, text=True, timeout=2)
                st["airplay"] = "Ready as LSBox" if r.stdout.strip() == "active" else "Off"
            except (OSError, subprocess.TimeoutExpired):
                st["airplay"] = ""
        self._status = st
        self.statusChanged.emit()

    # ---------------- shelf
    @Slot()
    def refreshShelf(self):
        if DEMO or not self.jf.ok:
            if not self.jf.ok and not DEMO:
                self._status["jellyfin"] = "Top shelf off: no ~/.config/refresh-match/config"
                self.statusChanged.emit()
            return
        if time.monotonic() - self._last_shelf < 60 and self._shelf:
            return
        self._last_shelf = time.monotonic()
        threading.Thread(target=self._fetch_shelf, daemon=True).start()

    def _fetch_shelf(self):
        try:
            shelf = self.jf.shelf()
            for c in shelf:
                c["backdrop"] = self.cache.local(c["backdrop"])
                c["thumb"] = self.cache.local(c["thumb"])
                c["logo"] = self.cache.local(c["logo"])
            saver = []
            if not self._saver:
                saver = self.jf.saver()
                for c in saver:
                    c["backdrop"] = self.cache.local(c["backdrop"])
                    c["logo"] = self.cache.local(c["logo"])
                    c["thumb"] = ""
                saver = [c for c in saver if c["backdrop"]]
            self.cache.prune()
            self._shelfReady.emit(shelf, saver)
        except Exception as e:
            log("jellyfin:", type(e).__name__, e)

    def _set_shelf(self, shelf, saver):
        self._shelf = shelf
        self.shelfChanged.emit()
        if saver:
            self._saver = saver
            self.saverChanged.emit()

    def _tick(self):
        self._saver = []  # new random set next time
        self.refreshShelf()
        self.refreshStatus()

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

    def _warm_up(self):
        for a in self.apps.values():
            if a.keep_warm and not any(a.owns(w) for w in self._windows):
                self._warm_pending.add(a.key)
                self._spawn(a.argv, a.key)
        if self._warm_pending:
            QTimer.singleShot(60000, self._warm_pending.clear)

    # ---------------- demo data for screenshots and tests
    def _demo_data(self):
        demo_dir = os.environ.get("LSBOX_DEMO_ART", "")
        imgs = sorted(os.path.join(demo_dir, n) for n in os.listdir(demo_dir)) if os.path.isdir(demo_dir) else []

        def u(i):
            return QUrl.fromLocalFile(imgs[i % len(imgs)]).toString() if imgs else ""
        titles = [("The Long Coast", "S2 E4 · Low Tide", "Continue Watching", 0.42),
                  ("Night Market", "2025", "Continue Watching", 0.71),
                  ("Glass Harbor", "S1 E1 · Pilot", "Up Next", 0.0),
                  ("Copper Hills", "2024", "Recently Added", 0.0),
                  ("Orbit Nine", "2026", "Recently Added", 0.0),
                  ("Field Notes", "S3 E2 · Fog", "Recently Added", 0.0)]
        self._shelf = [{"id": f"demo{i}", "title": t, "subtitle": s, "group": g, "progress": p,
                        "backdrop": u(i), "thumb": u(i), "logo": ""} for i, (t, s, g, p) in enumerate(titles)]
        self._saver = [dict(c) for c in self._shelf]
        if os.environ.get("LSBOX_DEMO_RUNNING") == "1":
            self._windows = [
                {"id": "w1", "cls": "org.moonfin.linux", "desktop": "org.moonfin.linux", "pid": 11, "caption": "Moonfin"},
                {"id": "w2", "cls": "spotify", "desktop": "com.spotify.Client", "pid": 12, "caption": "Spotify"},
                {"id": "w3", "cls": "steam", "desktop": "steam-tv", "pid": 13, "caption": "Steam"}]
            for a in self.apps.values():  # demo apps have no .desktop file
                a.match.append(a.key)
            for w, k in zip(self._windows, ("moonfin", "spotify", "steam")):
                w["cls"] = k


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
    if (w.pid === %d && w.normalWindow) { w.minimized = false; workspace.activeWindow = w; }
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


def main():
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
    keys = [k for k in os.environ.get("LSBOX_KEYS", "").split(",") if k]
    if keys:  # testing: press these keys (Qt key names without Key_), 300 ms apart
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent

        win.requestActivate()

        def press(i=0):
            if i >= len(keys):
                return
            name = keys[i]
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
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
