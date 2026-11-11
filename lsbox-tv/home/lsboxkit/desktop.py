"""Desktop entries and the App model."""
import os
import re
import shlex

from .util import DEMO, HOME


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


BUILTIN = {"search"}  # apps drawn by the home screen itself


class App:
    def __init__(self, cfg):
        self.cfg = cfg
        self.name = cfg.get("name", "App")
        self.key = cfg.get("key") or re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")
        self.builtin = cfg.get("builtin", "") or ("search" if self.key in BUILTIN else "")
        self.desktop_id = None
        self.entry = None
        for cand in cfg.get("desktop", []):
            e = read_desktop(cand)
            if e:
                self.desktop_id, self.entry = cand, e
                break
        if cfg.get("exec"):
            self.argv = exec_to_argv(cfg["exec"])
        else:
            self.argv = exec_to_argv(self.entry.get("Exec", "")) if self.entry else []
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
        return DEMO or bool(self.argv) or bool(self.builtin)

    def owns(self, win):
        if self.builtin or win.get("cls", "").lower() == "moonfin-video":
            return False
        keys = {win.get("cls", "").lower(), win.get("name", "").lower(), win.get("desktop", "").lower()}
        keys.discard("")
        return any(m in keys for m in self.match)
