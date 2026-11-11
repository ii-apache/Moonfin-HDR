"""Box controls for Control Center: sound output + volume, Bluetooth,
picture (HDR, refresh, scale via kscreen-doctor) and health readings."""
import glob
import json
import os
import re
import shutil

from .util import read_file, run

# ---------------------------------------------------------------- sound

def parse_sinks(json_text, default_name):
    try:
        sinks = json.loads(json_text)
    except ValueError:
        return []
    out = []
    for s in sinks:
        name = s.get("name", "")
        if not name or name.endswith(".monitor"):
            continue
        label = s.get("description") or name
        out.append({"name": name, "label": nice_sink(label), "active": name == default_name})
    return out


def nice_sink(label):
    """'GA107 High Definition Audio Controller Digital Stereo (HDMI 2)' -> 'TV (HDMI 2)'."""
    hdmi = re.search(r"\((HDMI[^)]*)\)", label)
    l = re.sub(r"\([^)]*\)", "", label)
    for junk in ("Digital Stereo", "Digital Surround [0-9.]*", "High Definition Audio Controller",
                 r"\b[A-Z]{2}[0-9]{3}\b", "Family 17h/19h", "Cannon Lake PCH cAVS", "Built-in Audio"):
        l = re.sub(junk, "", l)
    l = re.sub(r"\s+", " ", l).strip(" -")
    if hdmi and not l:
        return f"TV ({hdmi.group(1)})"
    return l or label


def sinks():
    if not shutil.which("pactl"):
        return []
    _, default = run(["pactl", "get-default-sink"], timeout=3)
    code, text = run(["pactl", "-f", "json", "list", "sinks"], timeout=4)
    return parse_sinks(text, default.strip()) if code == 0 else []


def set_sink(name):
    run(["pactl", "set-default-sink", name], timeout=3)


def parse_wpctl_volume(text):
    m = re.search(r"Volume:\s*([0-9.]+)", text)
    if not m:
        return None
    return {"level": int(round(float(m.group(1)) * 100)), "muted": "MUTED" in text}


def pw_volume():
    code, text = run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"], timeout=3)
    return parse_wpctl_volume(text) if code == 0 else None


def pw_step(delta):
    if delta == 0:
        run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"], timeout=3)
    else:
        sign = "+" if delta > 0 else "-"
        run(["wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", f"{abs(delta)}%{sign}"], timeout=3)
    return pw_volume()


def cec_status_to_volume(status):
    """CEC audio status byte -> {level, muted} or None when unknown (0x7F)."""
    if status is None or status < 0 or (status & 0x7F) == 0x7F:
        return None
    return {"level": min(100, status & 0x7F), "muted": bool(status & 0x80)}

# ---------------------------------------------------------------- bluetooth

_DEV = re.compile(r"^Device ([0-9A-F:]{17}) (.*)$", re.M)


def parse_devices(text):
    return [{"mac": m, "name": n.strip()} for m, n in _DEV.findall(text)]


def bt_devices():
    if not shutil.which("bluetoothctl"):
        return []
    _, all_text = run(["bluetoothctl", "devices"], timeout=4)
    _, paired_text = run(["bluetoothctl", "devices", "Paired"], timeout=4)
    _, conn_text = run(["bluetoothctl", "devices", "Connected"], timeout=4)
    paired = {d["mac"] for d in parse_devices(paired_text)}
    conn = {d["mac"] for d in parse_devices(conn_text)}
    out = []
    for d in parse_devices(all_text):
        if re.fullmatch(r"([0-9A-F]{2}-){5}[0-9A-F]{2}", d["name"].replace(":", "-")):
            continue  # nameless beacons
        d["paired"] = d["mac"] in paired
        d["connected"] = d["mac"] in conn
        out.append(d)
    out.sort(key=lambda d: (not d["connected"], not d["paired"], d["name"].lower()))
    return out


def bt_scan(seconds=15):
    run(["bluetoothctl", "--timeout", str(seconds), "scan", "on"], timeout=seconds + 5)


def bt_pair(mac):
    code, out = run(["bluetoothctl", "--timeout", "25", "pair", mac], timeout=30)
    run(["bluetoothctl", "trust", mac], timeout=5)
    c2, out2 = run(["bluetoothctl", "--timeout", "15", "connect", mac], timeout=20)
    ok = "Connection successful" in out2 or "Pairing successful" in out or "AlreadyExists" in out
    return ok


def bt_action(action, mac):
    """connect, disconnect, remove"""
    run(["bluetoothctl", "--timeout", "15", action, mac], timeout=20)

# ---------------------------------------------------------------- picture

def parse_kscreen(json_text):
    try:
        data = json.loads(json_text)
    except ValueError:
        return {}
    outs = [o for o in data.get("outputs", []) if o.get("enabled") and o.get("connected")]
    if not outs:
        return {}
    o = outs[0]
    modes = o.get("modes", [])
    cur = next((m for m in modes if str(m.get("id")) == str(o.get("currentModeId"))), None)
    size = (cur or {}).get("size", {})
    w, h = size.get("width"), size.get("height")
    rates = sorted({round(m.get("refreshRate", 0), 3) for m in modes
                    if m.get("size", {}).get("width") == w and m.get("size", {}).get("height") == h})
    hdr = o.get("hdr")
    if isinstance(hdr, dict):
        hdr = hdr.get("enabled")
    caps = o.get("capabilities")
    hdr_capable = hdr is not None or (isinstance(caps, int) and bool(caps & 0x80))
    return {"output": o.get("name", ""), "width": w, "height": h,
            "refresh": round((cur or {}).get("refreshRate", 0), 3), "refreshes": rates,
            "scale": round(float(o.get("scale", 1)), 2), "hdr": bool(hdr), "hdrCapable": hdr_capable}


def display():
    if not shutil.which("kscreen-doctor"):
        return {}
    code, text = run(["kscreen-doctor", "-j"], timeout=5)
    return parse_kscreen(text) if code == 0 else {}


def set_display(d, what, value):
    out = d.get("output")
    if not out:
        return
    if what == "hdr":
        run(["kscreen-doctor", f"output.{out}.hdr.{'enable' if value else 'disable'}"], timeout=8)
    elif what == "refresh":
        run(["kscreen-doctor", f"output.{out}.mode.{d['width']}x{d['height']}@{value:g}"], timeout=8)
    elif what == "scale":
        run(["kscreen-doctor", f"output.{out}.scale.{value:g}"], timeout=8)

# ---------------------------------------------------------------- health

def cpu_temp():
    for hw in glob.glob("/sys/class/hwmon/hwmon*"):
        if read_file(os.path.join(hw, "name")).strip() in ("coretemp", "k10temp", "zenpower"):
            t = read_file(os.path.join(hw, "temp1_input")).strip()
            if t.isdigit():
                return int(t) // 1000
    return None


def gpu():
    if not shutil.which("nvidia-smi"):
        return None, None
    code, text = run(["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu",
                      "--format=csv,noheader,nounits"], timeout=4)
    try:
        t, u = [int(x.strip()) for x in text.splitlines()[0].split(",")[:2]]
        return t, u
    except (ValueError, IndexError):
        return None, None


def parse_wireless(text):
    """/proc/net/wireless -> link quality percent (or None)."""
    for line in text.splitlines()[2:]:
        parts = line.split()
        if len(parts) >= 4:
            try:
                q = float(parts[2].rstrip("."))
                return max(0, min(100, int(q * 100 / 70)))
            except ValueError:
                pass
    return None


def parse_meminfo(text):
    vals = {}
    for line in text.splitlines():
        k, _, v = line.partition(":")
        if v.strip().split():
            vals[k] = int(v.strip().split()[0])
    tot, avail = vals.get("MemTotal"), vals.get("MemAvailable")
    if not tot or avail is None:
        return None
    return int(round((tot - avail) * 100 / tot))


def health():
    du = shutil.disk_usage("/")
    disk = int(round(du.used * 100 / du.total))
    gt, gu = gpu()
    h = {"cpuTemp": cpu_temp(), "gpuTemp": gt, "gpuLoad": gu,
         "wifi": parse_wireless(read_file("/proc/net/wireless")),
         "ram": parse_meminfo(read_file("/proc/meminfo")), "disk": disk,
         "diskText": f"{du.used / 1e9:.0f} of {du.total / 1e9:.0f} GB"}
    warn = []
    if (h["cpuTemp"] or 0) >= 90:
        warn.append("CPU hot")
    if (h["gpuTemp"] or 0) >= 83:
        warn.append("GPU hot")
    if disk >= 85:
        warn.append("Storage almost full")
    if h["wifi"] is not None and h["wifi"] < 35:
        warn.append("Weak Wi-Fi")
    if (h["ram"] or 0) >= 90:
        warn.append("Memory almost full")
    h["warnings"] = warn
    return h


def controller_batteries():
    """[(name, percent)] for game controllers and other device batteries."""
    out = []
    for ps in glob.glob("/sys/class/power_supply/*"):
        if read_file(os.path.join(ps, "scope")).strip() != "Device":
            continue
        cap = read_file(os.path.join(ps, "capacity")).strip()
        if cap.isdigit():
            name = read_file(os.path.join(ps, "model_name")).strip() or os.path.basename(ps)
            out.append((name, int(cap)))
    return out
