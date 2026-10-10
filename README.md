# context-shaping

A case study on **context window shaping** in coding-agent harnesses: how tools like Claude Code, Cursor, Aider, Codex CLI, Cline, OpenHands, SWE-agent and Gemini CLI decide what goes into the model's context, and a controlled experiment measuring how those choices affect a cheap model on **multi-file refactors**.

The thesis: we are the harness, not the model. Holding the model fixed (a cheap Haiku-class model), how much does the *layout and selection of context* change pass rate, missed callers, and cost per success?

**Core question:** how does harness-side context management change outcomes on multi-file refactors when the model is cheap and held fixed?

## Timeline (3 days, done Mon Oct 12, 2026)
- **Fri/Sat: research** (done). See `docs/research/` and `SUMMARY.md` / `PRIOR_WORK.md`.
- **Sat: build** the harness, 20 refactor tasks, graders, and a pilot run.
- **Sun: run** the experiments.
- **Mon: write** a comprehensive case study and publish it on bicrick.com.

## Experiment arms (full plan: `docs/EXPERIMENT_PLAN.md`)
- **A. Layout:** full repo, touched files only, a skeleton ladder (tree → +imports → +signatures → +docstrings → full), skeleton + on-demand retrieval, and agentic grep/read only.
- **B. Compaction:** none, summarize at 50%, summarize at 90%, and drop old tool outputs.
- **C. Procedural context:** no skill, a refactor skill file, and a repo conventions doc.
- **D. Placement:** key file at the start vs the end of the prompt.

## Metrics
Pass rate, missed callers, diff size, tokens (including cache), cost per solved task (with prompt caching), and wall time. Estimated budget is about $100, with a hard cap at $150.

See `BACKLOG.md` for next steps.
