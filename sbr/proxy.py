"""Logging reverse proxy that every harness talks to instead of api.anthropic.com.

It forwards requests unchanged and streams responses back, and for each Messages call it records the
token usage and the prompt size (input + cache read + cache write). That prompt size is the context
window the model saw on that call, so a run's window-size curve, its compactions (a drop in prompt
size) and its cache hit rate all come straight from these logs, the same way for every harness.

Limits, so every harness gets the same budget:
  - only MODEL is allowed through
  - a per-task dollar cap: once a task has spent it, every further call gets a 429
  - a global hard cap across the whole comparison, kept in OUT/ledger.json
"""
import fcntl, json, threading, time, http.server, socketserver
import httpx
from .config import MODEL, OUT, HARD_CAP_USD

UPSTREAM = "https://api.anthropic.com"
LEDGER = OUT / "ledger.json"

PRICES = {  # USD per million tokens; prompts over 100k tokens bill at the higher tier
    "le100k": dict(input=0.10, cache_write=0.125, cache_read=0.01, output=0.50),
    "gt100k": dict(input=0.50, cache_write=0.625, cache_read=0.05, output=2.50),
}

def cost(u):
    prompt = u["input"] + u["cache_read"] + u["cache_write"]
    p = PRICES["gt100k" if prompt > 100_000 else "le100k"]
    return sum(u[k] * p[k] for k in p) / 1e6

def spent():
    return json.loads(LEDGER.read_text())["total_usd"] if LEDGER.exists() else 0.0

def _charge(usd):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0); txt = f.read()
        d = json.loads(txt) if txt else {"total_usd": 0.0, "calls": 0}
        d["total_usd"] += usd; d["calls"] += 1
        f.seek(0); f.truncate(); f.write(json.dumps(d))

class Recorder:
    """Per-task call log. `budget` is this task's dollar cap."""
    def __init__(self, budget, log_path):
        self.budget = budget; self.log_path = log_path
        self.lock = threading.Lock(); self.calls = []; self.status = {}; self.refused = 0

    @property
    def usd(self):
        return sum(c["usd"] for c in self.calls)

    def add(self, row):
        with self.lock:
            self.calls.append(row)
            with open(self.log_path, "a") as f:
                f.write(json.dumps(row) + "\n")

def _usage(obj, u):
    us = obj.get("usage") or (obj.get("message") or {}).get("usage") or {}
    for src, k in (("input_tokens", "input"), ("output_tokens", "output"),
                   ("cache_read_input_tokens", "cache_read"), ("cache_creation_input_tokens", "cache_write")):
        if us.get(src) is not None:
            u[k] = us[src] if k == "output" else max(u[k], us[src])
    sr = obj.get("stop_reason") or (obj.get("delta") or {}).get("stop_reason")
    if sr:
        u["stop_reason"] = sr
    return u

def _handler(rec):
    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _err(self, code, msg):
            b = json.dumps({"type": "error", "error": {"type": "rate_limit_error" if code == 429 else "invalid_request_error",
                                                         "message": msg}}).encode()
            self.send_response(code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(b)))
            self.end_headers(); self.wfile.write(b)

        def _fwd(self, method):
            n = int(self.headers.get("content-length") or 0)
            body = self.rfile.read(n) if n else b""
            try:
                req = json.loads(body) if body else {}
            except ValueError:
                req = {}
            is_msg = self.path.split("?")[0].endswith("/v1/messages")
            if is_msg:
                if req.get("model") and not str(req["model"]).startswith(MODEL):
                    return self._err(400, f"proxy: only {MODEL} is allowed, got {req.get('model')}")
                if spent() >= HARD_CAP_USD:
                    return self._err(429, "proxy: global hard cap reached")
                if rec.usd >= rec.budget:
                    rec.refused += 1
                    return self._err(429, f"proxy: task budget ${rec.budget:.2f} spent")
            hdrs = {k: v for k, v in self.headers.items()
                    if k.lower() not in ("host", "content-length", "accept-encoding", "connection")}
            t0 = time.time()
            with httpx.Client(timeout=httpx.Timeout(600, connect=15, read=120)) as c:
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
                    status = r.status_code
            if not is_msg:
                return
            with rec.lock:
                rec.status[status] = rec.status.get(status, 0) + 1
            if status != 200:
                return
            text = b"".join(buf).decode("utf-8", "replace")
            u = dict(input=0, output=0, cache_read=0, cache_write=0)
            if text.lstrip().startswith("{"):
                try: _usage(json.loads(text), u)
                except ValueError: pass
            else:
                for line in text.splitlines():
                    if line.startswith("data:"):
                        try: _usage(json.loads(line[5:]), u)
                        except ValueError: pass
            usd = cost(u)
            _charge(usd)
            rec.add(dict(t=round(t0, 3), s=round(time.time() - t0, 2), usd=round(usd, 6),
                         prompt=u["input"] + u["cache_read"] + u["cache_write"], **u,
                         n_messages=len(req.get("messages") or []), n_tools=len(req.get("tools") or [])))

        def do_POST(self): self._fwd("POST")
        def do_GET(self): self._fwd("GET")
    return H

class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

def start(budget, log_path, host="127.0.0.1"):
    """Start a proxy for one task. Returns (server, recorder, base_url)."""
    rec = Recorder(budget, log_path)
    srv = _Server((host, 0), _handler(rec))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, rec, f"http://{host}:{srv.server_address[1]}"
