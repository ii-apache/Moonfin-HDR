"""Phone remote: a small web page served by the box on your home network.
Pair once with the 4-digit code shown in Control Center > Phone remote."""
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KEYS = {"up", "down", "left", "right", "ok", "back", "home", "menu", "playpause",
        "next", "previous", "volumeup", "volumedown", "mute"}


class RemoteServer:
    """handler(kind, value) is called from the server thread for 'key', 'text'
    and 'app'; state() returns a JSON-able dict. Tokens persist via save()."""

    def __init__(self, port, pin, tokens, handler, state, save_tokens):
        self.port, self.pin = port, pin
        self.tokens = set(tokens)
        self.handler, self.state, self.save_tokens = handler, state, save_tokens
        self.fails = []
        self.total_fails = 0   # too many wrong codes: pairing stops until a new code is made
        self.httpd = None

    def start(self):
        outer = self

        class H(BaseHTTPRequestHandler):
            server_version = "LSBox"

            def log_message(self, *a):
                pass

            def _send(self, code, body=b"", ctype="application/json", headers=()):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Frame-Options", "DENY")
                for k, v in headers:
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def _token_ok(self):
                for part in self.headers.get("Cookie", "").split(";"):
                    k, _, v = part.strip().partition("=")
                    if k == "lsbox" and v in outer.tokens:
                        return True
                return False

            def _body(self):
                n = min(int(self.headers.get("Content-Length", "0") or 0), 4096)
                try:
                    return json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return {}

            def do_GET(self):
                if self.path in ("/", "/index.html"):
                    self._send(200, PAGE.encode(), "text/html; charset=utf-8")
                elif self.path == "/api/state":
                    if not self._token_ok():
                        return self._send(401, b'{"paired":false}')
                    self._send(200, json.dumps(outer.state()).encode())
                else:
                    self._send(404, b"{}")

            def do_POST(self):
                # Only this page may call the API (no other site, no other port).
                origin = self.headers.get("Origin")
                if origin and origin.split("://", 1)[-1] != self.headers.get("Host", ""):
                    return self._send(403, b'{"error":"origin"}')
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    return self._send(415, b"{}")
                body = self._body()
                if self.path == "/api/pair":
                    now = time.time()
                    outer.fails = [t for t in outer.fails if now - t < 60]
                    if outer.total_fails >= 30:
                        return self._send(423, b'{"error":"locked"}')
                    if len(outer.fails) >= 5:
                        return self._send(429, b'{"error":"wait a minute"}')
                    if not secrets.compare_digest(str(body.get("pin", "")), outer.pin):
                        outer.fails.append(now)
                        outer.total_fails += 1
                        return self._send(403, b'{"error":"wrong code"}')
                    tok = secrets.token_hex(16)
                    outer.tokens.add(tok)
                    outer.save_tokens(sorted(outer.tokens))
                    return self._send(200, b'{"paired":true}', headers=[
                        ("Set-Cookie", f"lsbox={tok}; Max-Age=31536000; Path=/; HttpOnly; SameSite=Strict")])
                if not self._token_ok():
                    return self._send(401, b'{"paired":false}')
                if self.path == "/api/key" and body.get("key") in KEYS:
                    outer.handler("key", body["key"])
                elif self.path == "/api/text" and isinstance(body.get("text"), str):
                    outer.handler("text", body["text"][:200])
                elif self.path == "/api/app" and isinstance(body.get("key"), str):
                    outer.handler("app", body["key"][:64])
                else:
                    return self._send(400, b"{}")
                self._send(200, b'{"ok":true}')

        try:
            self.httpd = ThreadingHTTPServer(("0.0.0.0", self.port), H)
        except OSError:
            self.httpd = None
            return False
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return True

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes"><title>LSBox Remote</title>
<style>
:root{--bg:#0d0e12;--panel:#1b1d24;--btn:#262933;--txt:#f2f3f5;--dim:#9aa0ab;--acc:#7c5cff}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent;user-select:none}
body{margin:0;background:var(--bg);color:var(--txt);font:16px -apple-system,system-ui,sans-serif;
padding:16px;padding-top:max(16px,env(safe-area-inset-top));display:flex;flex-direction:column;gap:16px;min-height:100vh}
h1{font-size:18px;margin:0;color:var(--dim);font-weight:600}
.pad{position:relative;width:min(78vw,320px);aspect-ratio:1;margin:8px auto;border-radius:50%;background:var(--panel)}
.pad button{position:absolute;border:0;background:transparent;color:var(--txt);font-size:28px;width:33%;height:33%}
.pad .u{top:0;left:33.5%}.pad .d{bottom:0;left:33.5%}.pad .l{left:0;top:33.5%}.pad .r{right:0;top:33.5%}
.pad .ok{top:30%;left:30%;width:40%;height:40%;border-radius:50%;background:var(--btn);font-size:20px;font-weight:600}
.row{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.row button,.apps button,form button{border:0;border-radius:14px;background:var(--btn);color:var(--txt);padding:14px 0;font-size:15px}
.row button:active,.pad button:active,.apps button:active{background:var(--acc)}
.apps{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
form{display:flex;gap:8px}input{flex:1;border:0;border-radius:14px;padding:14px;background:var(--panel);color:var(--txt);font-size:16px}
form button{padding:0 18px}#np{background:var(--panel);border-radius:14px;padding:12px 14px;color:var(--dim);min-height:20px}
#pair{display:none;flex-direction:column;gap:12px;margin-top:20vh;text-align:center}
#pair input{text-align:center;font-size:32px;letter-spacing:12px}
</style></head><body>
<div id="pair"><h1>Enter the code shown on the TV<br>(Control Center &rsaquo; Phone remote)</h1>
<input id="pin" inputmode="numeric" maxlength="4" autocomplete="off"><div id="perr" style="color:#ff6b6b"></div></div>
<div id="main" style="display:none;flex-direction:column;gap:16px">
<h1>LSBox</h1><div id="np">Nothing playing</div>
<div class="pad"><button class="u" data-k="up">&#9650;</button><button class="l" data-k="left">&#9664;</button>
<button class="ok" data-k="ok">OK</button><button class="r" data-k="right">&#9654;</button><button class="d" data-k="down">&#9660;</button></div>
<div class="row"><button data-k="back">Back</button><button data-k="home">Home</button><button data-k="menu">Menu</button><button data-k="playpause">&#9199;</button></div>
<div class="row"><button data-k="previous">&#9198;</button><button data-k="volumedown">Vol &minus;</button><button data-k="volumeup">Vol +</button><button data-k="next">&#9197;</button></div>
<form id="tf"><input id="txt" placeholder="Type or search" autocomplete="off"><button>Send</button></form>
<div class="apps" id="apps"></div></div>
<script>
const $=s=>document.querySelector(s);
async function post(p,b){const r=await fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});if(r.status==401)showPair();return r}
function showPair(){$('#pair').style.display='flex';$('#main').style.display='none';$('#pin').focus()}
function showMain(){$('#pair').style.display='none';$('#main').style.display='flex'}
document.querySelectorAll('[data-k]').forEach(b=>b.addEventListener('click',()=>{post('/api/key',{key:b.dataset.k});if(navigator.vibrate)navigator.vibrate(8)}));
$('#tf').addEventListener('submit',e=>{e.preventDefault();post('/api/text',{text:$('#txt').value});$('#txt').value=''});
$('#pin').addEventListener('input',async e=>{if(e.target.value.length==4){const r=await post('/api/pair',{pin:e.target.value});
if(r.ok){showMain();refresh()}else{$('#perr').textContent=r.status==429?'Too many tries, wait a minute':r.status==423?'Locked: make a new code on the TV':'Wrong code';e.target.value=''}}});
async function refresh(){const r=await fetch('/api/state');if(r.status==401){showPair();return}showMain();const s=await r.json();
$('#np').textContent=s.nowPlaying&&s.nowPlaying.active?((s.nowPlaying.playing?'▶ ':'⏸ ')+s.nowPlaying.title+(s.nowPlaying.artist?' · '+s.nowPlaying.artist:'')):'Nothing playing';
const a=$('#apps');if(!a.dataset.done){a.dataset.done=1;s.apps.forEach(x=>{const b=document.createElement('button');b.textContent=x.name;b.onclick=()=>post('/api/app',{key:x.key});a.appendChild(b)})}}
refresh();setInterval(()=>{if(!document.hidden)refresh()},4000);
</script></body></html>"""
