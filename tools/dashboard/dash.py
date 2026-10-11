import json, os, time, pathlib, shutil, statistics, threading, html, collections
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

R = pathlib.Path(os.environ.get("SBR_RESULTS", str(pathlib.Path.home() / "context-shaping/results/swebench")))
_token_env = os.environ.get("SBR_DASH_TOKEN", "").strip()
_token_file = pathlib.Path(os.environ.get("SBR_DASH_TOKEN_FILE", str(pathlib.Path(__file__).parent / "token")))
TOKEN = _token_env or (_token_file.read_text().strip() if _token_file.exists() else "")
if not TOKEN:
    raise SystemExit("SBR_DASH_TOKEN or token file required")

K = ["input", "output", "cache_read", "cache_write"]
CAP = float(os.environ.get("SBR_HARD_CAP", "45"))

# Same-settings (thinking off) lead set
SS = [
    "cursor_nothink",
    "mini_swe_agent_nothink",
    "swe_agent_nothink",
    "opencode_nothink",
    "aider_nothink",
    "claude_code_nothink",
]
LABEL = {
    "cursor_nothink": "Cursor",
    "mini_swe_agent_nothink": "mini-swe-agent",
    "swe_agent_nothink": "SWE-agent",
    "opencode_nothink": "OpenCode",
    "aider_nothink": "Aider",
    "claude_code_nothink": "Claude Code",
    "cursor": "Cursor (thinking)",
    "mini_swe_agent": "mini-swe-agent",
    "swe_agent": "SWE-agent",
    "opencode": "OpenCode",
    "opencode_auto": "OpenCode (auto)",
    "aider": "Aider",
    "claude_code": "Claude Code",
}
# Earlier runs (thinking on / default)
EARLIER = ["cursor", "opencode_auto", "opencode", "claude_code", "mini_swe_agent", "aider", "swe_agent"]

tokcache = {}


def toks(iid, h):
    d = R / "runs" / iid / h
    f = d / "calls.jsonl"
    s = d / "stdout.txt"
    src = f if f.exists() else s
    if not src.exists():
        return 0
    m = src.stat().st_mtime
    if tokcache.get((iid, h), (None,))[0] == m:
        return tokcache[(iid, h)][1]
    t = 0
    if src is f:
        for l in f.read_text(errors="ignore").splitlines():
            try:
                c = json.loads(l)
                t += sum(c.get(k, 0) or 0 for k in K)
            except Exception:
                pass
    else:
        u = None
        for l in s.read_text(errors="ignore").splitlines():
            if '"usage"' in l:
                try:
                    u = json.loads(l).get("usage") or u
                except Exception:
                    pass
        if u:
            t = sum(u.get(k, 0) or 0 for k in ("inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens"))
    tokcache[(iid, h)] = (m, t)
    return t


def mem_disk():
    mi = {l.split(":")[0]: int(l.split()[1]) for l in open("/proc/meminfo")}
    return mi["MemAvailable"] / 1048576, mi["MemTotal"] / 1048576, shutil.disk_usage("/").free / 1e9


def load_rows(tasks):
    rows = {}
    p = R / "results.jsonl"
    if not p.exists():
        return rows
    for l in p.read_text().splitlines():
        try:
            d = json.loads(l)
        except Exception:
            continue
        if d.get("harness") != "gold" and d.get("instance_id") in tasks:
            rows[(d["instance_id"], d["harness"])] = d
    return rows


def harness_stats(h, tasks, rows):
    rs = [(i, rows[(i, h)]) for i in tasks if (i, h) in rows]
    n = len(rs)
    s = sum(bool(r.get("resolved")) for _, r in rs)
    usd = sum(r.get("usd") or 0 for _, r in rs)
    T = sum(toks(i, h) for i, _ in rs)
    w = [r["wall_s"] for _, r in rs if r.get("wall_s")]
    return {
        "h": h,
        "n": n,
        "s": s,
        "usd": usd,
        "T": T,
        "mw": statistics.median(w) if w else 0,
        "pass": (s / n * 100) if n else 0,
        "usd_solve": (usd / s) if s else 0,
        "tok_solve": (T // s) if s else 0,
    }


def detect_running(tasks, harnesses, rows, now):
    running = []
    runset = set()
    for iid in tasks:
        for h in harnesses:
            d = R / "runs" / iid / h
            if not d.exists():
                continue
            try:
                mt = max((p.stat().st_mtime for p in d.iterdir()), default=d.stat().st_mtime)
            except Exception:
                continue
            r = rows.get((iid, h))
            if (d / "grade").exists() and r:
                continue
            if now - mt < 1800 and not (r and (d / "grade").exists()):
                st = min((p.stat().st_mtime for p in d.iterdir()), default=mt)
                if r is None or (st > now - 1800 and not (d / "patch.diff").exists()):
                    running.append((h, iid, now - st))
                    runset.add((iid, h))
    return running, runset


def grade_mtimes(tasks, harnesses):
    mts = []
    for iid in tasks:
        for h in harnesses:
            g = R / "runs" / iid / h / "grade"
            if g.exists():
                try:
                    mts.append(g.stat().st_mtime)
                except Exception:
                    pass
            else:
                # also count results rows that finished recently via patch+row without grade dir walk
                pass
    return sorted(mts)


def eta_text(tasks, harnesses, rows, now):
    """Overall ETA from recent completion rate of same-settings set."""
    done = sum(1 for h in harnesses for i in tasks if (i, h) in rows)
    total = len(tasks) * len(harnesses)
    remaining = total - done
    if remaining <= 0:
        return "complete", done, total, 0

    # Prefer grade mtimes; fall back to results.jsonl wall timestamps if present
    mts = grade_mtimes(tasks, harnesses)
    # Also use results.jsonl file isn't per-row ts; use run dir grade or patch.diff mtime
    if len(mts) < 3:
        for iid in tasks:
            for h in harnesses:
                for name in ("grade", "patch.diff", "result.json"):
                    p = R / "runs" / iid / h / name
                    if p.exists():
                        try:
                            mts.append(p.stat().st_mtime)
                        except Exception:
                            pass
        mts = sorted(mts)

    window = 3600  # last hour
    recent = [m for m in mts if now - m < window]
    rate_per_s = 0.0
    if len(recent) >= 2:
        span = max(60.0, now - recent[0])
        rate_per_s = len(recent) / span
    elif len(mts) >= 2:
        span = max(60.0, mts[-1] - mts[0])
        rate_per_s = len(mts) / span

    if rate_per_s <= 0:
        return "estimating…", done, total, remaining

    secs = remaining / rate_per_s
    eta_dt = datetime.now(ZoneInfo("America/Chicago")) + timedelta(seconds=secs)
    if secs < 3600:
        human = f"~{secs/60:.0f}m"
    else:
        human = f"~{secs/3600:.1f}h"
    return f"{human} · ~{eta_dt.strftime('%I:%M %p CT')}", done, total, remaining


PAGE = "<p>loading…</p>"


def build():
    global PAGE
    now = time.time()
    tasks = [i["instance_id"] for i in json.load(open(R / "subset.json"))["instances"]]
    rows = load_rows(tasks)
    try:
        spend = json.load(open(R / "ledger.json"))["total_usd"]
    except Exception:
        spend = 0
    try:
        rq = len(json.load(open(R / "rerun_queue.json")).get("pairs", []))
    except Exception:
        rq = 0

    ss_stats = [harness_stats(h, tasks, rows) for h in SS]
    earlier_present = [h for h in EARLIER if any((i, h) in rows for i in tasks)]
    earlier_stats = [harness_stats(h, tasks, rows) for h in earlier_present]

    running, runset = detect_running(tasks, SS, rows, now)
    eta, done_all, total_all, rem = eta_text(tasks, SS, rows, now)

    ma, mt_, df = mem_disk()
    ct = datetime.now(ZoneInfo("America/Chicago")).strftime("%b %d %I:%M:%S %p CT")
    e = html.escape

    o = []
    o.append(f"<h1>SWE-bench · same settings (thinking off)</h1>")
    o.append(f"<p class=m>Updated {ct} · auto-refresh 30s · Haiku 5.5 · 50 tasks</p>")

    pct = min(100, spend / CAP * 100)
    o.append(
        f"<p><b>Spend ${spend:.2f}</b> of ${CAP:.0f} "
        f"<span class=m>(Cursor bills separately, not included)</span></p>"
        f"<div class=bar><div style='width:{pct:.1f}%'></div></div>"
    )
    overall_pct = (done_all / total_all * 100) if total_all else 0
    o.append(
        f"<p><b>Same-settings progress</b> {done_all}/{total_all} "
        f"({overall_pct:.0f}%) · remaining {rem} · ETA {e(eta)}</p>"
        f"<div class=bar><div class=b2 style='width:{overall_pct:.1f}%'></div></div>"
    )
    o.append(f"<p class=m>RAM free {ma:.1f}/{mt_:.0f} GB · disk free {df:.0f} GB · rerun queue {rq}</p>")

    # Lead table
    o.append(
        "<div class=sc><table>"
        "<tr><th>harness</th><th>done</th><th>solved</th><th>pass</th>"
        "<th>$/solve</th><th>tok/solve</th><th>med wall</th><th>progress</th></tr>"
    )
    for st in ss_stats:
        label = LABEL.get(st["h"], st["h"])
        pbar = st["n"] / 50 * 100
        o.append(
            f"<tr><td>{e(label)}</td>"
            f"<td>{st['n']}/50</td>"
            f"<td>{st['s']}</td>"
            f"<td>{st['pass']:.0f}%</td>"
            f"<td>{st['usd_solve']:.3f}</td>"
            f"<td>{st['tok_solve']:,}</td>"
            f"<td>{st['mw']/60:.1f}m</td>"
            f"<td class=pb><div class=pbar><div style='width:{pbar:.1f}%'></div></div>"
            f"<span class=m>{st['n']}/50</span></td></tr>"
        )
    o.append("</table></div>")
    o.append("<p class=m>Cursor $ shows 0 (not proxied); its tokens come from its own logs. All six use thinking off.</p>")

    # Running
    o.append("<h2>Running now</h2>")
    if running:
        o.append(
            "<ul>"
            + "".join(
                f"<li>{e(LABEL.get(h,h))} · {e(i)} · {s/60:.0f}m</li>"
                for h, i, s in sorted(running, key=lambda x: -x[2])
            )
            + "</ul>"
        )
    else:
        o.append("<p class=m>nothing detected</p>")

    # Task grid — same-settings only
    o.append("<h2>Per-task grid (same settings)</h2>")
    o.append(
        "<div class=sc><table class=g><tr><th></th>"
        + "".join(f"<th>{e(LABEL.get(h,h)[:6])}</th>" for h in SS)
        + "</tr>"
    )
    for i in tasks:
        o.append(f"<tr><td class=t>{e(i.replace('__','/'))}</td>")
        for h in SS:
            if (i, h) in runset:
                c = "y"
            elif (i, h) in rows:
                c = "g" if rows[(i, h)].get("resolved") else "r"
            else:
                c = "n"
            o.append(f"<td class={c}></td>")
        o.append("</tr>")
    o.append("</table></div><p class=m>green solved · red unsolved · yellow running · grey pending</p>")

    # Collapsed earlier runs
    o.append("<details class=earlier><summary>Earlier runs (thinking on / default settings)</summary>")
    if earlier_stats:
        o.append(
            "<div class=sc><table>"
            "<tr><th>harness</th><th>done</th><th>solved</th><th>pass</th>"
            "<th>$</th><th>$/solve</th><th>tok/solve</th><th>med wall</th></tr>"
        )
        for st in earlier_stats:
            label = LABEL.get(st["h"], st["h"])
            o.append(
                f"<tr><td>{e(label)}</td>"
                f"<td>{st['n']}/50</td>"
                f"<td>{st['s']}</td>"
                f"<td>{st['pass']:.0f}%</td>"
                f"<td>{st['usd']:.2f}</td>"
                f"<td>{st['usd_solve']:.3f}</td>"
                f"<td>{st['tok_solve']:,}</td>"
                f"<td>{st['mw']/60:.1f}m</td></tr>"
            )
        o.append("</table></div>")
        o.append("<p class=m>These used default / thinking-on settings and are not comparable to the lead table.</p>")
    else:
        o.append("<p class=m>none</p>")
    o.append("</details>")

    PAGE = (
        """<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">"""
        """<meta http-equiv=refresh content=30><title>SWE-bench same settings</title><style>
body{font:14px system-ui,-apple-system,sans-serif;margin:12px;color:#222;max-width:960px}
h1{font-size:18px;margin:0}h2{font-size:15px;margin:16px 0 6px}
.m{color:#777;font-size:12px}
table{border-collapse:collapse;width:100%}
td,th{padding:4px 6px;border-bottom:1px solid #eee;text-align:right;white-space:nowrap}
td:first-child,th:first-child{text-align:left}
.sc{overflow-x:auto;-webkit-overflow-scrolling:touch}
.bar{background:#eee;height:8px;border-radius:4px;margin:4px 0 10px}
.bar div{background:#4a7;height:8px;border-radius:4px}
.bar .b2{background:#38a}
.pbar{background:#eee;height:6px;border-radius:3px;width:72px;display:inline-block;vertical-align:middle;margin-right:4px}
.pbar div{background:#38a;height:6px;border-radius:3px}
.pb{text-align:left!important}
.g td{width:16px;height:14px;padding:0;border:1px solid #fff}
.g th{font-size:10px;text-align:center}
.t{font-size:10px;padding-right:6px!important}
.g{font-size:10px}
.g .g{background:#3a6}.r{background:#d55}.n{background:#ddd}.y{background:#eb3}
.earlier{margin-top:18px;border:1px solid #eee;padding:8px 10px;border-radius:4px}
.earlier summary{cursor:pointer;font-weight:600;font-size:14px}
@media (max-width:600px){
  body{font-size:13px;margin:8px}
  h1{font-size:16px}
  td,th{padding:3px 4px}
  .pbar{width:48px}
}
</style>"""
        + "".join(o)
    )


def loop():
    while True:
        try:
            build()
        except Exception as ex:
            print("build error", ex, flush=True)
        time.sleep(20)


class Hd(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path != "/" + TOKEN:
            self.send_response(404)
            self.end_headers()
            return
        b = PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


threading.Thread(target=loop, daemon=True).start()
# prime one build before serving
try:
    build()
except Exception as ex:
    print("initial build error", ex, flush=True)
ThreadingHTTPServer(("127.0.0.1", 8787), Hd).serve_forever()
