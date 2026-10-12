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
import os
CALL_DEADLINE_S = 300
# Parity normalization (2026-10-11): claude-haiku-5-5 thinks adaptively unless a request says otherwise, and the
# harnesses differ (Claude Code/OpenCode ask for adaptive thinking + an effort level, Aider/mini/SWE-agent send
# nothing and get the model default). With SBR_THINKING=disabled every forwarded Messages call gets
# thinking={"type":"disabled"} and no output_config.effort, so all proxied harnesses run at the same level: none.
# Cursor's equivalent is its "No Thinking" model id. Everything else in the request is forwarded unchanged.
THINKING = os.environ.get("SBR_THINKING", "")

def normalize(req, thinking=None):
    """Returns the request to forward (or None to forward the original bytes unchanged)."""
    if (thinking or THINKING) != "disabled":
        return None
    out = dict(req)
    out["thinking"] = {"type": "disabled"}
    oc = dict(out.get("output_config") or {})
    oc.pop("effort", None)
    if oc: out["output_config"] = oc
    else: out.pop("output_config", None)
    cm = out.get("context_management")
    if isinstance(cm, dict) and cm.get("edits"):  # thinking-clearing edits are invalid once thinking is off
        edits = [e for e in cm["edits"] if "thinking" not in str(e.get("type", ""))]
        if edits: out["context_management"] = {**cm, "edits": edits}
        else: out.pop("context_management", None)
    msgs = []
    for m in out.get("messages") or []:  # drop any thinking blocks already in history
        c = m.get("content")
        if isinstance(c, list):
            c = [b for b in c if not (isinstance(b, dict) and b.get("type") in ("thinking", "redacted_thinking"))]
            m = {**m, "content": c}
        msgs.append(m)
    if "messages" in out: out["messages"] = msgs
    return out

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
    def __init__(self, budget, log_path, thinking=None):
        self.budget = budget; self.log_path = log_path; self.thinking = thinking
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

REQ_KEYS = ("model", "max_tokens", "temperature", "top_p", "top_k", "thinking", "output_config", "reasoning_effort", "stream")

def _req_params(req):
    """The sampling/reasoning settings a harness actually sent (no message content, no headers/keys)."""
    out = {k: req[k] for k in REQ_KEYS if k in req}
    if req.get("__normalized"):
        out["normalized"] = "thinking=disabled, effort dropped"
    if req.get("__beta"):
        out["anthropic_beta"] = req["__beta"]
    extra = sorted(k for k in req if k not in REQ_KEYS + ("messages", "tools", "system", "metadata", "tool_choice", "__beta", "__normalized"))
    if extra:
        out["other_keys"] = extra
    return out

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
            if is_msg and self.headers.get("anthropic-beta"):  # logged only; the forwarded body is the raw bytes
                req["__beta"] = self.headers.get("anthropic-beta")
            if is_msg:
                if req.get("model") and not str(req["model"]).startswith(MODEL):
                    return self._err(400, f"proxy: only {MODEL} is allowed, got {req.get('model')}")
                if spent() >= HARD_CAP_USD:
                    return self._err(429, "proxy: global hard cap reached")
                if rec.usd >= rec.budget:
                    rec.refused += 1
                    return self._err(429, f"proxy: task budget ${rec.budget:.2f} spent")
            if is_msg and req:
                fwd = normalize(req, rec.thinking)
                if fwd is not None:
                    fwd.pop("__beta", None)
                    body = json.dumps(fwd).encode()
                    req["__normalized"] = True
            hdrs = {k: v for k, v in self.headers.items()
                    if k.lower() not in ("host", "content-length", "accept-encoding", "connection")}
            t0 = time.time()
            with httpx.Client(timeout=httpx.Timeout(600, connect=15, read=120)) as c:
                with c.stream(method, UPSTREAM + self.path, headers=hdrs, content=body) as r:
                    # Hard per-call deadline: an upstream stream that stays open (pings / trickle) never trips the
                    # 120 s read timeout and hung SWE-agent 10+ min twice (django-10554). Longest healthy call seen
                    # is ~64 s, so closing at CALL_DEADLINE_S only ever drops a stuck call; the client sees a broken
                    # connection and retries. Nothing is recorded for the dropped call (usage never arrived).
                    wd = threading.Timer(CALL_DEADLINE_S, r.close); wd.daemon = True; wd.start()
                    self.send_response(r.status_code)
                    for k, v in r.headers.items():
                        if k.lower() not in ("content-length", "transfer-encoding", "connection", "content-encoding"):
                            self.send_header(k, v)
                    self.send_header("Transfer-Encoding", "chunked"); self.end_headers()
                    buf = []
                    for chunk in r.iter_bytes():
                        buf.append(chunk)
                        self.wfile.write(f"{len(chunk):X}\r\n".encode() + chunk + b"\r\n"); self.wfile.flush()
                    wd.cancel()
                    if time.time() - t0 > CALL_DEADLINE_S:
                        raise TimeoutError(f"proxy: upstream call exceeded {CALL_DEADLINE_S}s deadline")
                    status = r.status_code
            # Record the call BEFORE sending the final chunk. The client returns as soon as it sees the
            # terminator, so recording after it races: a caller reading rec.calls right away (preflight, or
            # run.py after a harness's last call) could miss this call and under-count cost.
            try:
                if is_msg:
                    self._record(req, status, buf, t0)
            finally:
                self.wfile.write(b"0\r\n\r\n"); self.wfile.flush()

        def _record(self, req, status, buf, t0):
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
            n_think = text.count('"type":"thinking"') + text.count('"type": "thinking"') \
                + text.count('"type":"redacted_thinking"') + text.count('"type": "redacted_thinking"')
            usd = cost(u)
            _charge(usd)
            rec.add(dict(t=round(t0, 3), s=round(time.time() - t0, 2), usd=round(usd, 6),
                         prompt=u["input"] + u["cache_read"] + u["cache_write"], **u,
                         n_messages=len(req.get("messages") or []), n_tools=len(req.get("tools") or []),
                         req=_req_params(req), think_blocks=n_think))

        def do_POST(self): self._fwd("POST")
        def do_GET(self): self._fwd("GET")
    return H

class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

def start(budget, log_path, host="127.0.0.1", thinking=None):
    """Start a proxy for one task. Returns (server, recorder, base_url). thinking="disabled" normalizes (see normalize)."""
    rec = Recorder(budget, log_path, thinking)
    srv = _Server((host, 0), _handler(rec))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, rec, f"http://{host}:{srv.server_address[1]}"
