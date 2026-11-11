"""Jellyfin: top shelf rows, screensaver art, now playing on this box, search.
Talks only to your own server (URL + token from refresh-match's config)."""
import json
import os
import ssl
import urllib.parse
import urllib.request

HEADER = ('MediaBrowser Client="LSBox Home", Device="LSBox", '
          'DeviceId="lsbox-home-1", Version="2.0"')


def read_conf(conf_path):
    conf = {}
    try:
        with open(os.path.expanduser(conf_path)) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    conf[k.strip()] = v.strip()
    except OSError:
        pass
    return conf


def make_ctx():
    # The old Home CA has no keyUsage extension and Python 3.13+ rejects that
    # by default. Certificates and host names are still checked.
    ctx = ssl.create_default_context()
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx


class Jellyfin:
    FIELDS = ("ParentId,SeriesName,ParentBackdropImageTags,ParentLogoImageTag,UserData,"
              "ProductionYear,RunTimeTicks,OfficialRating")

    def __init__(self, conf_path, token_file=None):
        self.ctx = make_ctx()
        conf = read_conf(conf_path)
        self.url = conf.get("JELLYFIN_URL", "").rstrip("/") or None
        self.device_match = [d.strip().lower() for d in conf.get("DEVICE_MATCH", "").split(",") if d.strip()]
        tf = token_file or conf.get("TOKEN_FILE") or os.path.join(
            os.path.dirname(os.path.expanduser(conf_path)), "token")
        try:
            with open(os.path.expanduser(tf)) as f:
                self.token = f.read().strip() or None
        except OSError:
            self.token = None
        self.user_id = None

    @property
    def ok(self):
        return bool(self.url and self.token)

    # ---------------- HTTP
    def request(self, path, params=None, body=None, method=None, token=True):
        q = ("?" + urllib.parse.urlencode(params)) if params else ""
        auth = HEADER + (f', Token="{self.token}"' if token and self.token else "")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path + q, data=data, method=method or ("POST" if data is not None else "GET"),
                                     headers={"Authorization": auth, "Accept": "application/json",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8, context=self.ctx) as r:
            raw = r.read()
        return json.loads(raw) if raw else None

    def get(self, path, params=None):
        return self.request(path, params)

    def me(self):
        if not self.user_id:
            self.user_id = self.get("/Users/Me")["Id"]
        return self.user_id

    def _items(self, new_path, old_path, params):
        try:
            res = self.get(new_path, params)
        except Exception:
            res = self.get(old_path, {k: v for k, v in params.items() if k != "userId"})
        return res if isinstance(res, list) else (res or {}).get("Items", [])

    # ---------------- shelf
    def rows(self):
        """Rows for Moonfin's top shelf: [{title, items:[card]}]."""
        uid = self.me()
        base = {"userId": uid, "fields": self.FIELDS, "enableImageTypes": "Primary,Backdrop,Logo,Thumb",
                "imageTypeLimit": 1}
        rows = []

        def add(title, items, group_key=None, limit=20):
            cards, seen = [], set()
            for it in items:
                key = it.get("SeriesId") if group_key == "series" and it.get("Type") == "Episode" else it.get("Id")
                if key and key not in seen:
                    seen.add(key)
                    cards.append(self.card(it, title))
            if cards:
                rows.append({"title": title, "items": cards[:limit]})

        resume = self._items("/UserItems/Resume", f"/Users/{uid}/Items/Resume",
                             dict(base, limit=16, mediaTypes="Video"))
        add("Continue Watching", resume)
        add("Up Next", self._items("/Shows/NextUp", "/Shows/NextUp", dict(base, limit=16)))
        add("Recently Added", self._items("/Items/Latest", f"/Users/{uid}/Items/Latest",
                                          dict(base, limit=20, includeItemTypes="Movie,Episode,Series",
                                               groupItems="true")), group_key="series")
        add("Favorites", self._items("/Items", f"/Users/{uid}/Items",
                                     dict(base, recursive="true", filters="IsFavorite", limit=20,
                                          includeItemTypes="Movie,Series", sortBy="SortName")))
        add("Tonight's Picks", self._items("/Items", f"/Users/{uid}/Items",
                                           dict(base, recursive="true", isPlayed="false", limit=8,
                                                includeItemTypes="Movie", sortBy="Random",
                                                imageTypes="Backdrop")))
        try:
            views = self._items("/UserViews", f"/Users/{uid}/Views", {"userId": uid})
        except Exception:
            views = []
        for v in views:
            if v.get("CollectionType") in ("movies", "tvshows"):
                add(v.get("Name", "Library"), self._items("/Items", f"/Users/{uid}/Items", dict(
                    base, parentId=v["Id"], recursive="true", limit=20, sortBy="Random",
                    includeItemTypes="Movie" if v.get("CollectionType") == "movies" else "Series")))
        return rows

    def saver(self):
        uid = self.me()
        res = self._items("/Items", f"/Users/{uid}/Items", {
            "userId": uid, "recursive": "true", "includeItemTypes": "Movie,Series",
            "imageTypes": "Backdrop", "sortBy": "Random", "limit": 40,
            "fields": "ProductionYear", "enableImageTypes": "Backdrop,Logo", "imageTypeLimit": 1})
        return [self.card(it, "") for it in res]

    def search(self, text):
        uid = self.me()
        res = self._items("/Items", f"/Users/{uid}/Items", {
            "userId": uid, "searchTerm": text, "recursive": "true", "limit": 24,
            "includeItemTypes": "Movie,Series,Episode", "fields": self.FIELDS,
            "enableImageTypes": "Primary,Backdrop,Logo,Thumb", "imageTypeLimit": 1})
        return [self.card(it, "Search") for it in res]

    # ---------------- what this box is playing (Moonfin reports to Jellyfin)
    def box_session(self):
        sessions = self.get("/Sessions", {"activeWithinSeconds": 120}) or []
        for s in sessions:
            if not s.get("NowPlayingItem"):
                continue
            client = (s.get("Client") or "").lower()
            dev = (s.get("DeviceName") or "").lower()
            if "moonfin" not in client:
                continue
            if self.device_match and not any(d in dev for d in self.device_match):
                continue
            return s
        return None

    def session_info(self, s):
        it = s["NowPlayingItem"]
        ps = s.get("PlayState") or {}
        card = self.card(it, "Now Playing")
        length = (it.get("RunTimeTicks") or 0) / 1e7
        return {"active": True, "source": "moonfin", "appKey": "moonfin", "sessionId": s.get("Id"),
                "itemId": it.get("Id"), "title": card["title"], "artist": card["subtitle"],
                "art": card["thumb"] or card["backdrop"], "position": (ps.get("PositionTicks") or 0) / 1e7,
                "length": length, "playing": not ps.get("IsPaused", False), "video": True}

    def playstate(self, session_id, command):
        """command: PlayPause, Pause, Unpause, Stop, NextTrack, PreviousTrack, Rewind, FastForward"""
        self.request(f"/Sessions/{session_id}/Playing/{command}", body={}, method="POST")

    # ---------------- profiles
    def authenticate(self, user, password):
        res = self.request("/Users/AuthenticateByName", body={"Username": user, "Pw": password}, token=False)
        return res["AccessToken"], res["User"]["Id"]

    # ---------------- cards
    def _img(self, item_id, kind, tag, width):
        if not item_id or not tag:
            return ""
        return f"{self.url}/Items/{item_id}/Images/{kind}?maxWidth={width}&quality=88&tag={tag}"

    def card(self, it, group):
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
            sub = " · ".join(x for x in (str(it.get("ProductionYear") or ""), it.get("OfficialRating") or "") if x)
        return {"kind": "jellyfin", "id": it.get("Id", ""), "title": title, "subtitle": sub, "group": group,
                "backdrop": backdrop or thumb, "thumb": thumb or backdrop, "logo": logo, "tint": "",
                "progress": float(ud.get("PlayedPercentage") or 0) / 100.0}
