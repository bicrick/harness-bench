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
import argparse, fcntl, json, os, shutil, subprocess, sys, threading, time
from pathlib import Path
from .config import OUT, DATASET, TASK_BUDGET_USD, HARD_CAP_USD, MODEL, TOOLS, image_for
from . import proxy
from .harnesses import HARNESSES, PROXIED, CHECKS, DOCKER, CPUS, MEM

RESULTS = OUT / "results.jsonl"
MIN_FREE_GB = 25
RERUN = OUT / "rerun_queue.json"  # pairs whose old-regime row is flagged (timeouts/conn errors under box pressure)
SKIP_FILE = OUT / "skip_instances.json"  # infra-broken instances; never grade, excluded from scoring
EXCLUDE_NOTE = "excluded: infra (httpbin unreachable)"

def _skip_ids():
    if not SKIP_FILE.exists():
        return set()
    return set(json.loads(SKIP_FILE.read_text()).get("instances") or [])

def _ensure_excluded(iid, harnesses, repo=""):
    """Append exclusion rows for (iid, h) pairs that lack one, so resume + scoring stay consistent."""
    have = set()
    if RESULTS.exists():
        for l in RESULTS.read_text().splitlines():
            if not l.strip(): continue
            r = json.loads(l)
            if r.get("instance_id") == iid and (r.get("excluded") or r.get("notes") == EXCLUDE_NOTE):
                have.add(r["harness"])
    with open(RESULTS, "a") as f:
        for h in harnesses:
            if h in have: continue
            f.write(json.dumps(dict(instance_id=iid, repo=repo, harness=h, model=MODEL, resolved=None,
                                    notes=EXCLUDE_NOTE, excluded=True, calls=0, usd=0.0, peak_prompt=0,
                                    wall_s=0, concurrency_regime=REGIME, cost_source="n/a")) + "\n")

# Concurrency control: at most SLOTS agent runs (agent + grading) at once across every runner on the box,
# via flock'd slot files. wall_s is measured from slot acquisition, so time spent queueing doesn't count.
SLOTS = int(os.environ.get("SBR_SLOTS", "3"))
SLOT_DIR = Path(os.environ.get("SBR_SLOT_DIR", Path.home() / "sbr-slots"))
REGIME = f"slots{SLOTS}_cpus{CPUS}_mem{MEM}"

def _acquire_slot(label):
    SLOT_DIR.mkdir(exist_ok=True)
    t0 = last = time.time()
    while True:
        for k in range(SLOTS):
            f = open(SLOT_DIR / f"slot{k}.lock", "a+")
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                f.seek(0); f.truncate(); f.write(f"{os.getpid()} {label}\n"); f.flush()
                return f, time.time() - t0
            except BlockingIOError:
                f.close()
        if time.time() - last > 300:  # heartbeat so the manager's stall detector sees a live runner
            print(f"  waiting for a slot ({(time.time()-t0)/60:.0f} min)", flush=True); last = time.time()
        time.sleep(5)

def _enforce_limits(stop):
    """Host-side agents (mini-swe-agent, SWE-agent) and the SWE-bench grader create their own containers;
    clamp any unclamped running container to the same CPU/memory limits within a few seconds of start."""
    nano = int(float(CPUS) * 1e9)
    while not stop.wait(3):
        ids = subprocess.run(DOCKER + ["ps", "-q"], capture_output=True, text=True).stdout.split()
        if not ids: continue
        r = subprocess.run(DOCKER + ["inspect", "-f", "{{.Id}} {{.HostConfig.NanoCpus}}"] + ids, capture_output=True, text=True)
        for l in r.stdout.splitlines():
            cid, n = l.split()
            if int(n) != nano:
                subprocess.run(DOCKER + ["update", f"--cpus={CPUS}", f"--memory={MEM}", f"--memory-swap={MEM}", cid],
                               capture_output=True)

# Shards: several runners of one harness may run concurrently on overlapping instance lists. A pair is run only
# by the runner holding its flock'd claim file (released automatically if that runner dies), and only if a fresh
# read of results.jsonl still says it's needed, so no two shards ever run the same (instance, harness) pair.
CLAIM_DIR = Path(os.environ.get("SBR_CLAIM_DIR", Path.home() / "sbr-claims"))

def _claim(iid, harness):
    CLAIM_DIR.mkdir(exist_ok=True)
    f = open(CLAIM_DIR / f"{iid}__{harness}.lock", "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close(); return None
    f.seek(0); f.truncate(); f.write(f"{os.getpid()}\n"); f.flush()
    return f

def _still_needed(iid, harness, second):
    done, fresh = _done()
    if second:
        return (iid, harness) in _rerun_pairs() and (iid, harness) not in fresh
    return (iid, harness) not in done

def _rerun_pairs():
    return {tuple(p) for p in json.loads(RERUN.read_text())["pairs"]} if RERUN.exists() else set()

def _done():
    if not RESULTS.exists():
        return set(), set()
    rows = [json.loads(l) for l in RESULTS.read_text().splitlines() if l.strip()]
    skip = _skip_ids()
    good, fresh, zero = set(), set(), {}
    for r in rows:
        k = (r["instance_id"], r["harness"])
        excluded = r.get("excluded") or r.get("notes") == EXCLUDE_NOTE or r["instance_id"] in skip
        if excluded and not r.get("error"):
            good.add(k); fresh.add(k); continue
        # infra failure: a proxied harness that never reached the model (upstream 5xx / CLI crash) gets one retry
        if not r["harness"].startswith("cursor") and not r.get("calls") and r.get("resolved") is False:
            zero[k] = zero.get(k, 0) + 1
            if zero[k] < 2:
                good.discard(k); fresh.discard(k); continue
        if not r.get("error") and r.get("resolved") is not None:
            good.add(k)
            if r.get("concurrency_regime", "unconstrained") != "unconstrained":
                fresh.add(k)
    # every real harness is done for a skipped instance even before a row lands
    for iid in skip:
        for h in HARNESSES:
            if h in CHECKS: continue
            good.add((iid, h)); fresh.add((iid, h))
    return good, fresh

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
    slot, waited = _acquire_slot(f"{iid} {harness}")
    t0 = time.time()
    row = dict(instance_id=iid, repo=inst["repo"], harness=harness, model=MODEL, task_budget_usd=TASK_BUDGET_USD,
               concurrency_regime=REGIME, slot_wait_s=round(waited, 1))
    srv = rec = None
    try:
        srv, rec, url = proxy.start(TASK_BUDGET_USD, logdir / "calls.jsonl", thinking="disabled" if harness.endswith("_nothink") else None)
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
        row["wall_s"] = round(time.time() - t0, 1)
        slot.close()  # releases the flock
    calls = rec.calls if rec else []
    row.update(calls=len(calls), usd=round(sum(c["usd"] for c in calls), 5),
               peak_prompt=max((c["prompt"] for c in calls), default=0),
               budget_refusals=rec.refused if rec else 0,
               http_status={str(k): v for k, v in (rec.status if rec else {}).items()},
               cost_source="proxy" if harness in PROXIED else "harness")
    # A harness that never reached the model (crashed, bad config, network) is an infrastructure failure,
    # not an unresolved task: log it as an error so it's retried on resume and kept out of the score.
    # Exception: the upstream API answered with a 4xx other than 429 (e.g. 400 invalid request). The harness did
    # reach the model; the API rejected what it sent. That's the harness failing the task, not infrastructure, so
    # it's logged as unresolved (the 0-call rule in _done still gives it one retry before it counts).
    rejected = {k for k in row["http_status"] if k.startswith("4") and k != "429"}
    if not row.get("error") and harness in PROXIED and not calls and rejected:
        row.setdefault("notes", {})
        if isinstance(row["notes"], dict): row["notes"]["upstream_rejected"] = sorted(rejected)
        row["resolved"] = False
    elif not row.get("error") and harness in PROXIED and not calls:
        row["error"] = f"no model calls reached the proxy (exit {row.get('notes', {}).get('exit_code')}); see {logdir}/stderr.txt"
    if not row.get("error") and harness.startswith("cursor") and row.get("notes", {}).get("exit_code") not in (0, None) and not row.get("patch_lines"):
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
    done, fresh = _done()
    rerun = _rerun_pairs() - fresh
    insts = _instances(ids)
    stop = threading.Event(); threading.Thread(target=_enforce_limits, args=(stop,), daemon=True).start()
    print(f"{len(insts)} instances x {len(harnesses)} harnesses; {len(done)} pairs already done; "
          f"spent ${proxy.spent():.2f} of ${HARD_CAP_USD:.0f}", flush=True)
    # pass 1: everything not yet done; pass 2: flagged old-regime pairs, rerun under the new regime
    plan = [(n, inst, False) for n, inst in enumerate(insts, 1)] + [(n, inst, True) for n, inst in enumerate(insts, 1)]
    skip = _skip_ids()
    for n, inst, second in plan:
        iid = inst["instance_id"]
        if iid in skip:
            if not second:
                print(f"[{n}/{len(insts)}] {iid}  SKIP {EXCLUDE_NOTE}", flush=True)
                _ensure_excluded(iid, harnesses, inst.get("repo", ""))
            continue
        if second:
            todo = [h for h in harnesses if (iid, h) in rerun]
        else:
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
            claim = _claim(iid, h)
            if not claim:
                print(f"  {h}: claimed by another shard; skipping", flush=True); continue
            try:
                if not _still_needed(iid, h, second):
                    print(f"  {h}: already done by another shard; skipping", flush=True); continue
                if second: print(f"  rerun (flagged old-regime row)", flush=True)
                run_one(inst, h)
            finally:
                claim.close()
        if not a.keep_images:
            subprocess.run(DOCKER + ["rmi", "-f", image_for(iid)], capture_output=True)
            subprocess.run(DOCKER + ["image", "prune", "-f"], capture_output=True)
    print(f"done; spent ${proxy.spent():.2f}. Summary: python -m sbr.report", flush=True)

if __name__ == "__main__":
    main()
