#!/bin/bash
# Puts the box back on Plasma Bigscreen. Run as zzanderr: bash uninstall.sh
# Keeps python3-pyside6 and playerctl installed (remove them with dnf if you want).
set -u
TVUSER=tv
STATE=/var/lib/lsbox-tv
TVUID=$(id -u "$TVUSER")
TVHOME=$(getent passwd "$TVUSER" | cut -d: -f6)
TVENV="HOME=$TVHOME XDG_RUNTIME_DIR=/run/user/$TVUID DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$TVUID/bus"
astv() { sudo -u "$TVUSER" env $TVENV "$@"; }
AUTO=$(sudo grep -rlsE "^User=$TVUSER\b" /etc/plasmalogin.conf.d /etc/plasmalogin.conf 2>/dev/null | grep -v lsbox-bak | head -1)
if [ -n "$AUTO" ] && [ -e "$AUTO.lsbox-bak" ]; then
  sudo cp -a "$AUTO.lsbox-bak" "$AUTO" && sudo rm -f "$AUTO.lsbox-bak"
  echo "autologin restored:"; sudo grep -E '^(User|Session)=' "$AUTO"
fi
astv systemctl --user disable lsbox-home.service 2>/dev/null
sudo rm -f "$TVHOME/.config/systemd/user/lsbox-home.service" \
  "$TVHOME/.config/systemd/user/plasma-plasmashell.service.d/lsbox.conf"
sudo rmdir "$TVHOME/.config/systemd/user/plasma-plasmashell.service.d" 2>/dev/null
astv systemctl --user daemon-reload
astv systemctl --user unset-environment LSBOX_TV 2>/dev/null
astv kwriteconfig6 --file ksplashrc --group KSplash --key Engine --delete
astv kwriteconfig6 --file ksplashrc --group KSplash --key Theme --delete
astv kwriteconfig6 --file kwinrc --group Plugins --key squashEnabled --delete
astv kwriteconfig6 --file kwinrc --group Plugins --key magiclampEnabled --delete
for m in printmanager smbwatcher remotenotifier browserintegrationreminder freespacenotifier; do
  astv kwriteconfig6 --file kded6rc --group "Module-$m" --key autoload --delete
done
if [ -f "$STATE/disabled-services" ]; then
  for s in $(sort -u "$STATE/disabled-services"); do sudo systemctl enable "$s" >/dev/null 2>&1 && echo "turned $s back on"; done
fi
sudo rm -rf "$STATE"
sudo rm -f /etc/modules-load.d/lsbox-uinput.conf /etc/udev/rules.d/70-lsbox-uinput.rules
sudo udevadm control --reload
if sudo firewall-cmd --get-zones 2>/dev/null | grep -qw tvbox; then
  sudo firewall-cmd -q --permanent --zone=tvbox --remove-rich-rule='rule priority="-1" family="ipv4" source address="192.168.50.26" port port="8095" protocol="tcp" reject' 2>/dev/null
  sudo firewall-cmd -q --permanent --zone=tvbox --remove-rich-rule='rule family="ipv4" source address="192.168.50.0/24" port port="8095" protocol="tcp" accept' 2>/dev/null
  sudo firewall-cmd -q --reload
fi
sudo rm -f /usr/local/bin/lsbox-tv-session /usr/share/wayland-sessions/lsbox-tv.desktop
sudo rm -rf "$TVHOME/.local/share/lsbox-home" "$TVHOME/.local/share/lsbox-home.prev" "$TVHOME/.local/share/lsbox-home.bad" \
  "$TVHOME/.local/share/lsbox-home.new" "$TVHOME/.local/share/lsbox-src" "$TVHOME/.local/share/lsbox-guard" "$TVHOME/.cache/lsbox-home"
echo "Kept your settings in $TVHOME/.config/lsbox-home (delete it if you like)."
echo "box-heartbeat keeps its home screen check; it only applies inside LSBox TV, so it is harmless."
echo "DONE. Reboot to get Plasma Bigscreen back:  sudo systemctl reboot"
