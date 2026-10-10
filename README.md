# Same model, better harness

**How much does the harness matter?** We hold the model fixed (**Claude Haiku 5.5** only) and change only harness-side context management and tool design. Then we measure how much pass rate and cost per solved task change on **multi-file refactors**.

Headline we are after: **best harness config vs naive baseline on the same model**, reported as a pass-rate lift (percentage points) and a change in cost per solved task.

- Deadline: case study published on bicrick.com **today, Sat Oct 10, 2026, 11:30 AM CT**.
- Budget: **$50 hard cap**, enforced in `cshape/llm.py` (`CSHAPE_HARD_CAP`).
- Research: `docs/research/` (per-tool notes, `SUMMARY.md`, `PRIOR_WORK.md`).
- Plan: `docs/EXPERIMENT_PLAN.md`. Status and next steps: `BACKLOG.md`.

## Run it
```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt simplejson freezegun
export ANTHROPIC_API_KEY=...            # never commit
python -m cshape verify                 # reference solutions pass, unmodified repos fail
python -m cshape run --strategies all --tasks all --seeds 1
python -m cshape spend
```

## Layout
- `cshape/`: the harness (context builders, strategies, SEARCH/REPLACE edits, grader, cost ledger).
- `tasks/<repo>/`: pinned repo plus refactor tasks (`*.yaml`) and reference diffs.
- `results/`: JSONL per run and `ledger.json` (cumulative spend).
