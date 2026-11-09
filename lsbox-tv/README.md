# LSBox TV

A fast home screen for the living room box, built for a TV remote. It replaces the Plasma Bigscreen shell on LSBox and takes its layout ideas from Apple TV. The design and code are original.

- **Top shelf**: Continue Watching, Up Next and Recently Added from your own Jellyfin server. OK opens the item in Moonfin; Play starts it.
- **App grid**: Moonfin, YouTube (VacuumTube), Spotify, Steam Big Picture, Moonlight, Eden and Settings.
- **Fast switching**: an app keeps running after you open it, so opening it again just brings its window back. The tile appears full screen the moment you press OK, so you never sit on a blank screen.
- **Home**: CEC Home, the Xbox button and the HomePage key bring you back from any app. Press Home twice for the app switcher, where OK opens an app and Up closes it.
- **Control Center** (Menu or X button): turn the TV off over CEC, see open apps, close all apps, open Settings, restart the home screen or restart the box. It also shows AirPlay status and free storage.
- **Hold OK on a tile** to move it, hide it or close the app.
- **Screensaver**: after 5 idle minutes, slow pans over artwork from your own library.
- Nothing talks to the internet except your Jellyfin server.

## How it fits together

```
plasmalogin autologin (tv) -> "LSBox TV" session
  = Plasma Bigscreen's session (KWin with HDR, Bigscreen input handler for
    CEC + controller, portals, PipeWire, your user services)
  - plasmashell (skipped: ExecCondition on LSBOX_TV)
  + lsbox-home.service (this app, PySide6 + Qt Quick)
      + kwin-bridge.js loaded into KWin: open windows, Home key, keeps
        Moonfin's HDR video layer visible by hiding Home behind apps
```

Plasma Bigscreen stays installed and untouched, so `uninstall.sh` brings it back after a reboot.

## Files on the box

| Path | What |
|---|---|
| `~tv/.local/share/lsbox-home/` | the app |
| `~tv/.config/lsbox-home/apps.json` | your app list (copy `apps.json` here to edit it) |
| `~tv/.config/lsbox-home/state.json` | tile order and hidden apps |
| `~tv/.cache/lsbox-home/img/` | Jellyfin artwork cache, capped at 150 MB |
| `~tv/.config/refresh-match/config` + `token` | Jellyfin URL and token (shared with refresh-match) |
| `/usr/local/bin/lsbox-tv-session`, `/usr/share/wayland-sessions/lsbox-tv.desktop` | the session |

Logs: `journalctl --user -u lsbox-home` (as tv). Each app runs in its own unit with its own log: `journalctl --user -u 'lsbox-moonfin-*'`.

## Install / undo

As the admin user, from this folder: `bash install.sh`, then reboot. To undo: `bash uninstall.sh`, then reboot.

## Tests (no box needed)

- `node tests/kwin_bridge_test.js` checks the KWin bridge against a fake workspace.
- `tests/run_integration.sh` runs the real app on a private D-Bus with a fake Jellyfin and checks the bus calls, the artwork cache and QML errors. It needs xvfb-run and PySide6.
- `LSBOX_DEMO=1 python3 home/lsbox_home.py` runs it in a window with sample data.
