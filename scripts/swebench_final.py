"""Final per-harness table over the pinned subset, from summary_tokens.csv (run swebench_tokens.py first).
rate: solved/N with 95% Wilson CI; $/solve: usd_est sum / solves; tok/solve: total tokens / solves;
min/solve: fair-regime rows only (concurrency_regime != unconstrained), their wall time / their solves.
cache: cache_read / (input + cache_read + cache_write)."""
import csv, json, math, pathlib
R = pathlib.Path(__file__).resolve().parent.parent / "results/swebench"
ids = {i["instance_id"] for i in json.loads((R / "subset.json").read_text())["instances"]}
N = len(ids)
def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h
by = {}
for r in csv.DictReader(open(R / "summary_tokens.csv")):
    if r["instance_id"] in ids and r["harness"] != "gold": by.setdefault(r["harness"], []).append(r)
out = []
for h, rs in by.items():
    s = sum(r["resolved"] == "True" for r in rs); U = sum(float(r["usd_est"]) for r in rs); T = sum(int(r["total_tokens"]) for r in rs)
    f = [r for r in rs if r["concurrency_regime"] != "unconstrained"]; fs = sum(r["resolved"] == "True" for r in f)
    W = sum(float(r["wall_s"] or 0) for r in f)
    g = lambda k: sum(int(r[k]) for r in rs)
    lo, hi = wilson(s, N)
    out.append(dict(harness=h, runs=len(rs), solved=s, rate=round(100 * s / N), ci=[round(100 * lo), round(100 * hi)],
                    usd_total=round(U, 3), usd=round(U / s, 4), tok=T // s, tok_task=T // len(rs), min=round(W / 60 / fs, 1),
                    fair_rows=len(f), cache=round(100 * g("cache_read") / (g("input") + g("cache_read") + g("cache_write")))))
out.sort(key=lambda d: -d["solved"])
print(json.dumps(dict(N=N, harnesses=out), indent=1))
