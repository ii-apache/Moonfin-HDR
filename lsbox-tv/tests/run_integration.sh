#!/bin/bash
# Runs LSBox Home for real (not demo) on a private D-Bus with fake apps and a
# fake Jellyfin, pokes it the way KWin's bridge does, and checks the results.
# Needs: xvfb-run, dbus-run-session, python3 + PySide6.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d)
trap 'kill $(jobs -p) 2>/dev/null; rm -rf "$T"' EXIT
mkdir -p "$T/data/applications" "$T/conf" "$T/rm" "$T/bin"
for a in org.moonfin.linux com.spotify.Client; do
  printf '[Desktop Entry]\nType=Application\nName=%s\nExec=%s/bin/fakeapp %%U\nIcon=none\n' "$a" "$T" > "$T/data/applications/$a.desktop"
done
printf '#!/bin/sh\necho "$@" >> %s/launched\n' "$T" > "$T/bin/fakeapp"; chmod +x "$T/bin/fakeapp"
printf 'JELLYFIN_URL=http://127.0.0.1:18096\nTOKEN_FILE=%s/rm/token\n' "$T" > "$T/rm/config"
echo good-token > "$T/rm/token"
python3 - "$HERE/../home/apps.json" "$T/conf/apps.json" "$T/rm/config" <<'PY'
import json, sys
c = json.load(open(sys.argv[1])); c["jellyfin_config"] = sys.argv[3]
json.dump(c, open(sys.argv[2], "w"))
PY
python3 "$HERE/fake_jellyfin.py" 18096 &
sleep 0.5

cat > "$T/poke.sh" <<POKE
sleep 3
dbus-send --session --print-reply --dest=org.lsbox.Home /Home org.lsbox.Home.windows string:'[{"id":"w1","cls":"org.moonfin.linux","desktop":"org.moonfin.linux","pid":1,"active":true},{"id":"w2","cls":"moonfin-video","pid":1}]' >/dev/null && echo POKE windows ok
sleep 0.5
dbus-send --session --print-reply --dest=org.lsbox.Home /Home org.lsbox.Home.homeKey boolean:false >/dev/null && echo POKE home ok
POKE
chmod +x "$T/poke.sh"

OUT=$(XDG_DATA_DIRS="$T/data" HOME="$T" PATH="$T/bin:$PATH" LSBOX_CONF_DIR="$T/conf" LSBOX_CACHE_DIR="$T/cache" \
  LSBOX_SCREENSHOT="$T/shot.png" LSBOX_SCREENSHOT_DELAY=6000 LIBGL_ALWAYS_SOFTWARE=1 \
  timeout 60 xvfb-run -a -s "-screen 0 1920x1080x24" dbus-run-session -- bash -c "$T/poke.sh & python3 $HERE/../home/lsbox_home.py" 2>&1)
echo "$OUT" | grep -v "pipeline cache"
fail=0
check() { if eval "$2"; then echo "PASS $1"; else echo "FAIL $1"; fail=1; fi; }
check "bus calls accepted" 'echo "$OUT" | grep -q "POKE windows ok" && echo "$OUT" | grep -q "POKE home ok"'
check "skips apps that are not installed" 'echo "$OUT" | grep -q "not installed, skipped: YouTube"'
check "artwork cached" '[ "$(ls "$T/cache/img" 2>/dev/null | wc -l)" -ge 4 ]'
check "screenshot written" '[ -s "$T/shot.png" ]'
check "no QML errors" '! echo "$OUT" | grep -qiE "qml.*(error|TypeError|ReferenceError)|is not defined|Cannot read"'
cp "$T/shot.png" "${SHOT_OUT:-/dev/null}" 2>/dev/null
exit $fail
