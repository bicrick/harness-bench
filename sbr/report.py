"""Summary of the comparison, from results.jsonl and the per-call proxy logs.

For each harness: resolve rate with a 95% interval, cost, model calls, and how it handled the context
window, all measured the same way for every harness:
  peak_prompt   largest prompt any call sent (the biggest the window got)
  compactions   calls where the prompt shrank by 30% or more from the previous call
  cache_hit     share of prompt tokens served from the prompt cache

  python -m sbr.report     -> prints a table, writes OUT/summary.csv and OUT/summary.md
"""
import csv, json, math, statistics as st
from collections import defaultdict
from .config import OUT

def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))

def calls_for(iid, harness):
    p = OUT / "runs" / iid / harness / "calls.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []

def window_stats(calls):
    prompts = [c["prompt"] for c in sorted(calls, key=lambda c: c["t"])]
    comp = sum(1 for a, b in zip(prompts, prompts[1:]) if a and b < 0.7 * a)
    tot = sum(prompts); cached = sum(c["cache_read"] for c in calls)
    return dict(compactions=comp, cache_hit=(cached / tot) if tot else 0.0)

def _skip_ids():
    p = OUT / "skip_instances.json"
    return set(json.loads(p.read_text()).get("instances") or []) if p.exists() else set()

def load():
    skip = _skip_ids()
    rows = {}
    for l in (OUT / "results.jsonl").read_text().splitlines():
        r = json.loads(l)
        if r["harness"] == "gold":
            continue
        if r["instance_id"] in skip or r.get("excluded") or r.get("notes") == "excluded: infra (httpbin unreachable)":
            continue  # infra-broken tasks stay out of scoring for every harness
        k = (r["instance_id"], r["harness"])
        good = not r.get("error") and r.get("resolved") is not None
        prev_good = k in rows and not rows[k].get("error") and rows[k].get("resolved") is not None
        if good or not prev_good:
            rows[k] = r  # keep the latest good row per pair (reruns replace earlier rows)
    return list(rows.values())

def summarize(rows):
    by = defaultdict(list)
    for r in rows:
        if not r.get("error") and r.get("resolved") is not None:
            by[r["harness"]].append(r)
    out = []
    for h, rs in by.items():
        n = len(rs); k = sum(bool(r["resolved"]) for r in rs)
        lo, hi = wilson(k, n)
        ws = [window_stats(calls_for(r["instance_id"], h)) for r in rs]
        usd = [r["usd"] for r in rs]
        out.append(dict(
            harness=h, n=n, resolved=k, rate=k / n, ci_lo=lo, ci_hi=hi,
            usd_total=sum(usd), usd_median=st.median(usd), usd_per_resolve=(sum(usd) / k) if k else None,
            calls_median=st.median(r["calls"] for r in rs),
            peak_prompt_median=st.median(r["peak_prompt"] for r in rs),
            compactions_mean=st.mean(w["compactions"] for w in ws),
            cache_hit=st.mean(w["cache_hit"] for w in ws),
            budget_hit=sum(r.get("budget_refusals", 0) > 0 for r in rs),
            timeouts=sum(bool((r.get("notes") or {}).get("timeout")) for r in rs),
            cost_source=rs[0].get("cost_source", "proxy")))
    return sorted(out, key=lambda r: -r["rate"])

def main():
    rows = summarize(load())
    if not rows:
        print("no graded results yet"); return
    cols = ["harness", "n", "resolved", "rate", "ci_lo", "ci_hi", "usd_total", "usd_median", "usd_per_resolve",
            "calls_median", "peak_prompt_median", "compactions_mean", "cache_hit", "budget_hit", "timeouts", "cost_source"]
    with open(OUT / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    lines = ["| harness | resolved | 95% CI | $/resolve | median calls | median peak window | compactions/run | cache hit |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        cpr = f"${r['usd_per_resolve']:.4f}" if r["usd_per_resolve"] else "—"
        if r["cost_source"] != "proxy":
            cpr += " *"
        lines.append(f"| {r['harness']} | {r['resolved']}/{r['n']} ({r['rate']:.0%}) | {r['ci_lo']:.0%}–{r['ci_hi']:.0%} | {cpr} | "
                     f"{r['calls_median']:.0f} | {r['peak_prompt_median']:,.0f} | {r['compactions_mean']:.1f} | {r['cache_hit']:.0%} |")
    if any(r["cost_source"] != "proxy" for r in rows):
        lines.append("\n\\* not measured by our proxy (Cursor bills through its own servers); see its own usage numbers.")
    md = "\n".join(lines)
    (OUT / "summary.md").write_text(md + "\n")
    print(md)

if __name__ == "__main__":
    main()
