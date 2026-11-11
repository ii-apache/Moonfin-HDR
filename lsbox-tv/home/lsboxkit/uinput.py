"""A small virtual keyboard (Linux uinput) so the phone remote can press
keys in any app. Needs /dev/uinput access (installer adds a uaccess rule)."""
import fcntl
import os
import struct
import time

UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_DEV_SETUP = 0x405C5503
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
EV_SYN, EV_KEY, SYN_REPORT = 0, 1, 0

KEYS = {"esc": 1, "backspace": 14, "tab": 15, "enter": 28, "shift": 42, "space": 57,
        "up": 103, "left": 105, "right": 106, "down": 108, "menu": 127, "mute": 113,
        "volumedown": 114, "volumeup": 115, "next": 163, "playpause": 164, "previous": 165,
        "back": 158, "homepage": 172}
_ROWS = [("1234567890-=", 2), ("qwertyuiop[]", 16), ("asdfghjkl;'`", 30), ("\\zxcvbnm,./", 43)]
_SHIFTED = {'!': '1', '@': '2', '#': '3', '$': '4', '%': '5', '^': '6', '&': '7', '*': '8', '(': '9',
            ')': '0', '_': '-', '+': '=', '{': '[', '}': ']', ':': ';', '"': "'", '~': '`', '|': '\\',
            '<': ',', '>': '.', '?': '/'}
CHARS = {}
for chars, first in _ROWS:
    for i, c in enumerate(chars):
        CHARS[c] = first + i


def char_key(c):
    """-> (keycode, shift) for a US-layout character, or None."""
    if c == " ":
        return KEYS["space"], False
    if c == "\n":
        return KEYS["enter"], False
    if c in CHARS:
        return CHARS[c], False
    if c.isalpha() and c.lower() in CHARS:
        return CHARS[c.lower()], True
    if c in _SHIFTED:
        return CHARS[_SHIFTED[c]], True
    return None


class VirtualKeyboard:
    def __init__(self):
        self.fd = None
        try:
            fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        except OSError:
            return
        try:
            fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
            for code in set(KEYS.values()) | set(CHARS.values()):
                fcntl.ioctl(fd, UI_SET_KEYBIT, code)
            setup = struct.pack("HHHH80sI", 0x06, 0x1209, 0x4C53, 1, b"LSBox phone remote", 0)
            fcntl.ioctl(fd, UI_DEV_SETUP, setup)
            fcntl.ioctl(fd, UI_DEV_CREATE)
            self.fd = fd
            time.sleep(0.2)  # let the compositor pick the device up
        except OSError:
            os.close(fd)

    @property
    def ok(self):
        return self.fd is not None

    def _emit(self, etype, code, value):
        now = time.time()
        os.write(self.fd, struct.pack("llHHi", int(now), int((now % 1) * 1e6), etype, code, value))

    def _key(self, code, down):
        self._emit(EV_KEY, code, 1 if down else 0)
        self._emit(EV_SYN, SYN_REPORT, 0)

    def tap(self, name):
        code = KEYS.get(name)
        if self.fd is None or code is None:
            return False
        self._key(code, True)
        self._key(code, False)
        return True

    def type_text(self, text):
        if self.fd is None:
            return False
        for c in text[:200]:
            k = char_key(c)
            if not k:
                continue
            code, shift = k
            if shift:
                self._key(KEYS["shift"], True)
            self._key(code, True)
            self._key(code, False)
            if shift:
                self._key(KEYS["shift"], False)
            time.sleep(0.008)
        return True

    def close(self):
        if self.fd is not None:
            try:
                fcntl.ioctl(self.fd, UI_DEV_DESTROY)
            except OSError:
                pass
            os.close(self.fd)
            self.fd = None
