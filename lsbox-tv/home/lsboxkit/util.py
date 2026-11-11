import json
import os
import subprocess
import time

HOME = os.path.expanduser("~")
CONF_DIR = os.environ.get("LSBOX_CONF_DIR", os.path.join(HOME, ".config", "lsbox-home"))
CACHE_DIR = os.environ.get("LSBOX_CACHE_DIR", os.path.join(HOME, ".cache", "lsbox-home"))
RUNTIME_DIR = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "lsbox-home")
DEMO = os.environ.get("LSBOX_DEMO") == "1"


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    if mode is not None:
        os.chmod(tmp, mode)
    os.replace(tmp, path)


def run(cmd, timeout=5, input_text=None):
    """Run a command, return (exit code, stdout). Never raises."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input_text)
        return r.returncode, r.stdout
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def read_file(path, default=""):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return default
