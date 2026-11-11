"""Profiles: each person gets their own app order, Jellyfin user for the top
shelf, and optional Kids mode (only some apps, a cut-down Control Center).

~/.config/lsbox-home/profiles.json (written by the --add-profile command):
  [{"name": "Trevor", "color": "#5a3fd6"},
   {"name": "Kids", "kids": true, "token_file": "...", "user_id": "...",
    "apps": ["moonfin", "youtube"], "pin": "<salt>$<sha256>"}]
"""
import hashlib
import os
import secrets

from .util import CONF_DIR, load_json, save_json

PATH = os.path.join(CONF_DIR, "profiles.json")
DEFAULT_KIDS_APPS = ["moonfin", "youtube", "spotify", "search"]
COLORS = ["#5a3fd6", "#d4282b", "#1db954", "#2a6db0", "#c2366e", "#e08a1e"]


def load():
    data = load_json(PATH, [])
    profiles = [p for p in data if isinstance(p, dict) and p.get("name")]
    if not profiles:
        profiles = [{"name": "Home"}]
    for i, p in enumerate(profiles):
        p.setdefault("color", COLORS[i % len(COLORS)])
        p.setdefault("kids", False)
        if p["kids"]:
            p.setdefault("apps", DEFAULT_KIDS_APPS)
    return profiles


def save(profiles):
    save_json(PATH, profiles, mode=0o600)


def hash_pin(pin):
    salt = secrets.token_hex(8)
    return salt + "$" + hashlib.sha256((salt + pin).encode()).hexdigest()


def check_pin(stored, pin):
    if not stored:
        return True
    salt, _, digest = stored.partition("$")
    return secrets.compare_digest(hashlib.sha256((salt + pin).encode()).hexdigest(), digest)


def public(p, active):
    return {"name": p["name"], "color": p["color"], "kids": bool(p.get("kids")),
            "hasPin": bool(p.get("pin")), "active": active}
