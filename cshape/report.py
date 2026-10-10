"""Rebuild results/summary.csv and figures/*.png from all raw results/*.jsonl logs.
Usage: python -m cshape.report   (or: make figures)"""
import csv, glob, json, math
from collections import defaultdict
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
RES, FIG = ROOT / "results", ROOT / "figures"

def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0, c - h), min(1, c + h))

def load(pattern="*.jsonl"):
    rows = []
    for f in sorted(RES.glob(pattern)):
        if f.name.startswith("archive_"):
            continue
        for line in f.open():
            r = json.loads(line); r["_file"] = f.stem; rows.append(r)
    return rows

def summarize(rows):
    g = defaultdict(list)
    for r in rows:
        g[(r["_file"], r["strategy"])].append(r)
    out = []
    for (src, strat), rs in sorted(g.items()):
        n = len(rs); k = sum(bool(r.get("passed")) for r in rs)
        cost = sum(r.get("cost_usd", 0) for r in rs)
        tok = lambda key: sum(r.get("tokens", {}).get(key, 0) for r in rs) / n
        lo, hi = wilson(k, n)
        out.append(dict(source=src, strategy=strat, n=n, passed=k, pass_rate=round(k / n, 3), ci_lo=round(lo, 3), ci_hi=round(hi, 3),
                        mean_missed_callers=round(sum(r.get("missed_callers") or 0 for r in rs) / n, 2),
                        mean_diff_lines=round(sum((r.get("diff", {}).get("added", 0) + r.get("diff", {}).get("removed", 0)) for r in rs) / n, 1),
                        mean_input=round(tok("input")), mean_cache_read=round(tok("cache_read")), mean_cache_write=round(tok("cache_write")),
                        mean_output=round(tok("output")), total_cost_usd=round(cost, 4),
                        cost_per_solve_usd=round(cost / k, 4) if k else None,
                        mean_wall_s=round(sum(r.get("wall_s", 0) for r in rs) / n, 1),
                        mean_tool_calls=round(sum(r.get("notes", {}).get("tool_calls", 0) for r in rs) / n, 1),
                        errors=sum(1 for r in rs if r.get("error"))))
    return out

def main():
    rows = load(); FIG.mkdir(exist_ok=True)
    summ = summarize(rows)
    with open(RES / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summ[0].keys())); w.writeheader(); w.writerows(summ)
    for src in sorted({s["source"] for s in summ}):
        ss = [s for s in summ if s["source"] == src]
        x = range(len(ss))
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.bar(x, [s["pass_rate"] for s in ss], yerr=[[s["pass_rate"] - s["ci_lo"] for s in ss], [s["ci_hi"] - s["pass_rate"] for s in ss]], capsize=3)
        ax.set_xticks(list(x)); ax.set_xticklabels([s["strategy"] for s in ss], rotation=30, ha="right")
        ax.set_ylim(0, 1); ax.set_ylabel("pass rate (95% Wilson CI)"); ax.set_title(f"{src}: pass rate by strategy (Haiku 5.5)")
        fig.tight_layout(); fig.savefig(FIG / f"{src}_pass_rate.png", dpi=150); plt.close(fig)
        fig, ax = plt.subplots(figsize=(6, 4.5))
        for s in ss:
            if s["cost_per_solve_usd"]:
                ax.scatter(s["cost_per_solve_usd"], s["pass_rate"]); ax.annotate(s["strategy"], (s["cost_per_solve_usd"], s["pass_rate"]), fontsize=8)
        ax.set_xscale("log"); ax.set_xlabel("cost per solved task (USD, log)"); ax.set_ylabel("pass rate")
        ax.set_title(f"{src}: pass rate vs cost per solve"); fig.tight_layout(); fig.savefig(FIG / f"{src}_pass_vs_cost.png", dpi=150); plt.close(fig)
    print(f"{len(rows)} runs -> results/summary.csv, figures/*.png")
    for s in summ:
        print(f"{s['source']:<12} {s['strategy']:<16} n={s['n']:<3} pass={s['pass_rate']:.2f} [{s['ci_lo']:.2f},{s['ci_hi']:.2f}] missed={s['mean_missed_callers']} $/solve={s['cost_per_solve_usd']}")

if __name__ == "__main__":
    main()
