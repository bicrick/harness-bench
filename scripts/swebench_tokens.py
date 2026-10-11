"""Summarize SWE-bench pilot results with token totals derived from per-call proxy logs.
Reads results/swebench/results.jsonl (latest row per instance+harness) and runs/<iid>/<harness>/calls.jsonl.
Writes results/swebench/summary_tokens.csv (per run) and prints a per-harness table."""
import json, csv, pathlib, collections
R = pathlib.Path(__file__).resolve().parent.parent / "results/swebench"
_skip = set()
if (R / "skip_instances.json").exists():
    _skip = set(json.loads((R / "skip_instances.json").read_text()).get("instances") or [])
rows = {}
for l in (R / "results.jsonl").read_text().splitlines():
    if l.strip():
        d = json.loads(l)
        if d["instance_id"] in _skip or d.get("excluded") or d.get("notes") == "excluded: infra (httpbin unreachable)":
            continue
        rows[(d["instance_id"], d["harness"])] = d
K = ["input", "output", "cache_read", "cache_write"]
LE100K = dict(input=0.10, cache_write=0.125, cache_read=0.01, output=0.50)  # Haiku 5.5 USD/M, lower tier (cursor estimate only)
USD_COL = "usd_est"
out = []
for (iid, h), d in rows.items():
    t = dict.fromkeys(K, 0); f = R / "runs" / iid / h / "calls.jsonl"
    if f.exists():
        for l in f.read_text().splitlines():
            if l.strip():
                c = json.loads(l)
                for k in K: t[k] += c.get(k, 0) or 0
    s = R / "runs" / iid / h / "stdout.txt"
    if not f.exists() and s.exists():  # cursor bypasses the proxy; its stream-json result carries run-level usage
        u = None
        for l in s.read_text(errors="ignore").splitlines():
            if '"usage"' in l:
                try: u = json.loads(l).get("usage") or u
                except Exception: pass
        if u:
            t = {"input": u.get("inputTokens", 0), "output": u.get("outputTokens", 0),
                 "cache_read": u.get("cacheReadTokens", 0), "cache_write": u.get("cacheWriteTokens", 0)}
    tot = sum(t.values())
    out.append({"instance_id": iid, "harness": h, "resolved": bool(d.get("resolved")), "usd": d.get("usd", 0),
                "calls": d.get("calls", 0), **t, "usd_est": (d.get("usd") or 0) or round(sum(t[k] * LE100K[k] for k in K) / 1e6, 6), "total_tokens": tot, "peak_prompt": d.get("peak_prompt"), "wall_s": d.get("wall_s"), "concurrency_regime": d.get("concurrency_regime") or "unconstrained"})
with open(R / "summary_tokens.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
agg = collections.defaultdict(list)
for r in out: agg[r["harness"]].append(r)
print(f"{'harness':16}{'runs':>5}{'solved':>7}{'tok/task':>11}{'tok/solve':>11}{'$/solve':>9}")
for h, rs in sorted(agg.items()):
    s = sum(r["resolved"] for r in rs); T = sum(r["total_tokens"] for r in rs); U = sum(r["usd_est"] for r in rs)
    print(f"{h:16}{len(rs):>5}{s:>7}{T//len(rs):>11,}{(T//s if s else 0):>11,}{(U/s if s else 0):>9.3f}")
