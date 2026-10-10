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


UNEXPLAINED_MAX_USD = 1.25  # spend from before the per-call log existed (rows lost when runs were killed at 3:43, 4:24 and 5:09 AM)



def _first_call_ts():
    p = RES / "ledger_calls.ndjson"
    if not p.exists():
        return None
    with p.open() as fh:
        line = fh.readline().strip()
    return json.loads(line).get("ts") if line else None

def runs_in_flight():
    try:
        out = subprocess.run(["pgrep", "-af", "cshape run"], capture_output=True, text=True).stdout
        return [l for l in out.splitlines() if "pgrep" not in l]
    except Exception:
        return []


def workers_in_flight(live):
    n = 0
    for l in live:
        parts = l.split()
        n += int(parts[parts.index("--workers") + 1]) if "--workers" in parts else 6
    return n


def call_attribution(logged_ids, live):
    """Split per-call ledger spend (results/ledger_calls.ndjson) into: calls belonging to logged rows, calls of
    runs still in flight (live pid, no row yet), and orphaned calls (dead pid, no row: run killed mid-flight)."""
    f = RES / "ledger_calls.ndjson"
    if not f.exists():
        return None
    live_pids = {int(l.split()[0]) for l in live}
    a = dict(calls=0, usd=0.0, logged_usd=0.0, in_flight_usd=0.0, orphaned_usd=0.0, untagged_usd=0.0, orphaned_run_ids=set())
    for line in f.open():
        if not line.strip():
            continue
        c = json.loads(line)
        a["calls"] += 1; a["usd"] += c["usd"]
        rid = c.get("run_id")
        if not rid:
            a["untagged_usd"] += c["usd"]  # e.g. external-harness proxy calls
        elif rid in logged_ids:
            a["logged_usd"] += c["usd"]
        elif c.get("pid") in live_pids:
            a["in_flight_usd"] += c["usd"]
        else:
            a["orphaned_usd"] += c["usd"]; a["orphaned_run_ids"].add(rid)
    a["orphaned_runs"] = len(a.pop("orphaned_run_ids"))
    return {k: round(v, 4) if isinstance(v, float) else v for k, v in a.items()}


def main():
    files = {}
    logged = 0.0
    logged_ids = set()
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
        logged_ids |= {r.get("run_id") for r in rows if r.get("run_id")}
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
    attr = call_attribution(logged_ids, live)
    # gap = in-flight spend + orphaned spend (killed runs) + anything billed before the per-call log started
    unexplained = gap - ((attr["in_flight_usd"] + attr["orphaned_usd"] + attr["untagged_usd"]) if attr else 0.0)
    if gap < -0.01:
        problems.append(f"logged cost exceeds ledger by ${-gap:.4f}")
    elif attr is None and (gap > UNEXPLAINED_MAX_USD + 0.10 * workers_in_flight(live) or (gap > UNEXPLAINED_MAX_USD and not live)):
        problems.append(f"ledger exceeds logged per-run cost by ${gap:.4f} with {len(live)} runs in flight")
    elif attr is not None and unexplained > UNEXPLAINED_MAX_USD:
        problems.append(f"${unexplained:.4f} of ledger spend is not attributable to any logged, in-flight or orphaned run")
    out = dict(checked_at=datetime.now().astimezone().isoformat(timespec="seconds"), files=files,
               ledger_usd=round(ledger, 4), logged_usd=round(logged, 4), unlogged_gap_usd=round(gap, 4),
               runs_in_flight=len(live), workers_in_flight=workers_in_flight(live), call_attribution=attr,
               unattributed_pre_call_log_usd=round(unexplained, 4),
               call_log_first_ts=_first_call_ts(),
               note=("ledger = logged rows + in-flight + orphaned (killed mid-run, no row) + pre-call-log spend. Rows were "
                     "lost when all runs were killed and restarted at ~3:43, ~4:24 and ~5:09 AM CT (API stall fixes, seed cuts); that spend "
                     f"predates results/ledger_calls.ndjson (first logged call {_first_call_ts()}) so it is only known as the residual."),
               ok=not problems, problems=problems)
    (RES / "integrity.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"ledger ${ledger:.2f}  logged ${logged:.2f}  gap ${gap:.3f}  in-flight {len(live)} procs/{workers_in_flight(live)} workers"
          f"  attribution {attr}  unattributed ${unexplained:.3f}  ->",
          "OK" if not problems else "PROBLEMS:\n  " + "\n  ".join(problems))
    return out


if __name__ == "__main__":
    main()
