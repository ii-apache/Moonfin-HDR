#!/bin/bash
# Puts the box back on Plasma Bigscreen. Run as zzanderr: bash uninstall.sh
# Keeps python3-pyside6 installed (remove it yourself with dnf if you want).
set -u
TVUSER=tv
TVUID=$(id -u "$TVUSER")
TVHOME=$(getent passwd "$TVUSER" | cut -d: -f6)
TVENV="HOME=$TVHOME XDG_RUNTIME_DIR=/run/user/$TVUID DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$TVUID/bus"
AUTO=$(sudo grep -rlsE "^User=$TVUSER\b" /etc/plasmalogin.conf.d /etc/plasmalogin.conf 2>/dev/null | grep -v lsbox-bak | head -1)
if [ -n "$AUTO" ] && [ -e "$AUTO.lsbox-bak" ]; then
  sudo cp -a "$AUTO.lsbox-bak" "$AUTO" && sudo rm -f "$AUTO.lsbox-bak"
  echo "autologin restored:"; sudo grep -E '^(User|Session)=' "$AUTO"
fi
sudo -u "$TVUSER" env $TVENV systemctl --user disable lsbox-home.service 2>/dev/null
sudo rm -f "$TVHOME/.config/systemd/user/lsbox-home.service" \
  "$TVHOME/.config/systemd/user/plasma-plasmashell.service.d/lsbox.conf"
sudo rmdir "$TVHOME/.config/systemd/user/plasma-plasmashell.service.d" 2>/dev/null
sudo -u "$TVUSER" env $TVENV systemctl --user daemon-reload
sudo -u "$TVUSER" env $TVENV systemctl --user unset-environment LSBOX_TV 2>/dev/null
sudo -u "$TVUSER" env $TVENV kwriteconfig6 --file ksplashrc --group KSplash --key Engine --delete
sudo -u "$TVUSER" env $TVENV kwriteconfig6 --file ksplashrc --group KSplash --key Theme --delete
sudo -u "$TVUSER" env $TVENV kwriteconfig6 --file kwinrc --group Plugins --key squashEnabled --delete
sudo -u "$TVUSER" env $TVENV kwriteconfig6 --file kwinrc --group Plugins --key magiclampEnabled --delete
sudo rm -f /usr/local/bin/lsbox-tv-session /usr/share/wayland-sessions/lsbox-tv.desktop
sudo rm -rf "$TVHOME/.local/share/lsbox-home"
echo "Kept your app list in $TVHOME/.config/lsbox-home (delete it if you like)."
echo "DONE. Reboot to get Plasma Bigscreen back:  sudo systemctl reboot"
