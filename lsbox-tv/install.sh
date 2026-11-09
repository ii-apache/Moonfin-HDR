#!/bin/bash
# LSBox TV installer. Run as the admin user (zzanderr) on LSBox, from this folder:
#   bash install.sh
# Undo everything with: bash uninstall.sh
set -u
SRC=$(cd "$(dirname "$0")" && pwd)
TVUSER=tv
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
AUTO=$(sudo grep -rlsE "^User=$TVUSER\b" /etc/plasmalogin.conf.d /etc/plasmalogin.conf 2>/dev/null | head -1)
[ -n "$AUTO" ] || stop "could not find the Plasma Login Manager autologin file for $TVUSER"
echo "Bigscreen session: $BIG_EXEC"
echo "Autologin file:    $AUTO"

echo "== 1/6 Qt for Python (PySide6), uses the Qt already installed"
sudo dnf install -y python3-pyside6 || stop "dnf install failed"
python3 -c "import PySide6.QtQuick, PySide6.QtDBus" || stop "PySide6 does not import"

echo "== 2/6 Home screen app -> $TVHOME/.local/share/lsbox-home"
sudo install -d -o "$TVUSER" -g "$TVUSER" "$TVHOME/.local/share/lsbox-home/qml" "$TVHOME/.config/lsbox-home" \
  "$TVHOME/.config/systemd/user/plasma-plasmashell.service.d"
sudo install -o "$TVUSER" -g "$TVUSER" -m 644 "$SRC"/home/lsbox_home.py "$SRC"/home/kwin-bridge.js "$SRC"/home/apps.json \
  "$TVHOME/.local/share/lsbox-home/"
sudo install -o "$TVUSER" -g "$TVUSER" -m 644 "$SRC"/home/qml/*.qml "$TVHOME/.local/share/lsbox-home/qml/"

echo "== 3/6 User services for $TVUSER"
sudo install -o "$TVUSER" -g "$TVUSER" -m 644 "$SRC/session/lsbox-home.service" "$TVHOME/.config/systemd/user/lsbox-home.service"
sudo install -o "$TVUSER" -g "$TVUSER" -m 644 "$SRC/session/plasmashell-lsbox.conf" \
  "$TVHOME/.config/systemd/user/plasma-plasmashell.service.d/lsbox.conf"
TVENV="HOME=$TVHOME XDG_RUNTIME_DIR=/run/user/$TVUID DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$TVUID/bus"
sudo -u "$TVUSER" env $TVENV systemctl --user daemon-reload
sudo -u "$TVUSER" env $TVENV systemctl --user enable lsbox-home.service || stop "could not enable lsbox-home.service"

echo "== 4/6 Session 'LSBox TV'"
sed "s|@BIGSCREEN_SESSION@|$BIG_EXEC|" "$SRC/session/lsbox-tv-session" | sudo tee /usr/local/bin/lsbox-tv-session >/dev/null
sudo chmod 755 /usr/local/bin/lsbox-tv-session
sudo sed -e 's|^Exec=.*|Exec=/usr/local/bin/lsbox-tv-session|' -e 's|^TryExec=.*|TryExec=/usr/local/bin/lsbox-tv-session|' \
  -e 's|^Name=.*|Name=LSBox TV|' -e '/^Name\[/d' -e '/^Comment/d' "$BIG_DESKTOP" | sudo tee /usr/share/wayland-sessions/lsbox-tv.desktop >/dev/null

echo "== 5/6 Faster login: no splash screen, no file indexer for $TVUSER"
sudo -u "$TVUSER" env $TVENV kwriteconfig6 --file ksplashrc --group KSplash --key Engine none
sudo -u "$TVUSER" env $TVENV kwriteconfig6 --file ksplashrc --group KSplash --key Theme None
sudo -u "$TVUSER" env $TVENV kwriteconfig6 --file baloofilerc --group "Basic Settings" --key "Indexing-Enabled" false
# Apps and Home switch instantly (no minimise animation; Home hides itself
# behind apps so Moonfin's HDR video layer stays visible).
sudo -u "$TVUSER" env $TVENV kwriteconfig6 --file kwinrc --group Plugins --key squashEnabled false
sudo -u "$TVUSER" env $TVENV kwriteconfig6 --file kwinrc --group Plugins --key magiclampEnabled false

echo "== 6/6 Log $TVUSER into LSBox TV (backup: $AUTO.lsbox-bak)"
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
echo "DONE. Reboot to start LSBox TV:  sudo systemctl reboot"
echo "Undo any time:                   bash $SRC/uninstall.sh"
