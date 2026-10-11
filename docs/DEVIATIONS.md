# SWE-bench pilot deviations (box-level fixes, approved in the monitor routine)

## 2026-10-10 19:20 CDT swe_agent setup (approved fix 3)
- swe_agent failed task 1 with "no model calls reached the proxy": litellm raised `UnsupportedParamsError: claude-haiku-5-5 does not support temperature=0.0` (SWE-agent's default). Task 2 then hit "Runtime did not start within timeout" (swe-rex's 180 s startup window; container creation is very slow under the vfs storage driver).
- Fix (box config only, no sbr/ code): appended to /home/box/sbr-tools/swe-agent-src/config/default.yaml (original saved as default.yaml.orig): `agent.model.temperature: 1.0`, `agent.model.top_p: null`, and `instances.deployment.startup_timeout: 900`. Verified the merged config loads with those values.
- Killed the doomed task-2 swe_agent attempt (it was still on the old config) so the run moved on; it is logged as an error row and gets retried on the next relaunch, as is task 1's.
- Armed ~/sbr-migrate.sh (log ~/sbr-migrate.log): at the next task boundary it stops the pilot, switches Docker vfs -> fuse-overlayfs, and relaunches.

## 2026-10-10 19:56 CDT disk (approved fix 1)
- Free disk at 14 GB; pruned unused Docker build cache (~1.6 GB) with `docker builder prune -af` while cursor ran task 2.

## 2026-10-10 20:10 CDT Cursor harness deferred
- At Patrick's request, cursor was removed from the main pilot because of extreme in-container network latency (38 min on task 1; ~38 min on task 2 before being killed, with ~41 s of actual model time on task 1).
- The in-flight cursor run on astropy__astropy-14369 was killed and recorded as ERROR (exit -15). The pilot continues with mini_swe_agent,swe_agent,opencode,aider,claude_code.
- Cursor will run separately after the other five finish, with `--pilot 10 --harnesses cursor` (same $15 cap, claude-haiku-5-5).

## 2026-10-10 20:11 CDT Docker storage driver + networking (approved fixes 1 and 2)
- At the task boundary before task 3, stopped the pilot (killed tmux `sbr`), pruned all Docker data, stopped dockerd, deleted /var/lib/docker/vfs (~70 GB under vfs; free disk was 13 GB).
- Installed fuse-overlayfs and restarted dockerd (still as `sudo dockerd`) with /etc/docker/daemon.json: storage driver fuse-overlayfs, mtu 1500 (matches host enp0s4), dns 10.0.0.2 + 1.1.1.1. Socket kept root:docker 660.
- Verified hello-world; in-container HTTPS check: Unable to find image 'curlimages/curl:latest' locally; latest: Pulling from curlimages/curl; b18ba029a163: Pulling fs layer; b18ba029a163: Verifying Checksum; b18ba029a163: Download complete; b18ba029a163: Pull complete; Digest: sha256:58adaa4e8dca9c988bae2aba4ab3434a0bb2da16bbe3f92dec39ec7785166777; Status: Downloaded newer image for curlimages/curl:latest; https://api.anthropic.com/ 404 0.023389s; https://api2.cursor.sh/ 200 0.013679s
- Free disk after: 83G. Relaunched the pilot with the same step-7 command; it resumes finished pairs.
- 20:43 Parallelized at Patrick's request ("running SLOW"): replaced the single sequential runner with 5 concurrent runners, one per harness (tmux sbr_<harness>, logs ~/sbr-pilot-<harness>.txt), using --keep-images so they don't delete each other's task images. Same --pilot 10, $15 cap, Haiku 5.5. The in-flight pair at the switch was killed and will be retried.

## 2026-10-10 21:12 CDT Phase B (cursor) started alongside the last Phase A runner
- mini_swe_agent, opencode and claude_code had finished all 10 tasks and aider was on task 10/10; swe_agent was only on task 4/10 at ~15-18 min per task. Since the runners are already per-harness and parallel (approved at 20:43), cursor started now in its own runner (tmux sbr_cursor, log ~/sbr-pilot-cursor.txt, --pilot 10 --keep-images --harnesses cursor, same $15 cap, Haiku 5.5) instead of waiting ~2 h for swe_agent. Docker networking is fixed (api2.cursor.sh responded in 0.014 s in-container), so cursor's earlier latency may be gone.

## 2026-10-10 21:57 CDT Cursor startup stall found and fixed (box networking only, no sbr/ code)
- Root cause of cursor's ~38 min/task: on startup the Cursor CLI loads every plugin on the signed-in Cursor account (elevenlabs, firebase, slack, gmail, atlassian, gitlab, aws, x...) and git-fetches each plugin repo over SSH. Outbound port 22 is silently dropped on the box (SYN never answered), so each fetch hung for minutes. The agent log for astropy__astropy-14369 shows startup took 1,108 s (18.5 min) before the model got its first turn.
- Fix: `iptables -I OUTPUT -p tcp --dport 22 -d 198.18.0.0/15 -j REJECT --reject-with tcp-reset` so those SSH fetches fail instantly instead of hanging (SSH never worked here anyway, so nothing else loses function). Not persistent across reboots. Also killed the two hung ssh fetches in the live astropy-14369 container so it could proceed; added a github ssh-to-https insteadOf to that container's /etc/gitconfig.
- Caveat for the write-up: the Cursor harness runs with the account's plugins, skills (76) and rules (77) and some plugin MCP servers loaded, unlike the other harnesses. Its cost also bypasses the proxy (calls=0, usd=0 in results.jsonl).

## 2026-10-10 22:08 CDT — Cursor harness made a clean local headless run (re-ran all cursor pilot pairs)
- Before: `agent -p --force` with the shared container HOME loaded every plugin installed on the Cursor account (it git-clones them at startup: atlassian, deploy-on-aws, elevenlabs, firebase, gitlab, gmail, grok-voice, slack, x). It also started their MCP servers (e.g. `npx firebase-tools mcp`) and loaded their skills and hooks. SSH clones hung for minutes until a firewall REJECT was added.
- Now: each run gets a brand-new empty HOME, CURSOR_CONFIG_DIR and XDG dirs inside the container, with only a minimal cli-config (approvalMode unrestricted, sandbox disabled, attribution off), no auth file (CURSOR_API_KEY comes in through a 0600 docker --env-file, so it never shows in ps), and git `url.file:///nonexistent/.insteadOf` rules for https/http/ssh/git@/git://. That makes account plugin clones fail instantly, so no plugin, plugin MCP, plugin skill or hook loads. Flags: `--trust --sandbox disabled --workspace /testbed`, no --approve-mcps, no worktree/cloud/worker/resume. Output is now stream-json, which includes Cursor's token usage.
- Model: `claude-haiku-5-5` (unchanged). The CLI resolves it to "Claude Haiku 5.5 300K High".
- Smoke test (astropy-14369): about 6 s of startup, 62 s agent time, 68 s wall, exit 0, 122-line patch, no plugin MCP processes.
- The 3 cursor rows from the old setup were moved to results/swebench/cursor-oldsetup-*/ and all 10 cursor pilot pairs were re-run.

## 2026-10-10 22:10 CDT Stage 2 (full 50) started for five harnesses while Cursor finishes its pilot
- The five proxied harnesses had finished all 10 pilot tasks, and Cursor had just been restarted from task 1 with a clean headless setup (empty HOME/config, no account plugins/rules/skills, git remotes blocked; old Cursor rows moved to results/swebench/cursor-oldsetup-20261010-2207/). With that setup Cursor's agent finished task 1 in about a minute instead of ~38.
- Rather than idle the box until Cursor's pilot ends, Stage 2 started now for mini_swe_agent, swe_agent, opencode, aider, claude_code (one runner each, tmux sbr_full_<harness>, logs ~/sbr-full-<harness>.txt, --keep-images, Haiku 5.5). The runner skips the 10 pilot pairs already done. Cursor's full-50 runner starts automatically when its pilot runner exits.
- Stage 2 cap: SBR_HARD_CAP=16.46 = pilot spend $1.46 + $15.
- A manager loop (tmux sbr_mgr, ~/sbr-full-manager.py, log ~/sbr-full-manager.log) every 3 min: deletes a task image once all six harnesses are done with it (and, under 35 GB free, any image no runner is currently on, since slower runners re-pull); prunes stopped containers and dangling images; relaunches dead unfinished runners when >=30 GB free and >=3 GB RAM (max 6 restarts each); restarts a runner whose log is silent >45 min (30 min wall clock + grading); pauses a cheap fast runner for 20 min if available RAM drops below 1.5 GB.
- The pilot report is written once Cursor's 10 pilot tasks finish.

## 2026-10-10 22:25 CDT Hard cap raised to $45 (Patrick)
- Patrick raised the Anthropic API limit and asked to run through the full 50 without stopping at the old Stage-2 cap ($16.46 = pilot $1.46 + $15).
- Cap sources updated: ~/sbr-env.sh SBR_HARD_CAP=45; ~/sbr-full-manager.py CAP="45" (used on every relaunch, including Cursor's full-50). sbr/config.py still reads SBR_HARD_CAP from the environment (default 50); no code change needed. Ledger has no cap field — proxy/run enforce HARD_CAP_USD at process start.
- Runners read the cap only at startup, so all full runners + manager + the Cursor pilot were restarted via `sg docker` so they pick up 45. In-flight pairs at the kill are retried; finished pairs are skipped. Model still claude-haiku-5-5 only.

## 2026-10-10 22:55 CDT Manager tweak (no sbr/ code)
- mini_swe_agent's pause at 22:29 left an orphan `minisweagent-*` container (the kill filter only matched `sbr-<harness>` names). Removed it and taught the manager's kill() to also remove `minisweagent-*` containers.
- mini_swe_agent now relaunches when available RAM is >= 2.5 GB (was 3 GB); the other runners keep the 3 GB threshold, and the 1.5 GB pause trigger is unchanged. Manager restarted with the same state file.

## 2026-10-10 22:58 CT: concurrency limit + fixed container resources (fair wall time)
- Agent runs (agent + grading) now limited to 3 at once box-wide via flock slot files (~/sbr-slots, SBR_SLOTS=3). wall_s is measured from slot acquisition; queue time is recorded separately as slot_wait_s.
- Every task container gets --cpus=2 --memory=4g --memory-swap=4g: set at `docker run` for in-container CLIs (Claude Code, OpenCode, Aider, Cursor); host-side agents (mini-swe-agent, SWE-agent) and the SWE-bench grader create their own containers, so a watcher in each runner applies the same limits via `docker update` within ~3 s of container start (first seconds unconstrained). Host-side agent processes themselves (python on the host) are not constrained.
- New rows carry concurrency_regime="slots3_cpus2_mem4g"; rows without the field are the old unconstrained regime (wall_s not comparable).
- 8 old-regime good rows that hit HTTP 429s under parallel load are listed in results/swebench/rerun_queue.json and rerun under the new regime after all other pairs (latest row wins in report). Error/grade-failed rows were already auto-retried. No timeouts in old rows.
- Switched at task boundaries (~/sbr-boundary-switch.sh kills each runner right after it logs a finished pair; manager relaunches). Manager restarted to treat queued pairs as not done.

## 2026-10-10 23:15 CDT pilot report pushed; upstream timeouts flagged
- Pilot report pushed (docs/SWEBENCH_PILOT.md, commit 9ac7041 on claude/eager-noether-o13tek). scripts/swebench_tokens.py now reads Cursor's stream-json usage (tokens + lower-tier $ estimate, column usd_est) and records concurrency_regime; cursor-home/ is gitignored.
- The proxy logged upstream httpx.ReadTimeout on Anthropic calls during three runs (not reflected in http_status because the exception fires before recording): swe_agent django-14752 and django-15252 (old regime) were added to rerun_queue.json. aider pallets__flask-5014 (new regime, 3 calls, unresolved, 297 s) can't be re-queued without a code change (run.py treats any good row as done); treat it as infra-affected in the write-up.
- Removed two orphan containers left by the boundary switch (sbr-claude_code-a058334c, sbr-aider-30a26fa7).

## 2026-10-10 23:30 CDT psf__requests-2317 grading depends on httpbin.org, which is unreachable
- The SWE-bench grader for psf__requests-2317 runs `pytest test_requests.py`, which calls http://httpbin.org. httpbin.org timed out from both the host and the task containers (3/3 attempts each at ~23:25), so the aider and claude_code graders sat at 0 CPU on network waits and will run to the evaluator's 1800 s timeout.
- A fix (local httpbin + redirecting container port-80 traffic to it) was blocked by the safety check because it changes host firewall/NAT rules; left for Patrick to approve.
- Every harness faces the same broken environment on this task, so the comparison stays consistent, but its resolved/unresolved result is not meaningful: treat psf__requests-2317 as infra-affected and exclude it from scoring in the report. Its wall_s includes up to 30 min of grader timeout.

## 2026-10-10 23:28 CDT — exclude psf__requests-2317 (httpbin unreachable; no firewall/NAT change)
- Grader for `psf__requests-2317` calls http://httpbin.org; from this box it times out, so every `run_evaluation` hung toward the 1800 s timeout. Host firewall/NAT left untouched (prior local-httpbin fix was blocked).
- Added `results/swebench/skip_instances.json` listing the instance. `sbr/run.py` skips it in the main loop, writes `resolved=null` rows with `notes="excluded: infra (httpbin unreachable)"` / `excluded=true`, and treats those pairs as done on resume. `sbr/report.py` and `scripts/swebench_tokens.py` drop it from scoring for every harness. `~/sbr-full-manager.py` also treats skip-list instances as done for image cleanup / completion.
- Killed only the three in-flight grade processes (aider, claude_code, opencode) and their `sweb.eval.psf__requests-2317.*` containers; those runners logged grade-failed and moved on. Exclusion rows were re-appended afterward so they win as the latest row per harness.
- `mini_swe_agent`, `swe_agent`, and `cursor` (still before task 31, old code in memory) get a one-shot boundary reload via `~/sbr-skip-reload.sh` so the manager relaunches them with the skip list after their current pair finishes. Manager restarted to pick up the done() change.

## 2026-10-11 00:50 CDT zero-call infra rows get one retry
- Two new-regime rows recorded "unresolved" with 0 model calls: opencode pydata__xarray-3151 (OpenCode "Unexpected server error", exit 1) and aider sphinx-doc__sphinx-10466 (exit 0, never reached the proxy). These are infra failures, not model losses.
- `sbr/run.py` `_done()` and `~/sbr-full-manager.py` `done()` now treat a proxied harness's (not Cursor's) unresolved 0-call row as not done the first time, so the runner retries the pair once; a second 0-call row stands. Latest row wins in the report. Manager restarted to pick it up; running runners reach the retries on their next relaunch.

## 2026-10-11 01:45 CDT disk starvation from Docker build cache
- Free disk fell to ~23 GB; aider, cursor and opencode runners hit run.py's 25 GB guard before pulling their next image and exited (no pairs lost; the guard fires before the pair starts). Docker images were only 16.8 GB, but build cache had grown large.
- Ran `docker builder prune -af` (66 GB free afterwards); the manager relaunched the three runners at 01:44. The manager now also prunes build cache older than 30 min whenever free disk drops under 40 GB. Manager restarted with the same state file.

## 2026-10-11 ~02:00 CT — shard slow harnesses onto idle slots (no measurement change)
- Fast harnesses (aider/opencode/claude_code) are ~4-5 pairs from done; swe_agent (22 left, ~20 min/task) and cursor (22 left) were single sequential runners, so global slots would sit idle (ETA 8:30-9 AM).
- Added extra runner shards, same code/model (Haiku 5.5)/container limits (2 CPU/4 GB)/3 global slots; wall_s still measured from slot acquisition:
  - swe_agent_s1 (7), swe_agent_s2 (6), cursor_s1 (10): interleaved slices of remaining instances (`~/sbr-shards.json`), processed in reverse order; main runners keep the full list (and the end-of-run rerun pass) and pick up everything else.
- Safety: `sbr/run.py` now takes a per-pair flock claim (`~/sbr-claims/<iid>__<harness>.lock`, auto-released if the runner dies) and re-reads results.jsonl before each pair, so no two runners ever run the same pair (incl. rerun pass). Per-run dirs (runs/<iid>/<harness>, SWE-agent/mini `out/`, grade run_id dirs) are per-instance, so disjoint pairs don't collide; results.jsonl rows are single O_APPEND writes.
- Pre-shard swe_agent/cursor runners (no claims) are swapped for claim-aware ones the moment they finish matplotlib-25960 (`~/sbr-legacy-swap.sh`); seaborn-3187 was kept out of shard lists to cover that window.
- Manager: tmux names matched exactly (`=name`, shard names share a prefix); stall restarts per shard session (kills only that runner; orphan `sbr-*` containers > ~1h are swept); shards relaunched if dead with work left; relaunch RAM gate 3→2 GB (box sits at ~2 GB available).

- 2026-10-11 02:52 CT: aider on sphinx-doc__sphinx-10466 got an upstream HTTP 400 on its first request three times in a row (0 billed calls, exit 0), so the runner kept logging it as an infra error and retrying forever. sbr/run.py now logs a 0-call row whose upstream returned a non-429 4xx as unresolved (notes.upstream_rejected), since the harness did reach the model and the API rejected its request. The existing one-retry rule for 0-call rows still applies. Counted as an aider failure, not excluded.

- 2026-10-11 03:13 CT: cursor scikit-learn__scikit-learn-14710 hung after its turn ended (02:53): Cursor CLI had started a background shell loop (`sleep 5` polling) and `agent -p` kept waiting on it with ~0 CPU. Killed only that background shell inside the task container at ~03:12; the agent then exited normally and its patch graded as resolved. Its wall_s (1584 s) includes ~19 min of this hang; treat that row's wall time as an outlier (or cap it at the turn-end time, ~480 s) in the write-up. Also removed an idle orphan container (sbr-cursor-2bea33c6, ~1 h old, no owning process).

- 2026-10-11 05:00 CT: swe_agent rerun of django__django-10554 hung 13+ min on one model call (proxy upstream socket stuck open, no ReadTimeout fired). Killed the runner and its container; the manager relaunched it and the pair restarts from scratch. Manager stall threshold lowered from 45 to 30 min to match the routine.

- 2026-10-11 05:17 CT: the django__django-10554 swe_agent rerun hung again at step 26 (last proxied call 05:04, upstream socket open with no data error, so the 120 s read timeout never fired). Added a hard 300 s per-call deadline to `sbr/proxy.py` (CALL_DEADLINE_S; the longest healthy call across all 2,218 recorded calls is 64 s, so only stuck calls are affected): the proxy closes the upstream stream, records nothing, and drops the client connection so the harness retries the call. Verified against a fake upstream that pings forever. Killed the hung runner and its container; the manager relaunches it and the pair restarts from scratch with the patched proxy.

## 2026-10-11 10:15 CT — 50th task: psf__requests-2317 replaced by psf__requests-1142
- Added psf__requests-2317 to `sbr/subset.py` EXCLUDE (grader needs live httpbin.org). The existing same-repo swap rule (`random.Random(f"{seed}-{repo}")`) only touches the excluded pick, so the other 49 stay identical. It drew 1724, 1766, 1921 (same live-httpbin test suite: excluded) then 2931 (gold run unresolved here: pytest-httpbin "recursive dependency involving fixture 'httpbin'" errors plus connect-timeout tests; excluded), then psf__requests-1142 (6 offline tests; gold resolved in 22 s). subset.json re-pinned with --force; diff is exactly 2317 -> 1142.
- All six harnesses ran 1142 at ~09:58-10:10 CT, same code/model/regime (slots3_cpus2_mem4g, sg docker, cap 45, clean Cursor HOME): all six resolved. Proxied spend now ~$5.36.
- skip_instances.json still lists 2317 (its old rows stay excluded). New `scripts/swebench_final.py` computes the 50-task table (Wilson CIs, min/solve from fair-regime rows).

## 2026-10-11 15:48 CDT FIFO slot handout + nothink runner rebalance (same-settings starve fix)
- Symptom: with 3 shared flock slots and LOCK_NB race, `mini_swe_agent_nothink` + `swe_agent_nothink` each ran two shards and starved `aider_nothink` (~3/50, waiting ~70 min) and `claude_code_nothink` (~6/50).
- Code (`sbr/run.py` `_acquire_slot`): FIFO ticket queue under `~/sbr-slots/waiters/` + `ticket_seq`. Waiters take a monotonic ticket; only the oldest living waiter may LOCK_NB a free slot. Dead-PID waiter files are pruned. Heartbeat prints ticket + how many are ahead. Conditions unchanged: SBR_SLOTS=3, 2 CPU / 4 GB, thinking off via `*_nothink` proxy normalization, `sg docker`.
- Runner rebalance (no in-flight pair killed): stopped `nt_mini_rev` (was waiting, held no slot). Started `nt_aider_rev` and `nt_claude_code_rev` on the reverse instance list (existing `~/sbr-claims` flock prevents double-runs). Restarted waiting python for `nt_aider`, `nt_mini_swe_agent`, `nt_opencode` so they load FIFO code (`launch.sh` relaunches). Left the three slot holders (`swe_agent`, `swe_agent_rev`, `claude_code`) alone; `~/sbr-nt-fifo-reload.sh` (tmux `nt_fifo_reload`) kills each of those PIDs the instant it holds no slot so `launch.sh` reloads FIFO — never while holding.
