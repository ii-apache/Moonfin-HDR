"""Recently played Steam games from the local Steam install (no web API)."""
import glob
import os
import re

from .util import HOME, read_file

ROOTS = [os.path.join(HOME, ".var/app/com.valvesoftware.Steam/.local/share/Steam"),
         os.path.join(HOME, ".local/share/Steam"), os.path.join(HOME, ".steam/steam")]
SKIP = re.compile(r"proton|steam linux runtime|steamworks|steamvr|redistributables", re.I)
_KV = re.compile(r'"([^"]+)"\s+"([^"]*)"')


def acf_fields(text):
    return {k: v for k, v in _KV.findall(text)}


def library_paths(root):
    paths = [root]
    vdf = read_file(os.path.join(root, "steamapps", "libraryfolders.vdf"))
    for k, v in _KV.findall(vdf):
        if k == "path" and v not in paths:
            paths.append(v.replace("\\\\", "\\"))
    return paths


def art_for(root, appid):
    cache = os.path.join(root, "appcache", "librarycache")
    cands = [os.path.join(cache, f"{appid}_library_hero.jpg"), os.path.join(cache, f"{appid}_header.jpg")]
    for pattern in ("library_hero*.jpg", "header*.jpg", "library_600x900*.jpg"):
        cands += sorted(glob.glob(os.path.join(cache, str(appid), "**", pattern), recursive=True))
    return next((c for c in cands if os.path.isfile(c)), "")


def recent_games(limit=15, roots=None):
    games = {}
    for root in roots or ROOTS:
        if not os.path.isdir(os.path.join(root, "steamapps")):
            continue
        for lib in library_paths(root):
            for acf in glob.glob(os.path.join(lib, "steamapps", "appmanifest_*.acf")):
                f = acf_fields(read_file(acf))
                appid, name = f.get("appid"), f.get("name", "")
                if not appid or not name or SKIP.search(name):
                    continue
                last = int(f.get("LastPlayed", "0") or 0)
                if appid not in games or last > games[appid]["last"]:
                    games[appid] = {"appid": appid, "name": name, "last": last, "art": art_for(root, appid)}
    out = sorted(games.values(), key=lambda g: (-g["last"], g["name"].lower()))
    return out[:limit]


def rows(roots=None):
    games = recent_games(roots=roots)
    if not games:
        return []
    cards = [{"kind": "steam", "id": g["appid"], "title": g["name"], "subtitle": "Steam",
              "group": "Recently Played", "backdrop": "file://" + g["art"] if g["art"] else "",
              "thumb": "file://" + g["art"] if g["art"] else "", "logo": "", "progress": 0.0, "tint": ""}
             for g in games]
    return [{"title": "Recently Played", "items": cards}]
