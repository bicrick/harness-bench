"""Per-harness table over the first N instances of the pinned subset (pilot = 10), from summary_tokens.csv.
Usage: python3 scripts/swebench_pilot_report.py [N]  -> prints a markdown table."""
import csv, json, pathlib, statistics, sys
R = pathlib.Path(__file__).resolve().parent.parent / "results/swebench"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
ids = [i["instance_id"] for i in json.loads((R / "subset.json").read_text())["instances"]][:N]
rows = [r for r in csv.DictReader(open(R / "summary_tokens.csv")) if r["instance_id"] in ids and r["harness"] != "gold"]
by = {}
for r in rows: by.setdefault(r["harness"], []).append(r)
print(f"| harness | done | solved | pass rate | $ total | $/solve | tokens/task | tokens/solve | median wall s/task |")
print("|---|---|---|---|---|---|---|---|---|")
for h, rs in sorted(by.items(), key=lambda kv: -sum(r["resolved"] == "True" for r in kv[1])):
    s = sum(r["resolved"] == "True" for r in rs); U = sum(float(r["usd_est"]) for r in rs); T = sum(int(r["total_tokens"]) for r in rs)
    w = statistics.median(float(r["wall_s"]) for r in rs if r["wall_s"])
    print(f"| {h} | {len(rs)}/{N} | {s} | {s/len(rs):.0%} | {U:.3f} | {(U/s if s else 0):.4f} | {T//len(rs):,} | {(T//s if s else 0):,} | {w:.0f} |")
