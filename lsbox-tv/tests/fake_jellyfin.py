#!/usr/bin/env python3
"""Tiny stand-in for Jellyfin, enough for the top shelf and screensaver."""
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

def _png():
    import struct, zlib
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    raw = b"".join(b"\x00" + bytes([40, 60, 120]) * 16 for _ in range(9))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 9, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


PNG = _png()
SEEN = []


def item(i, kind="Movie", **kw):
    d = {"Id": f"id{i}", "Name": f"Movie {i}", "Type": kind, "ProductionYear": 2020 + i,
         "BackdropImageTags": [f"b{i}"], "ImageTags": {"Primary": f"p{i}", "Logo": f"l{i}"},
         "UserData": {"PlayedPercentage": 40.0}}
    d.update(kw)
    return d


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        SEEN.append(self.path)
        auth = self.headers.get("Authorization", "")
        p = self.path.split("?")[0]
        if "/Images/" in p:
            self.send_response(200); self.send_header("Content-Type", "image/png"); self.end_headers()
            self.wfile.write(PNG); return
        if 'Token="good-token"' not in auth:
            self.send_response(401); self.end_headers(); return
        if p == "/Users/Me":
            body = {"Id": "user1"}
        elif p == "/UserItems/Resume":
            body = {"Items": [item(1), item(2, "Episode", SeriesName="Show A", ParentIndexNumber=1, IndexNumber=3,
                                       BackdropImageTags=[], ParentBackdropItemId="s1", ParentBackdropImageTags=["sb"])]}
        elif p == "/Shows/NextUp":
            body = {"Items": [item(3, "Episode", SeriesName="Show B", SeriesId="s2")]}
        elif p == "/Items/Latest":
            body = [item(1), item(4)]   # id1 repeats: should be dropped
        elif p == "/Items":
            body = {"Items": [item(5), item(6)]}
        else:
            self.send_response(404); self.end_headers(); return
        data = json.dumps(body).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
