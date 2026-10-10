"""One-command harness: python -m cshape run --strategies all --tasks all --seeds 1"""
import argparse, json, shutil, subprocess, time, traceback, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import yaml
from . import llm, grade
from .strategies import STRATEGIES

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"

def load_tasks():
    tasks = []
    for repo_yaml in sorted((ROOT / "tasks").glob("*/repo.yaml")):
        repo = yaml.safe_load(repo_yaml.read_text())
        for t in sorted(repo_yaml.parent.glob("[th]*.yaml")):
            d = yaml.safe_load(t.read_text()); d["repo"] = repo; tasks.append(d)
    return tasks

def base_checkout(repo):
    """Clone/checkout the pinned base. File-locked so parallel `cshape run` starts don't race on git."""
    import fcntl
    dst = WORK / "base" / repo["name"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst.parent / ".checkout.lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        if not dst.exists():
            subprocess.run(["git", "clone", "-q", repo["url"], str(dst)], check=True)
        subprocess.run(["git", "checkout", "-q", repo["commit"]], cwd=dst, check=True)
    return dst

def fresh_copy(task):
    src = WORK / "base" / task["repo"]["name"]
    dst = WORK / "runs" / f"{task['id']}-{uuid.uuid4().hex[:8]}"
    shutil.copytree(src, dst)
    return dst

def categorize(r):
    """Auto-tag the failure mode of a run (None if passed)."""
    if r.get("passed"):
        return None
    err = r.get("error") or ""
    if err:
        return "context_overflow" if ("prompt is too long" in err or "context" in err.lower()) else "error"
    n = r.get("notes", {})
    d = r.get("diff", {})
    if d.get("added", 0) + d.get("removed", 0) == 0:
        if n.get("last_stop_reason") == "max_tokens":
            return "output_truncated"  # model hit the 16k output cap mid-answer
        return "apply_failure" if n.get("apply_errors") else "no_edit"
    tail = r.get("test_tail", "") + r.get("check_err", "")
    if any(k in tail for k in ("ImportError", "ModuleNotFoundError", "cannot import name")):
        return "broken_import"
    if r.get("missed_callers", 0) > 0:
        return "missed_caller"
    if n.get("apply_errors"):
        return "apply_failure"
    if not r.get("tests_ok", True):
        return "test_failure_other"
    return "check_failed"

def run_one(task, strat, seed, out):
    root = fresh_copy(task)
    rec = dict(task=task["id"], kind=task["kind"], strategy=strat, seed=seed, model=llm.MODEL, ts=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    t0 = time.time()
    try:
        stats = STRATEGIES[strat](root, task)
        rec.update(stats)
        rec.update(grade.grade(root, task))
    except llm.BudgetExceeded as e:
        rec.update(error=str(e), passed=False)
    except Exception as e:
        rec.update(error=f"{type(e).__name__}: {e}", trace=traceback.format_exc()[-1500:], passed=False)
    rec["wall_s"] = round(time.time() - t0, 1)
    rec["run_id"] = root.name
    tdir = Path(out).resolve().parent / "transcripts"; tdir.mkdir(parents=True, exist_ok=True)
    tpath = tdir / f"{Path(out).stem}__{strat}__{root.name}.json"
    for x in reversed(rec.get("transcript") or []):
        if isinstance(x, dict) and x.get("stop_reason"):
            rec.setdefault("notes", {})["last_stop_reason"] = x["stop_reason"]; break
    tpath.write_text(json.dumps({"task": task["id"], "strategy": strat, "seed": seed,
                                 "transcript": rec.pop("transcript", None)}, default=str))
    rec["transcript_path"] = str(tpath.relative_to(ROOT))
    rec["failure_category"] = categorize(rec)
    rec["config"] = dict(strategy=strat, model=llm.MODEL, max_steps=__import__("cshape.strategies", fromlist=["x"]).MAX_STEPS)
    with open(out, "a") as f:
        f.write(json.dumps(rec) + "\n")
    shutil.rmtree(root, ignore_errors=True)
    print(f"{task['id']:<28} {strat:<15} seed{seed} pass={rec.get('passed')} missed={rec.get('missed_callers')} "
          f"${rec.get('cost_usd', 0):.4f} {rec['wall_s']}s {rec.get('error','')}", flush=True)
    return rec

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--strategies", default="all"); r.add_argument("--tasks", default="all")
    r.add_argument("--seeds", type=int, default=1); r.add_argument("--workers", type=int, default=6)
    r.add_argument("--out", default=str(ROOT / "results" / "runs.jsonl"))
    sub.add_parser("verify", help="apply each task's reference solution and grade it")
    sub.add_parser("spend")
    a = ap.parse_args()
    if a.cmd == "spend":
        print(f"spent ${llm.spent():.4f} of hard cap ${llm.HARD_CAP_USD}"); return
    tasks = load_tasks()
    for repo in {t["repo"]["name"]: t["repo"] for t in tasks}.values():
        base_checkout(repo)
        subprocess.run(["git", "reset", "-q", "--hard"], cwd=WORK / "base" / repo["name"], check=True)
        subprocess.run(["git", "clean", "-qfd"], cwd=WORK / "base" / repo["name"], check=True)
    if a.cmd == "verify":
        for t in tasks:
            root = fresh_copy(t)
            subprocess.run(["git", "apply", str(ROOT / "tasks" / t["repo"]["name"] / t["reference"])], cwd=root, check=True)
            g = grade.grade(root, t)
            print(t["id"], "PASS" if g["passed"] else f"FAIL {g}")
            pre = fresh_copy(t); g0 = grade.grade(pre, t)
            print("   unmodified repo passes grader?", g0["passed"], "(should be False)")
            shutil.rmtree(root); shutil.rmtree(pre)
        return
    strats = list(STRATEGIES) if a.strategies == "all" else a.strategies.split(",")
    if a.tasks != "all":
        want = a.tasks.split(","); tasks = [t for t in tasks if t["id"] in want]
    jobs = [(t, s, k) for k in range(a.seeds) for t in tasks for s in strats]
    # resume: skip jobs already logged without an error; drop errored rows so they are re-run
    if Path(a.out).exists():
        keep, done = [], set()
        for line in open(a.out):
            r = json.loads(line)
            if r.get("error"):
                continue
            keep.append(line); done.add((r["task"], r["strategy"], r["seed"]))
        Path(a.out).write_text("".join(keep))
        jobs = [j for j in jobs if (j[0]["id"], j[1], j[2]) not in done]
    print(f"{len(jobs)} runs; spent so far ${llm.spent():.4f}; cap ${llm.HARD_CAP_USD}")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(lambda j: run_one(*j, a.out), jobs))
    print(f"done; total spent ${llm.spent():.4f}")

if __name__ == "__main__":
    main()
