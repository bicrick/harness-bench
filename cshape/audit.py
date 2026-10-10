"""Data-integrity audit over raw run logs. Writes results/integrity.json and prints a short report.
Checks: required fields on every row, transcript file exists, duplicate (file, task, strategy, seed) rows,
and that logged per-run cost reconciles with the API spend ledger (results/ledger.json).
Usage: python -m cshape.audit   (also run by `make figures`)"""
import json, os, subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
REQUIRED = ["task", "strategy", "seed", "model", "config", "run_id", "passed", "missed_callers", "diff", "tokens",
            "cost_usd", "wall_s", "transcript_path", "failure_category"]
SINGLE_SHOT = {"full", "touched", "skel_L0", "skel_L1", "skel_L2", "skel_L3"}  # no tool loop: tool_calls is 0 by design
TOLERANCE_USD = 0.25  # in-flight jobs bill the ledger per call but only log a row when the job finishes


def runs_in_flight():
    try:
        out = subprocess.run(["pgrep", "-af", "cshape run"], capture_output=True, text=True).stdout
        return [l for l in out.splitlines() if "pgrep" not in l]
    except Exception:
        return []


def main():
    files = {}
    logged = 0.0
    for f in sorted(RES.glob("*.jsonl")):
        rows = [json.loads(l) for l in f.open() if l.strip()]
        miss, notr, no_tc = Counter(), 0, 0
        keys = Counter((r.get("task"), r.get("strategy"), r.get("seed")) for r in rows)
        for r in rows:
            for k in REQUIRED:
                if k not in r:
                    miss[k] += 1
            tp = r.get("transcript_path")
            if not tp or not (ROOT / tp).exists():
                notr += 1
            if r.get("strategy") not in SINGLE_SHOT and "tool_calls" not in r.get("notes", {}):
                no_tc += 1
        cost = sum(r.get("cost_usd") or 0 for r in rows)
        logged += cost
        files[f.name] = dict(rows=len(rows), cost_usd=round(cost, 4), errors=sum(bool(r.get("error")) for r in rows),
                             missing_fields=dict(miss), missing_transcripts=notr, agentic_rows_without_tool_calls=no_tc,
                             duplicate_jobs=sum(v - 1 for v in keys.values() if v > 1), archived=f.name.startswith("archive_"))
    ledger = json.loads((RES / "ledger.json").read_text())["total_usd"]
    gap = ledger - logged
    live = runs_in_flight()
    problems = []
    for name, s in files.items():
        if s["archived"]:
            continue
        if s["missing_fields"]:
            problems.append(f"{name}: rows missing fields {s['missing_fields']}")
        if s["missing_transcripts"]:
            problems.append(f"{name}: {s['missing_transcripts']} rows without a transcript file")
        if s["agentic_rows_without_tool_calls"]:
            problems.append(f"{name}: {s['agentic_rows_without_tool_calls']} agentic rows without tool_calls")
    if gap < -0.01:
        problems.append(f"logged cost exceeds ledger by ${-gap:.4f}")
    elif gap > TOLERANCE_USD or (gap > 0.02 and not live):
        problems.append(f"ledger exceeds logged per-run cost by ${gap:.4f} with {len(live)} runs in flight")
    out = dict(checked_at=datetime.now().astimezone().isoformat(timespec="seconds"), files=files,
               ledger_usd=round(ledger, 4), logged_usd=round(logged, 4), unlogged_gap_usd=round(gap, 4),
               runs_in_flight=len(live), ok=not problems, problems=problems)
    (RES / "integrity.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"ledger ${ledger:.2f}  logged ${logged:.2f}  gap ${gap:.3f}  in-flight {len(live)}  ->",
          "OK" if not problems else "PROBLEMS:\n  " + "\n  ".join(problems))
    return out


if __name__ == "__main__":
    main()
