# harness-bench

I ran one model through five coding harnesses on 50 [SWE-bench Verified](https://www.swebench.com/) bugs.

Claude Haiku 5.5, thinking off, same settings in each. The project's own tests decided whether a fix worked.

**Write-up: [bicrick.com/projects/harness-bench](https://bicrick.com/projects/harness-bench)**

![A pixel crab in a harness, swinging over a landscape. The crab is the model.](docs/media/hero.gif)

## Harnesses

- [Claude Code](https://claude.com/product/claude-code)
- [Cursor](https://cursor.com/cli), from the command line
- [OpenCode](https://opencode.ai/)
- [SWE-agent](https://swe-agent.com/)
- [mini-swe-agent](https://mini-swe-agent.com/)

## Reproduce

Linux x86_64, Docker, 60 GB free, and an Anthropic API key. Cursor also needs a Cursor key. Full steps in [swebench/README.md](swebench/README.md).

```bash
git clone https://github.com/bicrick/harness-bench && cd harness-bench
SBR_TOOLS=$HOME/sbr-tools bash swebench/setup_tools.sh
export SBR_TOOLS=$HOME/sbr-tools ANTHROPIC_API_KEY=... CURSOR_API_KEY=...
make preflight   # checks the VM, Docker, and keys; one test call
make run         # 50 bugs x 5 harnesses, resumable
make report      # results/swebench/summary.md
```

The 50 bugs are pinned in `results/swebench/subset.json`.

## Layout

```
sbr/        benchmark runner: harness adapters, logging proxy, budget, grading, report
scripts/    analysis and figures
swebench/   VM checks and tool setup
results/    raw results: results.jsonl, per-run logs, patches, and grades
docs/       methodology, deviations, analyses
figures/    charts from the earlier default-settings pass
tools/      orchestration and the dashboard used during the runs
archive/    the earlier context-shaping pilot (see archive/README.md)
```
