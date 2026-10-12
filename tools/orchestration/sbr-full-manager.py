#!/usr/bin/env python3
"""Stage 2 manager: one runner per harness over the 50-task subset; keeps disk/RAM healthy, restarts dead/stuck runners."""
import json, os, re, shlex, shutil, subprocess, time, datetime
REPO = os.path.expanduser("~/context-shaping"); OUT = f"{REPO}/results/swebench"
H = ["mini_swe_agent", "swe_agent", "opencode", "aider", "claude_code", "cursor"]
CAP = "45"
DOCKER = ["sudo", "docker"]
STATE = os.path.expanduser("~/sbr-full-manager-state.json")
LOG = os.path.expanduser("~/sbr-full-manager.log")
def log(m):
    with open(LOG, "a") as f: f.write(f"{datetime.datetime.now():%m-%d %H:%M} {m}\n")
def sh(c): return subprocess.run(c, capture_output=True, text=True)
def alive(s): return sh(["tmux", "has-session", "-t", f"={s}"]).returncode == 0  # exact: shard names share the prefix
def free_gb(): return shutil.disk_usage("/").free / 1e9
def mem_gb():
    for l in open("/proc/meminfo"):
        if l.startswith("MemAvailable"): return int(l.split()[1]) / 1e6
ids = [m["instance_id"] for m in json.load(open(f"{OUT}/subset.json"))["instances"]]
def image_for(i):
    a, b = i.split("__", 1); return f"swebench/sweb.eval.x86_64.{a}_1776_{b}:latest"
def skip_ids():
    try: return set(json.load(open(f"{OUT}/skip_instances.json")).get("instances") or [])
    except FileNotFoundError: return set()
def done():
    s = set(); fresh = set(); zero = {}
    try: rq = {tuple(p) for p in json.load(open(f"{OUT}/rerun_queue.json"))["pairs"]}
    except FileNotFoundError: rq = set()
    skip = skip_ids()
    try:
        for l in open(f"{OUT}/results.jsonl"):
            if l.strip():
                r = json.loads(l)
                excl = r.get("excluded") or r.get("notes") == "excluded: infra (httpbin unreachable)" or r["instance_id"] in skip
                if excl and not r.get("error"):
                    s.add((r["instance_id"], r["harness"])); fresh.add((r["instance_id"], r["harness"])); continue
                k = (r["instance_id"], r["harness"])
                if r["harness"] != "cursor" and not r.get("calls") and r.get("resolved") is False:
                    zero[k] = zero.get(k, 0) + 1
                    if zero[k] < 2: s.discard(k); fresh.discard(k); continue
                if not r.get("error") and r.get("resolved") is not None:
                    s.add((r["instance_id"], r["harness"]))
                    if r.get("concurrency_regime", "unconstrained") != "unconstrained": fresh.add((r["instance_id"], r["harness"]))
    except FileNotFoundError: pass
    for i in skip:
        for h in H: s.add((i, h)); fresh.add((i, h))
    return s - (rq - fresh)  # flagged old-regime pairs aren't done until rerun under the new regime
def current(h):
    p = os.path.expanduser(f"~/sbr-full-{h}.txt")
    if not os.path.exists(p): return None, 0
    cur = None
    for l in open(p, errors="ignore"):
        m = re.match(r"\[\d+/\d+\] (\S+)", l)
        if m: cur = m.group(1)
    return cur, time.time() - os.path.getmtime(p)
def launch(h):
    cmd = (f'source ~/sbr-env.sh; cd {REPO} && SBR_TOOLS=/home/box/sbr-tools SBR_HARD_CAP={CAP} SBR_DOCKER="sudo docker" '
           f'/home/box/sbr-tools/host/bin/python -m sbr.run --keep-images --harnesses {h} 2>&1 | tee -a ~/sbr-full-{h}.txt')
    sh(["tmux", "new", "-d", "-s", f"sbr_full_{h}", "sg", "docker", "-c", "bash -c " + shlex.quote(cmd)]); log(f"launched {h}")  # sg: grading needs the docker group
SHARDS = os.path.expanduser("~/sbr-shards.json")  # {"swe_agent_s1": {"harness": "swe_agent", "instances": [...]}, ...}
def shards():
    try: return json.load(open(SHARDS))
    except FileNotFoundError: return {}
def shard_current(name):
    p = os.path.expanduser(f"~/sbr-full-{name}.txt")
    if not os.path.exists(p): return None, 0
    cur = None
    for l in open(p, errors="ignore"):
        m = re.match(r"\[\d+/\d+\] (\S+)", l)
        if m: cur = m.group(1)
    return cur, time.time() - os.path.getmtime(p)
def launch_shard(name, h, inst):
    # same runner, restricted to its own instance list; the runner's claim locks keep shards off each other's pairs
    cmd = (f'source ~/sbr-env.sh; cd {REPO} && SBR_TOOLS=/home/box/sbr-tools SBR_HARD_CAP={CAP} SBR_DOCKER="sudo docker" '
           f'/home/box/sbr-tools/host/bin/python -m sbr.run --keep-images --harnesses {h} --instances {",".join(inst)} 2>&1 | tee -a ~/sbr-full-{name}.txt')
    sh(["tmux", "new", "-d", "-s", f"sbr_full_{name}", "sg", "docker", "-c", "bash -c " + shlex.quote(cmd)]); log(f"launched shard {name} ({len(inst)} instances)")
def harness_sessions(h):
    return [f"sbr_full_{h}"] + [f"sbr_full_{n}" for n, v in shards().items() if v["harness"] == h]
def kill_session(sess, h):
    """Stall restart for one runner of a harness that has other live shards: kill only that runner, and only
    containers that no other live runner of this harness could own is unknowable, so leave containers to the
    age sweep (agent containers outlive WALL_S + grading only if orphaned)."""
    sh(["tmux", "kill-session", "-t", f"={sess}"])
def kill(h):
    others = [x for x in harness_sessions(h) if x != f"sbr_full_{h}" and alive(x)]
    if others:
        kill_session(f"sbr_full_{h}", h); return
    sh(["tmux", "kill-session", "-t", f"=sbr_full_{h}"])
    for n in sh(DOCKER + ["ps", "-aq", "--filter", f"name=sbr-{h.replace('_','-')}"]).stdout.split() +              sh(DOCKER + ["ps", "-aq", "--filter", f"name=sbr-{h}"]).stdout.split() + (sh(DOCKER + ["ps", "-aq", "--filter", "name=minisweagent-"]).stdout.split() if h == "mini_swe_agent" else []):
        sh(DOCKER + ["rm", "-f", n])
st = json.load(open(STATE)) if os.path.exists(STATE) else {"restarts": {}, "paused": {}}
while True:
    try:
        d = done(); now = time.time()
        pos = {}
        for h in H:
            s = f"sbr_full_{h}"; finished = all((i, h) in d for i in ids)
            cur, idle = current(h)
            if alive(s):
                pos[h] = ids.index(cur) if cur in ids else 0
                if idle > 30 * 60:
                    log(f"{h} stuck {idle/60:.0f} min on {cur}; restarting"); kill(h)
                    st["restarts"][h] = st["restarts"].get(h, 0) + 1
            elif not finished:
                pos[h] = next(k for k, i in enumerate(ids) if (i, h) not in d)
                if h == "cursor" and alive("sbr_cursor"): continue   # pilot cursor still running
                if st["paused"].get(h, 0) > now: continue
                if st["restarts"].get(h, 0) > 6: continue
                if free_gb() < 30 or mem_gb() < (2.5 if h == "mini_swe_agent" else 2): continue
                if os.path.exists(os.path.expanduser(f"~/sbr-full-{h}.txt")):
                    st["restarts"][h] = st["restarts"].get(h, 0) + 1
                launch(h)
        # shards: extra runners of slow harnesses on disjoint instance lists (see ~/sbr-deviations.md)
        for name, v in shards().items():
            h = v["harness"]; sess = f"sbr_full_{name}"
            cur, idle = shard_current(name)
            if cur in ids: pos[name] = ids.index(cur)
            if alive(sess):
                if idle > 30 * 60:
                    log(f"shard {name} stuck {idle/60:.0f} min on {cur}; restarting"); kill_session(sess, h)
                    st["restarts"][name] = st["restarts"].get(name, 0) + 1
            elif not all((i, h) in d for i in v["instances"]):
                if st["restarts"].get(name, 0) > 6: continue
                if free_gb() < 30 or mem_gb() < 2: continue
                if os.path.exists(os.path.expanduser(f"~/sbr-full-{name}.txt")):
                    st["restarts"][name] = st["restarts"].get(name, 0) + 1
                launch_shard(name, h, v["instances"])
        # orphaned agent containers (a killed shard's): agent+grade can't exceed ~70 min, so sweep older ones
        for l in sh(DOCKER + ["ps", "--filter", "name=sbr-", "--format", "{{.ID}} {{.RunningFor}}"]).stdout.splitlines():
            cid, age = l.split(" ", 1)
            if "hour" in age and not age.startswith("About an hour"): sh(DOCKER + ["rm", "-f", cid]); log(f"swept orphan container {cid} ({age})")
        # memory: pause the cheapest fast runner if RAM is tight
        if mem_gb() < 1.5:
            for h in ["mini_swe_agent", "aider", "opencode", "claude_code"]:
                if alive(f"sbr_full_{h}"):
                    log(f"low RAM {mem_gb():.1f} GB; pausing {h} 20 min"); kill(h); st["paused"][h] = now + 1200; break
        # disk: remove images every harness is past; under pressure, any image not at a runner's current task
        have = set(sh(DOCKER + ["images", "--format", "{{.Repository}}:{{.Tag}}"]).stdout.split())
        protect = {ids[p] for p in pos.values()} | ({current("cursor")[0]} if alive("sbr_cursor") else set())
        for k, i in enumerate(ids):
            img = image_for(i)
            if img not in have or i in protect: continue
            all_done = all((i, h) in d for h in H)
            if all_done or (free_gb() < 35 and k not in pos.values()):
                if sh(DOCKER + ["rmi", img]).returncode == 0: log(f"rmi {i} ({'all done' if all_done else 'disk pressure'})")
        sh(DOCKER + ["container", "prune", "-f"]); sh(DOCKER + ["image", "prune", "-f"])
        if free_gb() < 40: sh(DOCKER + ["builder", "prune", "-f", "--filter", "until=30m"])  # build cache grew to ~40 GB and starved disk (01:40)
        json.dump(st, open(STATE, "w"))
        if all((i, h) in d for i in ids for h in H) and not any(alive(x) for h in H for x in harness_sessions(h)):
            log("all 300 pairs done"); break
    except Exception as e:
        log(f"manager error: {e!r}")
    time.sleep(180)
