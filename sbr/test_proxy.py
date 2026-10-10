"""Proxy tests against a fake upstream; no API key or network needed.  pytest sbr/test_proxy.py"""
import http.server, json, threading
import httpx
import pytest
from sbr import proxy

USAGE = {"input_tokens": 13, "output_tokens": 4, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}

class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get("content-length") or 0))
        if "stream" in self.path:
            events = [{"type": "message_start", "message": {"usage": USAGE}},
                      {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 4}}]
            body = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()
            ctype = "text/event-stream"
        else:
            body = json.dumps({"model": proxy.MODEL, "content": [{"type": "text", "text": "ok"}],
                               "stop_reason": "end_turn", "usage": USAGE}).encode()
            ctype = "application/json"
        self.send_response(200); self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body))); self.end_headers(); self.wfile.write(body)

@pytest.fixture
def upstream(monkeypatch, tmp_path):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(proxy, "UPSTREAM", f"http://127.0.0.1:{srv.server_address[1]}")
    monkeypatch.setattr(proxy, "LEDGER", tmp_path / "ledger.json")
    yield tmp_path
    srv.shutdown()

def _call(url, path="/v1/messages", model=None):
    return httpx.post(url + path, json={"model": model or proxy.MODEL, "messages": [{"role": "user", "content": "hi"}]})

@pytest.mark.parametrize("path", ["/v1/messages", "/v1/messages?stream"])
def test_call_is_recorded_before_the_response_ends(upstream, path):
    srv, rec, url = proxy.start(1.0, upstream / "calls.jsonl")
    try:
        for i in range(20):  # the race showed up intermittently; check many times with no wait
            r = _call(url, path)
            assert r.status_code == 200
            assert len(rec.calls) == i + 1, "call not recorded when the client got its response"
        assert rec.calls[0]["prompt"] == 13 and rec.calls[0]["output"] == 4
    finally:
        srv.shutdown()

def test_task_budget_refuses_after_spend(upstream):
    srv, rec, url = proxy.start(1e-9, upstream / "calls.jsonl")
    try:
        assert _call(url).status_code == 200      # first call goes through and spends the budget
        r = _call(url)
        assert r.status_code == 429 and rec.refused == 1
    finally:
        srv.shutdown()

def test_other_models_are_refused(upstream):
    srv, rec, url = proxy.start(1.0, upstream / "calls.jsonl")
    try:
        assert _call(url, model="claude-opus-5-5").status_code == 400
        assert not rec.calls
    finally:
        srv.shutdown()
