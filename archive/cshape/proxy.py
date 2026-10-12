"""Logging reverse proxy for third-party harnesses (arm E).

Every harness is pointed at http://127.0.0.1:<port> via ANTHROPIC_BASE_URL (or its equivalent).
The proxy forwards to api.anthropic.com, streams responses back unchanged, and records usage from
both JSON and SSE responses, so tokens and cost are captured the same way for every harness.
It refuses requests that are not for claude-haiku-5-5, and it refuses all requests once the global $ hard cap is reached.
"""
import json, threading, http.server, socketserver
try:
    import httpx
except ImportError:  # newer anthropic SDKs ship httpx2
    import httpx2 as httpx
from . import llm
from .pricing import MODEL, cost

UPSTREAM = "https://api.anthropic.com"

class Recorder:
    def __init__(self):
        self.lock = threading.Lock(); self.calls = []; self.bodies = []; self.status = {}
    def add(self, u, req, resp_text):
        with self.lock:
            self.calls.append(u); self.bodies.append({"request": req, "response": resp_text[:200000]})

def _usage_from(obj, u):
    us = obj.get("usage") or (obj.get("message") or {}).get("usage") or {}
    for k_src, k in (("input_tokens", "input"), ("output_tokens", "output"),
                     ("cache_read_input_tokens", "cache_read"), ("cache_creation_input_tokens", "cache_write")):
        if us.get(k_src) is not None:
            u[k] = max(u[k], us[k_src]) if k != "output" else us[k_src]
    return u

def make_handler(rec: Recorder):
    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def log_message(self, *a):
            pass
        def _fwd(self, method):
            n = int(self.headers.get("content-length") or 0)
            body = self.rfile.read(n) if n else b""
            req = {}
            try:
                req = json.loads(body) if body else {}
            except Exception:
                pass
            is_msg = self.path.split("?")[0].endswith("/v1/messages")
            if is_msg:
                if req.get("model") and not str(req["model"]).startswith(MODEL):
                    return self._err(400, f"proxy: model {req.get('model')} not allowed; only {MODEL}")
                if llm.spent() >= llm.HARD_CAP_USD:
                    return self._err(429, "proxy: hard budget cap reached")
            hdrs = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length", "accept-encoding", "connection")}
            with httpx.Client(timeout=600) as c:
                with c.stream(method, UPSTREAM + self.path, headers=hdrs, content=body) as r:
                    self.send_response(r.status_code)
                    for k, v in r.headers.items():
                        if k.lower() not in ("content-length", "transfer-encoding", "connection", "content-encoding"):
                            self.send_header(k, v)
                    self.send_header("Transfer-Encoding", "chunked"); self.end_headers()
                    buf = []
                    for chunk in r.iter_bytes():
                        buf.append(chunk)
                        self.wfile.write(f"{len(chunk):X}\r\n".encode() + chunk + b"\r\n"); self.wfile.flush()
                    self.wfile.write(b"0\r\n\r\n"); self.wfile.flush()
            text = b"".join(buf).decode("utf-8", "replace")
            if is_msg:
                with rec.lock:
                    rec.status[r.status_code] = rec.status.get(r.status_code, 0) + 1
            if is_msg and r.status_code == 200:
                u = dict(input=0, output=0, cache_read=0, cache_write=0)
                if text.lstrip().startswith("{"):
                    try:
                        _usage_from(json.loads(text), u)
                    except Exception:
                        pass
                else:
                    for line in text.splitlines():
                        if line.startswith("data:"):
                            try:
                                _usage_from(json.loads(line[5:]), u)
                            except Exception:
                                pass
                llm._add(cost(u), u)
                rec.add(u, req, text)
        def _err(self, code, msg):
            b = json.dumps({"type": "error", "error": {"type": "proxy_error", "message": msg}}).encode()
            self.send_response(code); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_POST(self): self._fwd("POST")
        def do_GET(self): self._fwd("GET")
    return H

class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

def start():
    rec = Recorder()
    srv = Server(("127.0.0.1", 0), make_handler(rec))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, rec, f"http://127.0.0.1:{srv.server_address[1]}"
