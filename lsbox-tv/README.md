# LSBox TV

A fast home screen for the living room box, built for a TV remote. It replaces the Plasma Bigscreen shell on LSBox and takes its layout ideas from Apple TV. The design and code are original.

**Watching**
- **Top shelf** for the focused app. Moonfin: Continue Watching, Up Next, Recently Added, Favorites, Tonight's Picks and a row per library, from your own Jellyfin. Up and Down move between rows. OK opens the item in Moonfin, Play (or holding OK) starts it. Spotify: what this box played recently. Steam: your recent games, which start straight into the game.
- **Now Playing** pill next to the clock for Moonfin, Spotify, YouTube or anything else that plays. Go Up from the top row to reach it: OK pauses or plays, Left and Right skip, holding OK opens the app. Play/Pause on the remote works from anywhere on Home.
- **Search** tile: type on the on-screen keyboard (or from the phone remote) to search your Jellyfin library.
- **Live artwork tiles**: app tiles show what you would watch or play next.

**Remote and controller**
- **Home** (CEC Home, Xbox button) comes back from any app. Twice opens the app switcher (OK opens, Up closes, Menu force-closes a frozen app). Pressing Home again while already on the first tile opens Control Center.
- **Volume bar** for the volume keys, through CEC to the TV or receiver, or the box's own sound. It shows over apps too.
- **Phone remote** (off until you turn it on): a web page on the box, open only to your home network, with a d-pad, typing and app buttons. Pair once with the 4-digit code from Control Center. 30 wrong codes lock it until you make a new code.
- Small controller rumble and soft clicks when focus moves (each can be turned off). Clicks are never played while anything is playing, so passthrough audio is never touched.

**Control Center** (Menu or X): turn the TV off, sleep timer (30 min to 2 h, or end of the episode), sound output and volume, Bluetooth pairing, open apps, picture (HDR, refresh rate, text size), profiles, phone remote, home screen settings, box health, one-press update, close all apps, show hidden apps, System Settings, restart the home screen or the box.

**Profiles and Kids mode**: each profile has its own tile order and hidden apps, and can have its own Jellyfin user (so Continue Watching is theirs, and Jellyfin's own parental rating limits apply) and a PIN. Kids profiles only show the apps you allow and a short Control Center. Optional "Who's watching?" at start.

**Look**: dark, light, or artwork-coloured theme. The screensaver pans across your library, shows the album when music plays, and turns the TV off after an hour (all adjustable).

**Speed and upkeep**
- Moonfin starts hidden at login, so even the first open is instant. Apps keep running after you leave them; apps unused for 4 hours close themselves (never Moonfin or anything playing).
- The screens are pre-built at install, and the shelf from last time shows at once while fresh data loads.
- The installer turns off printing, modem, crash-report services and Plasma background modules a TV never uses (recorded, so uninstall turns them back on).
- Banners for desktop notifications, AirPlay starting, low controller battery and new arrivals in Jellyfin.
- If KWin restarts, the home screen reconnects by itself. Updates install from your fork with one press, and a version that fails to start twice is rolled back.
- The Uptime Kuma heartbeat on the box also alerts when the home screen is down.

Nothing talks to the internet except your Jellyfin server, plus GitHub when you press Update. Album art that Spotify or YouTube point at on the internet is not downloaded.

## How it fits together

```
plasmalogin autologin (tv) -> "LSBox TV" session
  = Plasma Bigscreen's session (KWin with HDR, Bigscreen input handler for
    CEC + controller, portals, PipeWire, your user services)
  - plasmashell (skipped: ExecCondition on LSBOX_TV)
  + lsbox-home.service (this app, PySide6 + Qt Quick; lsboxkit/ = the parts
    that talk to Jellyfin, playerctl, PipeWire, bluetoothctl, kscreen-doctor)
      + kwin-bridge.js loaded into KWin: open windows, Home and volume keys,
        keeps Moonfin's HDR video layer visible by hiding Home behind apps,
        keeps the banner overlay on top without focus
```

Plasma Bigscreen stays installed and untouched, so `uninstall.sh` brings it back after a reboot.

## Files on the box

| Path | What |
|---|---|
| `~tv/.local/share/lsbox-home/` | the app (`.prev` = the version before the last update) |
| `~tv/.local/share/lsbox-src/` | git copy used by one-press update |
| `~tv/.config/lsbox-home/apps.json` | your app list (copy `apps.json` here to edit it) |
| `~tv/.config/lsbox-home/state.json` | settings, tile order, hidden apps, phone remote code (mode 600) |
| `~tv/.config/lsbox-home/profiles.json` | profiles (mode 600; PINs stored hashed) |
| `~tv/.cache/lsbox-home/` | artwork cache (150 MB cap), last shelf, Spotify history |
| `~tv/.config/refresh-match/config` + `token` | Jellyfin URL and token (shared with refresh-match) |
| `/usr/local/bin/lsbox-tv-session`, `/usr/share/wayland-sessions/lsbox-tv.desktop` | the session |
| `/etc/udev/rules.d/70-lsbox-uinput.rules`, `/etc/modules-load.d/lsbox-uinput.conf` | phone remote keyboard |

Logs: `journalctl --user -u lsbox-home` (as tv). Each app runs in its own unit with its own log: `journalctl --user -u 'lsbox-moonfin-*'`.

## Profiles

As tv (`sudo -u tv -i`), then restart the home screen from Control Center:

```
python3 ~/.local/share/lsbox-home/lsbox_home.py --add-profile Trevor --pin 1234
python3 ~/.local/share/lsbox-home/lsbox_home.py --add-profile Kids --kids --jellyfin-user kids
python3 ~/.local/share/lsbox-home/lsbox_home.py --remove-profile Kids
```

`--jellyfin-user` asks for that user's password once and keeps only the resulting token (mode 600).

## Install / undo

As the admin user, from this folder: `bash install.sh`, then reboot. Running it again is safe. To undo: `bash uninstall.sh`, then reboot.

## Tests (no box needed)

- `node tests/kwin_bridge_test.js` checks the KWin bridge against a fake workspace (Home key, volume keys, overlay, HDR layer).
- `python3 tests/test_lsboxkit.py` checks the helpers against sample output of playerctl, pactl, wpctl, bluetoothctl, kscreen-doctor and Steam files.
- `tests/run_integration.sh` runs the real app on a private D-Bus with a fake Jellyfin and checks the bus calls, notifications, phone remote pairing and its security checks, the artwork cache and QML errors. It needs xvfb-run, curl and PySide6.
- `LSBOX_DEMO=1 python3 home/lsbox_home.py` runs it in a window with sample data.
