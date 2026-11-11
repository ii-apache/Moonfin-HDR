"""Artwork cache: downloads once, QML loads from disk. Also works out an
average colour per picture for the artwork-tinted theme."""
import hashlib
import os
import urllib.request

from .util import CACHE_DIR, log

CACHE_LIMIT_BYTES = 150 * 1024 * 1024  # small drive: keep the cache small


class ImageCache:
    def __init__(self, ctx, tint_fn=None, allowed=()):
        # Only pictures from these servers are downloaded (your Jellyfin).
        # Album art Spotify or YouTube point at on the internet is skipped, so
        # the home screen never contacts anything but your own server.
        self.allowed = [a.rstrip("/") + "/" for a in allowed if a]
        self.dir = os.path.join(CACHE_DIR, "img")
        os.makedirs(self.dir, exist_ok=True)
        self.ctx = ctx
        self.tint_fn = tint_fn  # path -> "#rrggbb" (needs Qt, given by the app)
        self._tints = {}

    def path_for(self, url):
        return os.path.join(self.dir, hashlib.sha1(url.encode()).hexdigest() + ".img")

    def local(self, url):
        """Returns a file:// URL for url, downloading it if needed ('' on failure)."""
        if not url:
            return ""
        if url.startswith("file://") or url.startswith("/"):
            return url if url.startswith("file://") else "file://" + url
        if not url.startswith("http") or not any(url.startswith(a) for a in self.allowed):
            return ""
        path = self.path_for(url)
        if not os.path.exists(path):
            try:
                with urllib.request.urlopen(url, timeout=10, context=self.ctx) as r:
                    data = r.read(20 * 1024 * 1024)
                with open(path + ".part", "wb") as f:
                    f.write(data)
                os.replace(path + ".part", path)
            except Exception as e:  # keep going without that picture
                log("image failed:", type(e).__name__)
                return ""
        else:
            try:
                os.utime(path, None)
            except OSError:
                pass
        return "file://" + path

    def tint(self, file_url):
        if not file_url or not self.tint_fn:
            return ""
        if file_url not in self._tints:
            self._tints[file_url] = self.tint_fn(file_url.replace("file://", "", 1))
        return self._tints[file_url]

    def localize(self, card, keys=("backdrop", "thumb", "logo")):
        for k in keys:
            if k in card:
                card[k] = self.local(card[k])
        card["tint"] = self.tint(card.get("backdrop") or card.get("thumb"))
        return card

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
