#!/bin/bash
# LSBox TV installer. Run as the admin user (zzanderr) on LSBox, from the git
# clone (~/lsbox-src/lsbox-tv):  bash install.sh
# Safe to run again (that is also how updates that touch more than the app
# itself are applied). Undo everything with: bash uninstall.sh
set -u
SRC=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$SRC/.." && pwd)
TVUSER=tv
STATE=/var/lib/lsbox-tv
stop() { echo "STOP: $*"; exit 1; }

[ "$(id -u)" -ne 0 ] || stop "run as zzanderr, not root (sudo is used where needed)"
id "$TVUSER" >/dev/null 2>&1 || stop "no user $TVUSER"
TVUID=$(id -u "$TVUSER")
TVHOME=$(getent passwd "$TVUSER" | cut -d: -f6)
BIG_DESKTOP=$(ls /usr/share/wayland-sessions/plasma-bigscreen-wayland.desktop 2>/dev/null)
[ -n "$BIG_DESKTOP" ] || stop "Plasma Bigscreen session file not found"
BIG_EXEC=$(sed -n 's/^Exec=//p' "$BIG_DESKTOP" | head -1)
case "$BIG_EXEC" in /*) ;; *) BIG_EXEC=$(command -v "${BIG_EXEC%% *}") ;; esac
[ -x "${BIG_EXEC%% *}" ] || stop "Bigscreen session program not found ($BIG_EXEC)"
command -v plasma-bigscreen-inputhandler >/dev/null || stop "plasma-bigscreen-inputhandler missing"
AUTO=$(sudo grep -rlsE "^User=$TVUSER\b" /etc/plasmalogin.conf.d /etc/plasmalogin.conf 2>/dev/null | grep -v lsbox-bak | head -1)
[ -n "$AUTO" ] || stop "could not find the Plasma Login Manager autologin file for $TVUSER"
echo "Bigscreen session: $BIG_EXEC"
echo "Autologin file:    $AUTO"
TVENV="HOME=$TVHOME XDG_RUNTIME_DIR=/run/user/$TVUID DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$TVUID/bus"
astv() { sudo -u "$TVUSER" env $TVENV "$@"; }
sudo install -d -m 755 "$STATE"

echo "== 1/9 Packages: Qt for Python (uses the Qt already installed), playerctl, git"
sudo dnf install -y python3-pyside6 playerctl git-core || stop "dnf install failed"
python3 -c "import PySide6.QtQuick, PySide6.QtDBus" || stop "PySide6 does not import"

echo "== 2/9 Home screen app -> $TVHOME/.local/share/lsbox-home"
LIVE="$TVHOME/.local/share/lsbox-home"
sudo install -d -o "$TVUSER" -g "$TVUSER" "$LIVE/qml" "$LIVE/lsboxkit" "$TVHOME/.config/lsbox-home" \
  "$TVHOME/.config/systemd/user/plasma-plasmashell.service.d"
sudo find "$LIVE" -name '*.py[co]' -delete 2>/dev/null
sudo install -o "$TVUSER" -g "$TVUSER" -m 644 "$SRC"/home/lsbox_home.py "$SRC"/home/kwin-bridge.js "$SRC"/home/apps.json "$LIVE/"
sudo install -o "$TVUSER" -g "$TVUSER" -m 644 "$SRC"/home/qml/*.qml "$LIVE/qml/"
sudo install -o "$TVUSER" -g "$TVUSER" -m 644 "$SRC"/home/lsboxkit/*.py "$LIVE/lsboxkit/"
sudo rm -f "$LIVE/.pending"
sudo install -o "$TVUSER" -g "$TVUSER" -m 755 "$SRC/session/lsbox-guard" "$TVHOME/.local/share/lsbox-guard"
# Your own copy of apps.json predates the Search tile: add it, keep the rest.
if sudo test -f "$TVHOME/.config/lsbox-home/apps.json"; then
  sudo -u "$TVUSER" python3 -I - "$TVHOME/.config/lsbox-home/apps.json" "$SRC/home/apps.json" <<'PY'
import json, sys
mine, new = sys.argv[1], json.load(open(sys.argv[2]))
c = json.load(open(mine))
keys = {a.get("key") for a in c.get("apps", [])}
for a in new["apps"]:
    if a["key"] not in keys and a.get("builtin"):
        c["apps"].insert(max(0, len(c["apps"]) - 1), a)
        print("added", a["name"], "to your apps.json")
for a in c.get("apps", []):
    for n in new["apps"]:
        if a.get("key") == n["key"] and n.get("shelf") and not a.get("shelf"):
            a["shelf"] = n["shelf"]
json.dump(c, open(mine, "w"), indent=2)
PY
fi

echo "== 3/9 One-press updates: a copy of this git clone that $TVUSER owns"
UPD="$TVHOME/.local/share/lsbox-src"
BRANCH=$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null)
if [ -d "$REPO/.git" ] && [ -n "$BRANCH" ] && [ "$BRANCH" != HEAD ]; then
  sudo rm -rf "$UPD"
  sudo cp -a "$REPO" "$UPD"
  echo "$BRANCH" | sudo tee "$UPD/.lsbox-branch" >/dev/null
  sudo chown -R "$TVUSER:$TVUSER" "$UPD"
  echo "update source: branch $BRANCH at $(git -C "$REPO" rev-parse --short HEAD)"
else
  echo "not run from a git clone: Control Center > Update will be off"
fi

echo "== 4/9 User services for $TVUSER"
sudo install -o "$TVUSER" -g "$TVUSER" -m 644 "$SRC/session/lsbox-home.service" "$TVHOME/.config/systemd/user/lsbox-home.service"
sudo install -o "$TVUSER" -g "$TVUSER" -m 644 "$SRC/session/plasmashell-lsbox.conf" \
  "$TVHOME/.config/systemd/user/plasma-plasmashell.service.d/lsbox.conf"
astv systemctl --user daemon-reload
astv systemctl --user enable lsbox-home.service || stop "could not enable lsbox-home.service"
# Kuma heartbeat (if installed): also alert when the home screen is down.
if sudo test -x "$TVHOME/.local/bin/box-heartbeat"; then
  sudo install -o "$TVUSER" -g "$TVUSER" -m 755 "$SRC/session/box-heartbeat" "$TVHOME/.local/bin/box-heartbeat"
  echo "box-heartbeat now also checks the home screen"
fi

echo "== 5/9 Session 'LSBox TV'"
sed "s|@BIGSCREEN_SESSION@|$BIG_EXEC|" "$SRC/session/lsbox-tv-session" | sudo tee /usr/local/bin/lsbox-tv-session >/dev/null
sudo chmod 755 /usr/local/bin/lsbox-tv-session
sudo sed -e 's|^Exec=.*|Exec=/usr/local/bin/lsbox-tv-session|' -e 's|^TryExec=.*|TryExec=/usr/local/bin/lsbox-tv-session|' \
  -e 's|^Name=.*|Name=LSBox TV|' -e '/^Name\[/d' -e '/^Comment/d' "$BIG_DESKTOP" | sudo tee /usr/share/wayland-sessions/lsbox-tv.desktop >/dev/null

echo "== 6/9 Phone remote: virtual keyboard access + firewall (off until you turn it on in Control Center)"
echo uinput | sudo tee /etc/modules-load.d/lsbox-uinput.conf >/dev/null
echo 'KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"' | \
  sudo tee /etc/udev/rules.d/70-lsbox-uinput.rules >/dev/null
sudo modprobe uinput
sudo udevadm control --reload
sudo udevadm trigger --name-match=uinput 2>/dev/null
if sudo firewall-cmd --get-zones 2>/dev/null | grep -qw tvbox; then
  sudo firewall-cmd -q --permanent --zone=tvbox --add-rich-rule='rule priority="-1" family="ipv4" source address="192.168.50.26" port port="8095" protocol="tcp" reject'
  sudo firewall-cmd -q --permanent --zone=tvbox --add-rich-rule='rule family="ipv4" source address="192.168.50.0/24" port port="8095" protocol="tcp" accept'
  sudo firewall-cmd -q --reload
  echo "firewall: 8095 open to 192.168.50.0/24 only (not .26, so nothing from Tailscale)"
else
  echo "no tvbox firewall zone found: port 8095 left closed"
fi

echo "== 7/9 Faster boot and login"
astv kwriteconfig6 --file ksplashrc --group KSplash --key Engine none
astv kwriteconfig6 --file ksplashrc --group KSplash --key Theme None
astv kwriteconfig6 --file baloofilerc --group "Basic Settings" --key "Indexing-Enabled" false
# Apps and Home switch instantly (no minimise animation).
astv kwriteconfig6 --file kwinrc --group Plugins --key squashEnabled false
astv kwriteconfig6 --file kwinrc --group Plugins --key magiclampEnabled false
# Plasma background modules a TV never needs.
for m in printmanager smbwatcher remotenotifier browserintegrationreminder freespacenotifier; do
  astv kwriteconfig6 --file kded6rc --group "Module-$m" --key autoload false
done
# System services a TV never needs. Each one turned off is recorded so
# uninstall.sh can turn it back on.
for s in cups.service cups.socket cups-browsed.service ModemManager.service abrtd.service \
         abrt-journal-core.service abrt-oops.service abrt-xorg.service; do
  if [ "$(systemctl is-enabled "$s" 2>/dev/null)" = enabled ]; then
    sudo systemctl disable --now "$s" >/dev/null 2>&1 && echo "$s" | sudo tee -a "$STATE/disabled-services" >/dev/null && echo "turned off $s"
  fi
done

echo "== 8/9 Pre-build the screens so the home screen paints at once"
astv env QT_QPA_PLATFORM=offscreen LSBOX_DEMO=1 LSBOX_PRECOMPILE=1 LSBOX_CACHE_DIR=/tmp/lsbox-precompile \
  timeout 60 python3 -I "$LIVE/lsbox_home.py" >/dev/null 2>&1 && echo "screens ready" || echo "pre-build skipped (fine, it happens on first start)"
sudo rm -rf /tmp/lsbox-precompile

echo "== 9/9 Log $TVUSER into LSBox TV (backup: $AUTO.lsbox-bak)"
[ -e "$AUTO.lsbox-bak" ] || sudo cp -a "$AUTO" "$AUTO.lsbox-bak"
OLD=$(sudo sed -n 's/^Session=//p' "$AUTO" | head -1)
case "$OLD" in *.desktop) NEW=lsbox-tv.desktop ;; *) NEW=lsbox-tv ;; esac
if sudo grep -q '^Session=' "$AUTO"; then
  sudo sed -i "s|^Session=.*|Session=$NEW|" "$AUTO"
else
  stop "no Session= line in $AUTO (nothing changed there)"
fi
sudo grep -E '^(User|Session)=' "$AUTO"
echo
echo "Boot time before this change (the next boot will be shorter):"
systemd-analyze 2>/dev/null | head -1
echo
echo "DONE. Reboot to start LSBox TV:  sudo systemctl reboot"
echo "Undo any time:                   bash $SRC/uninstall.sh"
