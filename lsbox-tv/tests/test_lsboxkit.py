#!/usr/bin/env python3
"""Checks the box-side helpers against sample command output: python3 tests/test_lsboxkit.py"""
import json
import os
import sys
import tempfile
import unittest

TMP = tempfile.mkdtemp()
os.environ["LSBOX_CONF_DIR"] = os.path.join(TMP, "conf")
os.environ["LSBOX_CACHE_DIR"] = os.path.join(TMP, "cache")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "home"))

from lsboxkit import media, profiles, steam, system, uinput  # noqa: E402
from lsboxkit.desktop import App, exec_to_argv  # noqa: E402
from lsboxkit.images import ImageCache  # noqa: E402


class Media(unittest.TestCase):
    def test_players(self):
        S = media.SEP
        text = "\n".join([
            S.join(["spotify", "Paused", "Song A", "Band", "https://i.example/a", "1000000", "200000000", "spotify:track:abc", ""]),
            S.join(["chromium.instance2", "Playing", "Video", "Chan", "", "5000000", "0", "/org/x", ""]),
            S.join(["mpv", "Stopped", "x", "", "", "0", "0", "", ""]),
        ])
        ps = media.parse_players(text)
        self.assertEqual([p["source"] for p in ps], ["spotify", "chromium"])
        self.assertEqual(ps[1]["appKey"], "youtube")
        self.assertEqual(ps[0]["length"], 200.0)
        self.assertEqual(media.pick(ps)["title"], "Video", "playing beats paused")
        self.assertEqual(media.spotify_uri(ps[0]), "spotify:track:abc")
        self.assertEqual(media.spotify_uri({"trackid": "/com/spotify/track/xyz"}), "spotify:track:xyz")

    def test_history(self):
        h = media.SpotifyHistory()
        p = {"trackid": "spotify:track:1", "title": "One", "artist": "A", "art": ""}
        self.assertTrue(h.note(p))
        self.assertFalse(h.note(p), "same song twice is one entry")
        h.note({"trackid": "spotify:track:2", "title": "Two"})
        self.assertEqual([c["id"] for c in h.rows()[0]["items"]], ["spotify:track:2", "spotify:track:1"])


class System(unittest.TestCase):
    def test_sinks(self):
        js = json.dumps([{"name": "alsa_output.hdmi", "description": "TU106 High Definition Audio Controller Digital Stereo (HDMI)"},
                         {"name": "bluez_output.x", "description": "Headphones"},
                         {"name": "x.monitor", "description": "m"}])
        s = system.parse_sinks(js, "bluez_output.x")
        self.assertEqual(len(s), 2)
        self.assertTrue(s[1]["active"])
        self.assertNotIn("TU106", s[0]["label"])

    def test_volume(self):
        self.assertEqual(system.parse_wpctl_volume("Volume: 0.45"), {"level": 45, "muted": False})
        self.assertEqual(system.parse_wpctl_volume("Volume: 0.30 [MUTED]")["muted"], True)
        self.assertIsNone(system.cec_status_to_volume(0x7F), "0x7F = unknown")
        self.assertEqual(system.cec_status_to_volume(0x80 | 20), {"level": 20, "muted": True})

    def test_bluetooth(self):
        d = system.parse_devices("Device AA:BB:CC:DD:EE:FF Xbox Wireless Controller\nDevice 11:22:33:44:55:66 Buds\njunk")
        self.assertEqual([x["name"] for x in d], ["Xbox Wireless Controller", "Buds"])

    def test_kscreen(self):
        js = json.dumps({"outputs": [
            {"name": "DP-1", "enabled": False, "connected": True},
            {"name": "HDMI-A-1", "enabled": True, "connected": True, "currentModeId": "2", "scale": 1.7, "hdr": True,
             "modes": [{"id": "1", "refreshRate": 60.0, "size": {"width": 3840, "height": 2160}},
                       {"id": "2", "refreshRate": 119.88, "size": {"width": 3840, "height": 2160}},
                       {"id": "3", "refreshRate": 144.0, "size": {"width": 1920, "height": 1080}}]}]})
        d = system.parse_kscreen(js)
        self.assertEqual(d["output"], "HDMI-A-1")
        self.assertEqual(d["refreshes"], [60.0, 119.88], "only rates at the current size")
        self.assertTrue(d["hdr"] and d["hdrCapable"])

    def test_health_parsers(self):
        wl = "Inter-| sta-|   Quality\n face | tus | link level noise\nwlp3s0: 0000   56.  -54.  -256\n"
        self.assertEqual(system.parse_wireless(wl), 80)
        self.assertEqual(system.parse_meminfo("MemTotal: 1000 kB\nMemAvailable: 250 kB\n"), 75)


class Steam(unittest.TestCase):
    def test_recent(self):
        root = os.path.join(TMP, "Steam")
        os.makedirs(os.path.join(root, "steamapps"))
        os.makedirs(os.path.join(root, "appcache", "librarycache", "620"))
        open(os.path.join(root, "appcache", "librarycache", "620", "library_hero.jpg"), "w").close()
        for appid, name, last in (("620", "Portal 2", 200), ("1493710", "Proton Experimental", 300), ("70", "Half-Life", 100)):
            with open(os.path.join(root, "steamapps", f"appmanifest_{appid}.acf"), "w") as f:
                f.write(f'"AppState"\n{{\n\t"appid"\t\t"{appid}"\n\t"name"\t\t"{name}"\n\t"LastPlayed"\t\t"{last}"\n}}\n')
        g = steam.recent_games(roots=[root])
        self.assertEqual([x["name"] for x in g], ["Portal 2", "Half-Life"], "newest first, no Proton")
        self.assertTrue(g[0]["art"].endswith("library_hero.jpg"))
        self.assertEqual(steam.rows(roots=[root])[0]["items"][0]["id"], "620")


class Profiles(unittest.TestCase):
    def test_pin(self):
        h = profiles.hash_pin("1234")
        self.assertTrue(profiles.check_pin(h, "1234"))
        self.assertFalse(profiles.check_pin(h, "4321"))
        self.assertNotIn("1234", h)

    def test_defaults(self):
        self.assertEqual(profiles.load()[0]["name"], "Home")
        profiles.save([{"name": "A"}, {"name": "K", "kids": True}])
        p = profiles.load()
        self.assertIn("search", p[1]["apps"])
        self.assertEqual(oct(os.stat(profiles.PATH).st_mode & 0o777), "0o600")


class Misc(unittest.TestCase):
    def test_keys(self):
        self.assertEqual(uinput.char_key("a"), (30, False))
        self.assertEqual(uinput.char_key("Z"), (44, True))
        self.assertEqual(uinput.char_key("?"), (53, True))
        self.assertIsNone(uinput.char_key("é"))

    def test_exec(self):
        self.assertEqual(exec_to_argv('flatpak run --branch=stable com.spotify.Client %U'),
                         ["flatpak", "run", "--branch=stable", "com.spotify.Client"])

    def test_builtin(self):
        a = App({"key": "search", "name": "Search", "builtin": "search"})
        self.assertTrue(a.available)
        self.assertFalse(a.owns({"cls": "search"}))

    def test_images_only_own_server(self):
        c = ImageCache(None, allowed=["http://jf.lan:8096"])
        self.assertEqual(c.local("https://i.scdn.co/image/x"), "", "internet art is never fetched")
        self.assertEqual(c.local("/tmp/x.jpg"), "file:///tmp/x.jpg")


if __name__ == "__main__":
    unittest.main(verbosity=1)
