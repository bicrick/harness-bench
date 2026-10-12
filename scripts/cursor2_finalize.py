"""Read Cursor's own /context breakdown for every cursor_nothink2 run, then summarize.

For each runs/<task>/cursor_nothink2/home (saved with SBR_KEEP_CURSOR_HOME=1), copy the HOME to a temp dir, move the
chat store to the md5 of a local stand-in workspace (Cursor keys chats by md5(cwd)), resume the chat in the
interactive CLI under tmux, type /context and parse the category breakdown. Writes
results/swebench/cursor_nothink2_context.jsonl and prints medians. Usage:
  python3 scripts/cursor2_finalize.py [--jobs 4] [--only TASK] [--summary-only]
Needs CURSOR_API_KEY (source ~/sbr-env.sh). Resuming and opening /context does not send a model request.
"""
import argparse, concurrent.futures as cf, hashlib, json, os, re, shutil, statistics as st, subprocess, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; RUNS = ROOT / "results/swebench/runs"; H = "cursor_nothink2"
OUT = ROOT / "results/swebench/cursor_nothink2_context.jsonl"
AGENT = os.environ.get("SBR_CURSOR_AGENT", "/home/box/sbr-tools/cursor/bin/agent")
MODEL = os.environ.get("SBR_CURSOR_NOTHINK_MODEL", "claude-haiku-5-5-high")
CATS = ["System prompt", "Tool definitions", "Rules", "Skills", "MCP", "Subagents", "Conversation", "Free space"]

def num(s):
    s = s.strip().upper(); m = 1000 if s.endswith("K") else 1_000_000 if s.endswith("M") else 1
    return round(float(s.rstrip("KM")) * m)

def parse(txt):
    out = {}
    for c in CATS:
        m = re.search(re.escape(c) + r"\s+([\d.]+[KM]?)\s*•", txt)
        if m: out[c] = num(m.group(1))
    m = re.search(r"([\d.]+[KM]?)\s*/\s*([\d.]+[KM]?)\s+[\d.]+%", txt)
    if m: out["used"], out["max"] = num(m.group(1)), num(m.group(2))
    return out

def stream_facts(p):
    """Model turns from the full stream-json: a new turn starts at the first assistant/tool event after a tool result."""
    turns, after_result, usage, tools = 0, True, None, 0
    for line in p.read_text(errors="ignore").splitlines():
        try: e = json.loads(line)
        except Exception: continue
        t, sub = e.get("type"), e.get("subtype")
        if t == "assistant" or (t == "tool_call" and sub == "started"):
            if after_result: turns += 1; after_result = False
            if t == "tool_call": tools += 1
        elif t == "tool_call" and sub == "completed": after_result = True
        elif t == "result": usage = e.get("usage")
    return turns, usage, tools

def context_for(task):
    d = RUNS / task / H; home = d / "home"
    sid = next((p.name for p in (home / ".cursor/chats").glob("*/*")), None)
    if not sid: return {"task": task, "error": "no chat store"}
    tmp = Path(tempfile.mkdtemp(prefix="c2fin-")); h = tmp / "h"; ws = tmp / "testbed"; ws.mkdir()
    shutil.copytree(home, h, symlinks=True)
    chats = h / ".cursor/chats"; src = next(chats.glob(f"*/{sid}")).parent
    dst = chats / hashlib.md5(str(ws).encode()).hexdigest()
    if src != dst: src.rename(dst)
    env = f"env HOME={h} CURSOR_CONFIG_DIR={h}/.cursor XDG_CONFIG_HOME={h}/.config XDG_CACHE_HOME={h}/.cache XDG_DATA_HOME={h}/.local/share NO_OPEN_BROWSER=1"
    s = "c2fin_" + hashlib.md5(task.encode()).hexdigest()[:8]
    subprocess.run(["tmux", "kill-session", "-t", s], capture_output=True)
    subprocess.run(["tmux", "new-session", "-d", "-s", s, "-x", "170", "-y", "50",
                    f"{env} bash -c 'cd {ws} && {AGENT} --trust --resume {sid} --model {MODEL}'"], check=True)
    txt = ""
    try:
        time.sleep(12)
        for _ in range(3):
            subprocess.run(["tmux", "send-keys", "-t", s, "/context"]); time.sleep(2)
            subprocess.run(["tmux", "send-keys", "-t", s, "Enter"]); time.sleep(8)
            txt = subprocess.run(["tmux", "capture-pane", "-p", "-t", s], capture_output=True, text=True).stdout
            if "Current context usage" in txt: break
            subprocess.run(["tmux", "send-keys", "-t", s, "Escape"]); time.sleep(3)
    finally:
        subprocess.run(["tmux", "kill-session", "-t", s], capture_output=True); shutil.rmtree(tmp, ignore_errors=True)
    (d / "context.txt").write_text(txt)
    ctx = parse(txt)
    if "used" not in ctx: return {"task": task, "error": "no /context panel", "session": sid}
    return {"task": task, "session": sid, "context": ctx}

def summarize():
    rows = {json.loads(l)["task"]: json.loads(l) for l in OUT.read_text().splitlines()} if OUT.exists() else {}
    res = [json.loads(l) for l in (ROOT / "results/swebench/results.jsonl").read_text().splitlines() if f'"{H}"' in l]
    last = {}
    for r in res:
        if not r.get("error"): last[r["instance_id"]] = r
    per = []
    for task, r in sorted(last.items()):
        turns, usage, tools = stream_facts(RUNS / task / H / "stdout.txt")
        c = rows.get(task, {}).get("context") or {}
        fixed = sum(c.get(k, 0) for k in CATS[:6]) if c else None
        prompt_tok = round(len((RUNS / task / H / "prompt.txt").read_text()) / 4)  # rough: ~4 chars per token
        total_in = sum((usage or {}).get(k, 0) for k in ("inputTokens", "cacheReadTokens", "cacheWriteTokens"))
        opening = fixed + prompt_tok if fixed is not None else None
        per.append(dict(task=task, resolved=r.get("resolved"), wall_s=r.get("wall_s"), turns=turns, tool_calls=tools,
                        usage=usage, total_in=total_in, out=(usage or {}).get("outputTokens", 0), fixed=fixed, opening=opening,
                        final=c.get("used"), conversation=c.get("Conversation"),
                        resent=round(100 * opening * turns / total_in) if opening and total_in else None, ctx=c))
    med = lambda k: st.median([p[k] for p in per if p[k] is not None]) if any(p[k] is not None for p in per) else None
    solved = sum(1 for p in per if p["resolved"])
    # Cost estimate from Cursor's own usage at the proxy's <=100k Haiku 5.5 rates ($/M): input .10, cache write .125,
    # cache read .01, output .50 (same tier table as sbr/proxy.py).
    usd = sum(((p["usage"] or {}).get("inputTokens", 0) * .10 + (p["usage"] or {}).get("cacheWriteTokens", 0) * .125 +
               (p["usage"] or {}).get("cacheReadTokens", 0) * .01 + p["out"] * .50) / 1e6 for p in per)
    tok = sum(p["total_in"] + p["out"] for p in per); mins = sum(p["wall_s"] or 0 for p in per) / 60
    cats = {k: st.median([p["ctx"][k] for p in per if k in p["ctx"]]) for k in CATS[:7] if any(k in p["ctx"] for p in per)}
    s = dict(n=len(per), solved=solved, with_context=sum(1 for p in per if p["final"]), median_opening=med("opening"),
             median_fixed=med("fixed"), median_final=med("final"), median_conversation=med("conversation"),
             median_turns=med("turns"), median_tool_calls=med("tool_calls"), median_total_in=med("total_in"),
             median_resent_pct=med("resent"), median_categories=cats,
             usd_per_fix=usd / solved if solved else None, tok_per_fix=tok / solved if solved else None,
             min_per_fix=mins / solved if solved else None, usd_total=usd)
    (ROOT / "results/swebench/cursor_nothink2_summary.json").write_text(json.dumps(dict(summary=s, runs=per), indent=1))
    print(json.dumps(s, indent=1))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--jobs", type=int, default=4); ap.add_argument("--only")
    ap.add_argument("--summary-only", action="store_true"); a = ap.parse_args()
    if not a.summary_only:
        have = {json.loads(l)["task"] for l in OUT.read_text().splitlines() if "context" in json.loads(l)} if OUT.exists() else set()
        tasks = [a.only] if a.only else sorted(p.parent.parent.name for p in RUNS.glob(f"*/{H}/home") if p.parent.parent.name not in have)
        with cf.ThreadPoolExecutor(a.jobs) as ex:
            for row in ex.map(context_for, tasks):
                print(row.get("task"), row.get("error") or row["context"].get("used"), flush=True)
                with open(OUT, "a") as f: f.write(json.dumps(row) + "\n")
    summarize()
