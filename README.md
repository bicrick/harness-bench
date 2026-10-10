# context-shaping

A case study on **context window shaping** in coding-agent harnesses: how tools like Claude Code, Cursor, Aider, Codex CLI, Cline, OpenHands, SWE-agent and Gemini CLI decide what goes into the model's context, and a controlled experiment measuring how those choices affect a cheap model on **multi-file refactors**.

The thesis: we are the harness, not the model. Holding the model fixed (a cheap Haiku-class model), how much does the *layout and selection of context* change pass rate, missed callers, and cost per success?

## Phases
1. **Research** (now) — cited write-ups per tool in `docs/research/`, comparison in `docs/research/SUMMARY.md`, prior work and gaps in `docs/research/PRIOR_WORK.md`.
2. **Harness** — one-command eval: fixed-commit refactor tasks, pluggable context strategies, test-based grading.
3. **Experiments** — strategies: full repo, touched files only, skeleton (tree + imports + dependency graph + signatures), skeleton + retrieval, plus compaction ablations.
4. **Publish** — results tables/charts and a write-up.

## Metrics
Test pass rate, missed callers, diff size, input/output tokens, cost, wall time, cost per successful task.

See `BACKLOG.md` for next steps.
