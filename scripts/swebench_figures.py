"""Figures for the full SWE-bench Verified run (6 harnesses x 50-task subset, Haiku 5.5).
Reads results/swebench/summary_tokens.csv (run scripts/swebench_tokens.py first).
Usage: uv run --with matplotlib python3 scripts/swebench_figures.py  -> figures/swebench_*.png"""
import csv, math, pathlib, statistics
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
ROOT = pathlib.Path(__file__).resolve().parent.parent
R, FIG = ROOT / "results/swebench", ROOT / "figures"
rows = [r for r in csv.DictReader(open(R / "summary_tokens.csv")) if r["harness"] != "gold"]
by = {}
for r in rows: by.setdefault(r["harness"], []).append(r)
def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h
S = []
for h, rs in by.items():
    k = sum(r["resolved"] == "True" for r in rs); n = len(rs)
    U = sum(float(r["usd_est"]) for r in rs); T = sum(int(r["total_tokens"]) for r in rs)
    W = [float(r["wall_s"]) for r in rs if r["wall_s"] and r["concurrency_regime"] != "unconstrained"]
    S.append(dict(h=h, k=k, n=n, p=k / n, ci=wilson(k, n), usd_solve=U / k, tok_solve=T / k, wall=statistics.median(W) if W else float("nan")))
S.sort(key=lambda s: -s["p"])
C = "#d97757"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
# 1. pass rate with 95% CI
fig, ax = plt.subplots(figsize=(7, 3.6))
for i, s in enumerate(S):
    ax.barh(i, s["p"], color=C, alpha=.85); ax.plot(s["ci"], [i, i], color="#333", lw=1.2)
    ax.text(s["ci"][1] + .01, i, f'{s["k"]}/{s["n"]} ({s["p"]:.0%})', va="center", fontsize=9)
ax.set_yticks(range(len(S)), [s["h"] for s in S]); ax.invert_yaxis(); ax.set_xlim(0, 1.05)
ax.set_xlabel("resolved (SWE-bench Verified, 49 scored tasks), 95% Wilson CI")
ax.set_title("Same model (Haiku 5.5), six harnesses"); fig.tight_layout(); fig.savefig(FIG / "swebench_pass_rate.png", dpi=150); plt.close(fig)
# 2. cost per solve vs pass rate
fig, ax = plt.subplots(figsize=(6.5, 4))
for s in S:
    ax.scatter(s["usd_solve"], s["p"], color=C, s=50, zorder=3); ax.annotate(s["h"] + (" (est.)" if s["h"] == "cursor" else ""), (s["usd_solve"], s["p"]), xytext=(6, 4), textcoords="offset points", fontsize=9)
ax.set_xscale("log")
from matplotlib.ticker import FixedLocator, NullLocator, FuncFormatter
ax.xaxis.set_major_locator(FixedLocator([0.005, 0.01, 0.02, 0.05, 0.1])); ax.xaxis.set_minor_locator(NullLocator())
ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:g}")); ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))
ax.set_xlabel("$ per resolved task (log scale)"); ax.set_ylabel("pass rate")
ax.set_title("Cost vs. pass rate"); fig.tight_layout(); fig.savefig(FIG / "swebench_cost_vs_pass.png", dpi=150); plt.close(fig)
# 3. tokens per solve
T = sorted(S, key=lambda s: s["tok_solve"])
fig, ax = plt.subplots(figsize=(7, 3.6))
for i, s in enumerate(T):
    ax.barh(i, s["tok_solve"] / 1e3, color=C, alpha=.85); ax.text(s["tok_solve"] / 1e3 + 5, i, f'{s["tok_solve"]/1e3:,.0f}k', va="center", fontsize=9)
ax.set_yticks(range(len(T)), [s["h"] for s in T]); ax.invert_yaxis()
ax.set_xlabel("tokens per resolved task (thousands; input+output+cache)"); ax.set_title("Context spent per solve")
fig.tight_layout(); fig.savefig(FIG / "swebench_tokens_per_solve.png", dpi=150); plt.close(fig)
for s in S: print(f'{s["h"]:15s} {s["k"]}/{s["n"]} ci={s["ci"][0]:.2f}-{s["ci"][1]:.2f} $/solve={s["usd_solve"]:.4f} tok/solve={s["tok_solve"]:,.0f} median wall (slots regime)={s["wall"]:.0f}s')
