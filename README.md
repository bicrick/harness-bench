# harness-bench

**Same model, five coding harnesses, 50 SWE-bench Verified bugs.**

A coding agent is two things: the model, and the harness, the program around the model that decides what goes
into its context window, which tools it gets, and when it stops. Most benchmarks compare models. This one holds
the model fixed (Claude Haiku 5.5, same settings everywhere) and changes only the harness, to see how much the
harness matters on its own.

Write-up: **https://bicrick.com/projects/context-shaping**

## Results

50 bugs from SWE-bench Verified, graded by the official SWE-bench evaluator. Same-settings run.

| | Claude Code | Cursor | OpenCode | SWE-agent | mini-swe-agent |
|---|---|---|---|---|---|
| Bugs fixed | 33/50 (66%) | 35/50 (70%) | 35/50 (70%) | 37/50 (74%) | 34/50 (68%) |
| 95% range | 52–78% | 56–81% | 56–81% | 60–84% | 54–79% |
| Tokens per fix | 471k | 393k | 230k | 251k | 105k |
| Cost per fix | $0.010 | $0.009\* | $0.006 | $0.008 | $0.004 |
| Minutes per fix | 4.0 | 4.9 | 4.6 | 9.1 | 3.9 |

\* Cursor bills through its own servers, so its traffic never passes our logging proxy. Its cost is estimated
from its own usage logs.

## Key findings

- **Accuracy is a tie.** 66–74% with heavily overlapping 95% ranges. At 50 bugs, no harness is clearly more accurate.
- **Token use is not.** Tokens per fix differ 4.5x, from 105k (mini-swe-agent) to 471k (Claude Code), for the same
  accuracy. Most of the gap is how much each harness puts in the window before the model reads any code: about 2k
  tokens and one to three tools for mini-swe-agent and SWE-agent, 11k for OpenCode, 13k for Cursor, 24k and 20 tools
  for Claude Code. That opening is resent with every request.
- **SWE-agent edges ahead by checking its work.** On the 9 bugs where the harnesses split, SWE-agent fixed 8. Its
  transcripts show it running code after editing in 98% of bugs (64–78% for the others) and revising after a failed
  check about twice as often. The edge is 2–4 bugs, so this is *consistent with* checking being the reason, not
  proof. See [docs/WHY_SWE_AGENT.md](docs/WHY_SWE_AGENT.md).

## Setup

- **Model:** Claude Haiku 5.5 for all five. Four harnesses call Anthropic's API through a logging proxy
  (`sbr/proxy.py`); Cursor uses its "Haiku 5.5 High No Thinking" option on its own servers.
- **Thinking:** off for all five.
- **Approvals:** every command auto-approved; runs are fully unattended.
- **Budget:** $0.50 per bug per harness (enforced by the proxy), 50 turns where the harness has a limit, 30 minutes wall clock.
- **Machine:** each run in its own SWE-bench task container, 2 CPU / 4 GB, 3 runs at a time.
- **Defaults:** shipped settings otherwise, no per-harness tuning. Full details in
  [docs/DEVIATIONS.md](docs/DEVIATIONS.md).

**Why no Aider:** Aider was in the first run but was dropped. It is built for a human at the keyboard and needs a
test command to check its own fixes; run unattended without one, it often stopped and asked a person to run the
tests. Its score would have measured our setup, not the harness.

## Reproduce

Needs a Linux x86_64 VM with Docker, 60+ GB free disk, and an Anthropic API key (plus a Cursor key for Cursor).
Full instructions in [swebench/README.md](swebench/README.md).

```bash
git clone https://github.com/bicrick/harness-bench && cd harness-bench
SBR_TOOLS=$HOME/sbr-tools bash swebench/setup_tools.sh
export SBR_TOOLS=$HOME/sbr-tools ANTHROPIC_API_KEY=... CURSOR_API_KEY=...
make preflight   # checks everything, one test call
make run         # 50 bugs x 5 harnesses, resumable
make report      # results/swebench/summary.md
```

The 50 bugs are pinned in `results/swebench/subset.json`.

## Layout

```
sbr/        benchmark runner: harness adapters, logging proxy, budget, grading, report
scripts/    analysis and figures (tokens, why-harnesses-differ, why-SWE-agent extraction)
swebench/   VM checks and tool setup
results/    raw results: results/swebench/results.jsonl and per-run logs, patches and grades
docs/       methodology, deviations, analyses, harness research notes
figures/    SWE-bench figures
tools/      orchestration and dashboard used during the runs
archive/    the earlier context-shaping pilot (see archive/README.md)
```
