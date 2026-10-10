"""The comparison loop. Resumable: rerun the same command and it skips (instance, harness) pairs already done.

For each instance in the pinned subset:
  1. pull the task image (skipped if present), after checking there's disk to spare
  2. run every harness on it, each through its own proxy with the per-task dollar cap
  3. grade every patch with the official SWE-bench evaluator
  4. delete the image (unless --keep-images)

  python -m sbr.run --pilot 10                       # first 10 instances, all harnesses
  python -m sbr.run --harnesses claude_code,aider    # some harnesses, whole subset
  python -m sbr.run --instances psf__requests-2317   # specific instances
"""
import argparse, json, shutil, subprocess, sys, time
from pathlib import Path
from .config import OUT, DATASET, TASK_BUDGET_USD, HARD_CAP_USD, MODEL, TOOLS, image_for
from . import proxy
from .harnesses import HARNESSES, PROXIED, CHECKS, DOCKER

RESULTS = OUT / "results.jsonl"
MIN_FREE_GB = 25

def _done():
    if not RESULTS.exists():
        return set()
    rows = [json.loads(l) for l in RESULTS.read_text().splitlines() if l.strip()]
    return {(r["instance_id"], r["harness"]) for r in rows if not r.get("error") and r.get("resolved") is not None}

def _instances(ids):
    from datasets import load_dataset
    rows = {r["instance_id"]: r for r in load_dataset(DATASET, split="test") if r["instance_id"] in set(ids)}
    return [rows[i] for i in ids if i in rows]

def _free_gb(path="/"):
    return shutil.disk_usage(path).free / 1e9

def _pull(iid):
    img = image_for(iid)
    if subprocess.run(DOCKER + ["image", "inspect", img], capture_output=True).returncode == 0:
        return img
    if _free_gb() < MIN_FREE_GB:
        sys.exit(f"only {_free_gb():.0f} GB free; free some space (docker image prune -a) before pulling {img}")
    r = subprocess.run(DOCKER + ["pull", "-q", img], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"pull failed for {img}: {r.stderr.strip()[-300:]}")
    return img

def grade(iid, harness, patch, workdir):
    """Official SWE-bench evaluation for one prediction. Returns True/False, or None if the evaluator failed."""
    if not patch.strip():
        return False
    workdir.mkdir(parents=True, exist_ok=True)
    preds = workdir / "pred.jsonl"
    preds.write_text(json.dumps({"instance_id": iid, "model_name_or_path": harness, "model_patch": patch}) + "\n")
    run_id = f"sbr-{harness}-{int(time.time())}"
    cmd = [str(TOOLS / "host/bin/python"), "-m", "swebench.harness.run_evaluation", "--dataset_name", DATASET,
           "--split", "test", "--instance_ids", iid, "--predictions_path", str(preds), "--max_workers", "1",
           "--run_id", run_id, "--timeout", "1800"]
    r = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True)
    (workdir / "grade.log").write_text(r.stdout[-20000:] + "\n" + r.stderr[-20000:])
    rep = workdir / "logs" / "run_evaluation" / run_id / harness / iid / "report.json"
    if not rep.exists():
        return None
    return bool(json.loads(rep.read_text()).get(iid, {}).get("resolved"))

def run_one(inst, harness):
    iid = inst["instance_id"]
    logdir = OUT / "runs" / iid / harness
    shutil.rmtree(logdir, ignore_errors=True); logdir.mkdir(parents=True)
    t0 = time.time()
    row = dict(instance_id=iid, repo=inst["repo"], harness=harness, model=MODEL, task_budget_usd=TASK_BUDGET_USD)
    srv = rec = None
    try:
        srv, rec, url = proxy.start(TASK_BUDGET_USD, logdir / "calls.jsonl")
        patch, notes = HARNESSES[harness](inst, url, logdir)
        (logdir / "patch.diff").write_text(patch)
        row.update(notes=notes, patch_lines=patch.count("\n"),
                   files_changed=len({l[6:] for l in patch.splitlines() if l.startswith("+++ b/")}))
        row["resolved"] = grade(iid, harness, patch, logdir / "grade")
    except Exception as e:  # logged as an error row; a rerun retries it
        row["error"] = f"{type(e).__name__}: {e}"[:500]
    finally:
        if srv:
            srv.shutdown()
    calls = rec.calls if rec else []
    row.update(wall_s=round(time.time() - t0, 1), calls=len(calls), usd=round(sum(c["usd"] for c in calls), 5),
               peak_prompt=max((c["prompt"] for c in calls), default=0),
               budget_refusals=rec.refused if rec else 0,
               http_status={str(k): v for k, v in (rec.status if rec else {}).items()},
               cost_source="proxy" if harness in PROXIED else "harness")
    # A harness that never reached the model (crashed, bad config, network) is an infrastructure failure,
    # not an unresolved task: log it as an error so it's retried on resume and kept out of the score.
    if not row.get("error") and harness in PROXIED and not calls:
        row["error"] = f"no model calls reached the proxy (exit {row.get('notes', {}).get('exit_code')}); see {logdir}/stderr.txt"
    if not row.get("error") and harness == "cursor" and row.get("notes", {}).get("exit_code") not in (0, None) and not row.get("patch_lines"):
        row["error"] = f"cursor exited {row['notes']['exit_code']} with no patch; see {logdir}/stderr.txt"
    with open(RESULTS, "a") as f:
        f.write(json.dumps(row) + "\n")
    status = ("ERROR " + row["error"] if row.get("error") else
              {True: "resolved", False: "unresolved", None: "grade failed"}[row.get("resolved")])
    print(f"  {harness:15s} {status:12s} ${row['usd']:.3f}  {row['calls']} calls  peak {row['peak_prompt']:,} tok  {row['wall_s']:.0f}s",
          flush=True)
    return row

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--harnesses", default=",".join(h for h in HARNESSES if h not in CHECKS))
    ap.add_argument("--instances", default="")
    ap.add_argument("--pilot", type=int, default=0, help="only the first N instances of the subset")
    ap.add_argument("--keep-images", action="store_true")
    a = ap.parse_args()

    harnesses = [h for h in a.harnesses.split(",") if h]
    bad = [h for h in harnesses if h not in HARNESSES]
    if bad:
        sys.exit(f"unknown harness(es): {bad}; known: {list(HARNESSES)}")
    if a.instances:
        ids = a.instances.split(",")
    else:
        sub = OUT / "subset.json"
        if not sub.exists():
            sys.exit("no subset yet: run python -m sbr.subset first")
        ids = [m["instance_id"] for m in json.loads(sub.read_text())["instances"]]
        if a.pilot:
            ids = ids[:a.pilot]
    OUT.mkdir(parents=True, exist_ok=True)
    done = _done()
    insts = _instances(ids)
    print(f"{len(insts)} instances x {len(harnesses)} harnesses; {len(done)} pairs already done; "
          f"spent ${proxy.spent():.2f} of ${HARD_CAP_USD:.0f}", flush=True)
    for n, inst in enumerate(insts, 1):
        iid = inst["instance_id"]
        todo = [h for h in harnesses if (iid, h) not in done]
        if not todo:
            continue
        if proxy.spent() >= HARD_CAP_USD:
            sys.exit(f"hard cap ${HARD_CAP_USD:.0f} reached; stopping")
        print(f"[{n}/{len(insts)}] {iid}", flush=True)
        try:
            _pull(iid)
        except RuntimeError as e:
            print(f"  skip: {e}", flush=True)
            continue
        for h in todo:
            run_one(inst, h)
        if not a.keep_images:
            subprocess.run(DOCKER + ["rmi", "-f", image_for(iid)], capture_output=True)
            subprocess.run(DOCKER + ["image", "prune", "-f"], capture_output=True)
    print(f"done; spent ${proxy.spent():.2f}. Summary: python -m sbr.report", flush=True)

if __name__ == "__main__":
    main()
