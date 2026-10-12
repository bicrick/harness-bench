# SWE-bench harness comparison

One model, Claude Haiku 5.5. Six real harnesses. The same pinned 50-task subset of SWE-bench Verified.
The only thing that changes is the harness.

| harness | where it runs | cost measured by |
|---|---|---|
| mini-swe-agent | host, its own SWE-bench Docker mode | our proxy |
| SWE-agent | host, its own SWE-bench Docker mode | our proxy |
| OpenCode | inside the task container | our proxy |
| Aider | inside the task container | our proxy |
| Claude Code | inside the task container | our proxy |
| Cursor agent | inside the task container | Cursor's own usage (it bills through Cursor) |

## Fair rules

- Same issue text for the CLI harnesses. mini-swe-agent and SWE-agent use their shipped SWE-bench configs.
- Same limits: $0.50 per task per harness, enforced by the proxy (every call after that gets a 429),
  50 turns where the harness has a turn limit, 30 minutes of wall clock.
- Default settings otherwise. No tuning per harness.
- Graded by the official SWE-bench evaluator (`swebench.harness.run_evaluation`).
- A harness that never reaches the model is logged as an error and retried, not scored as unresolved.

## Running it on a Linux VM

Needs x86_64, Docker your user can run, 60+ GB free, and outbound internet.

```bash
git clone https://github.com/bicrick/harness-bench && cd harness-bench
bash swebench/check_vm.sh                         # specs, docker, network: read-only
SBR_TOOLS=$HOME/sbr-tools bash swebench/setup_tools.sh   # ~3 GB, ~5 min

export SBR_TOOLS=$HOME/sbr-tools
export ANTHROPIC_API_KEY=...                      # required
export CURSOR_API_KEY=...                         # only for the cursor harness
PY=$SBR_TOOLS/host/bin/python

$PY -m sbr.preflight                              # checks everything; one test call, < $0.001
$PY -m sbr.subset                                 # pins the 50 tasks (refuses to overwrite)
$PY -m sbr.run --harnesses gold --pilot 3         # plumbing check: gold patches must resolve, $0
$PY -m sbr.run --pilot 10                         # the pilot: 10 tasks x 6 harnesses
$PY -m sbr.report                                 # table + summary.csv/md
```

Run long jobs in `tmux`. Everything is resumable: rerun the same command and finished pairs are skipped.

Then the full run: `$PY -m sbr.run` (all 50). Knobs: `SBR_SUBSET`, `SBR_TASK_BUDGET`, `SBR_HARD_CAP`,
`SBR_CURSOR_MODEL` (if Cursor names Haiku 5.5 differently; preflight lists its models),
`SBR_DOCKER="sudo docker"` if your user isn't in the docker group.

## Outputs (`results/swebench/`)

- `results.jsonl`: one row per (task, harness): resolved, cost, calls, peak window, wall time, notes
- `runs/<task>/<harness>/calls.jsonl`: every model call: prompt size, cache read/write, output, cost
- `runs/<task>/<harness>/patch.diff`, `stdout.txt`, `stderr.txt`, `grade/`: the patch, logs, grading
- `summary.md`: resolve rate with 95% interval, $/resolve, calls, peak window, compactions, cache hit
