"""Pick a pinned random subset of SWE-bench Verified, stratified by repo so Django doesn't swamp it.

python -m sbr.subset            -> writes results/swebench/subset.json (refuses to overwrite)
"""
import json, random, sys
from collections import defaultdict
from .config import DATASET, SUBSET_SIZE, SUBSET_SEED, OUT

def load():
    from datasets import load_dataset
    return list(load_dataset(DATASET, split="test"))

# Verified instances whose gold patch fails in the official harness (SWE-bench issue #267).
# Excluded picks are swapped for another task from the same repo; the rest of the draw is unchanged.
EXCLUDE = {"django__django-10097", "astropy__astropy-7606", "astropy__astropy-8707",
           "astropy__astropy-8872", "matplotlib__matplotlib-20488",
           # Grader tests call the live http://httpbin.org, which this box can't reach, so they can't be graded
           # here (2026-10-11). 2317 was the original pick; the same-repo swap rule then drew 1724, 1766 and 1921,
           # which use the same live-httpbin test suite, so they are excluded too. Next came 2931, but its gold patch
           # fails here (pytest-httpbin fixture recursion error in the image, plus connect-timeout tests that need a
           # routable network), so it is excluded as well. The rule lands on psf__requests-1142, whose 6 tests are
           # offline and whose gold patch resolves. No other pick changes.
           "psf__requests-2317", "psf__requests-1724", "psf__requests-1766", "psf__requests-1921",
           "psf__requests-2931"}

def pick(rows, n=SUBSET_SIZE, seed=SUBSET_SEED):
    by_repo = defaultdict(list)
    for r in sorted(rows, key=lambda r: r["instance_id"]):
        by_repo[r["repo"]].append(r)
    rng = random.Random(seed)
    # proportional allocation, at least one per repo, largest remainders fill the rest
    total = len(rows)
    quota = {k: max(1, int(n * len(v) / total)) for k, v in by_repo.items()}
    rem = sorted(by_repo, key=lambda k: -(n * len(by_repo[k]) / total - int(n * len(by_repo[k]) / total)))
    i = 0
    while sum(quota.values()) < n:
        quota[rem[i % len(rem)]] += 1; i += 1
    while sum(quota.values()) > n:
        k = max(quota, key=quota.get); quota[k] -= 1
    picked = []
    for k in sorted(by_repo):
        got = rng.sample(by_repo[k], quota[k])
        spare = [r for r in by_repo[k] if r not in got and r["instance_id"] not in EXCLUDE]
        swap = random.Random(f"{seed}-{k}")
        picked += [spare.pop(swap.randrange(len(spare))) if r["instance_id"] in EXCLUDE else r for r in got]
    return sorted(picked, key=lambda r: r["instance_id"])

def files_touched(patch):
    return len({l[6:] for l in patch.splitlines() if l.startswith("+++ b/")})

def main():
    path = OUT / "subset.json"
    if path.exists() and "--force" not in sys.argv:
        sys.exit(f"{path} exists; the subset is pinned. Pass --force only if you mean to change it.")
    rows = pick(load())
    OUT.mkdir(parents=True, exist_ok=True)
    meta = [dict(instance_id=r["instance_id"], repo=r["repo"], difficulty=r["difficulty"],
                 files_in_gold_patch=files_touched(r["patch"])) for r in rows]
    path.write_text(json.dumps(dict(dataset=DATASET, seed=SUBSET_SEED, size=len(rows), instances=meta), indent=1))
    by = defaultdict(int)
    for m in meta: by[m["repo"]] += 1
    print(f"wrote {path}: {len(rows)} instances")
    for k, v in sorted(by.items(), key=lambda kv: -kv[1]): print(f"  {v:3d} {k}")
    multi = sum(m["files_in_gold_patch"] > 1 for m in meta)
    print(f"  {multi} of {len(meta)} gold patches touch more than one file")

if __name__ == "__main__":
    main()
