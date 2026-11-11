"""Now Playing from MPRIS players (Spotify, YouTube/VacuumTube, anything
else) through playerctl, plus a local Spotify history for its shelf."""
import os
import shutil
import time

from .util import CACHE_DIR, load_json, run, save_json

SEP = "\x1f"
FORMAT = SEP.join(["{{playerName}}", "{{status}}", "{{title}}", "{{artist}}", "{{mpris:artUrl}}",
                   "{{position}}", "{{mpris:length}}", "{{mpris:trackid}}", "{{xesam:url}}"])

# playerName -> home screen app key
PLAYER_APPS = {"spotify": "spotify", "chromium": "youtube", "vacuumtube": "youtube",
               "electron": "youtube", "moonfin": "moonfin", "mpv": "moonfin"}


def have_playerctl():
    return shutil.which("playerctl") is not None


def parse_players(text):
    """playerctl -a metadata --format FORMAT output -> list of player dicts."""
    out = []
    for line in text.splitlines():
        f = line.split(SEP)
        if len(f) < 9:
            continue
        name, status, title, artist, art, pos, length, trackid, url = f[:9]
        base = name.split(".")[0].lower()
        if status not in ("Playing", "Paused"):
            continue

        def num(x):
            try:
                return int(x) / 1e6
            except ValueError:
                return 0.0
        out.append({"player": name, "source": base, "appKey": PLAYER_APPS.get(base, ""),
                    "title": title, "artist": artist, "art": art, "position": num(pos),
                    "length": num(length), "playing": status == "Playing", "trackid": trackid,
                    "url": url, "active": True, "video": False})
    return out


def pick(players):
    """The one to show: something playing beats something paused."""
    playing = [p for p in players if p["playing"]]
    return (playing or players or [None])[0]


def poll():
    if not have_playerctl():
        return []
    code, text = run(["playerctl", "-a", "metadata", "--format", FORMAT], timeout=3)
    return parse_players(text) if code == 0 else []


def control(player, action):
    """action: play-pause, next, previous, pause"""
    run(["playerctl", "-p", player, action], timeout=3)


def spotify_uri(p):
    tid = p.get("trackid") or ""
    if tid.startswith("spotify:"):
        return tid
    if "/track/" in tid:
        return "spotify:track:" + tid.rsplit("/", 1)[-1]
    url = p.get("url") or ""
    if "open.spotify.com/track/" in url:
        return "spotify:track:" + url.rsplit("/", 1)[-1].split("?")[0]
    return ""


class SpotifyHistory:
    """Remembers what Spotify played on this box (kept locally, 40 entries)."""

    def __init__(self):
        self.path = os.path.join(CACHE_DIR, "spotify-history.json")
        self.items = load_json(self.path, [])

    def note(self, p):
        uri = spotify_uri(p)
        if not uri or not p.get("title"):
            return False
        if self.items and self.items[0].get("uri") == uri:
            return False
        self.items = [i for i in self.items if i.get("uri") != uri]
        self.items.insert(0, {"uri": uri, "title": p["title"], "artist": p.get("artist", ""),
                              "art": p.get("art", ""), "t": int(time.time())})
        del self.items[40:]
        try:
            save_json(self.path, self.items)
        except OSError:
            pass
        return True

    def rows(self):
        if not self.items:
            return []
        cards = [{"kind": "spotify", "id": i["uri"], "title": i["title"], "subtitle": i["artist"],
                  "group": "Recently Played", "backdrop": i.get("art", ""), "thumb": i.get("art", ""),
                  "logo": "", "progress": 0.0, "tint": "", "square": True} for i in self.items[:20]]
        return [{"title": "Recently Played", "items": cards}]
