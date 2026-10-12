# Same model, better harness: experiment plan

**Question:** with Claude Haiku 5.5 held fixed, how much can harness-side context management and tool design raise success on multi-file refactors, and at what cost per solved task?

**Constraints:** Haiku 5.5 only (`claude-haiku-5-5`). **$50 hard cap.** Done by **11:30 AM CT, Sat Oct 10, 2026**.

## Model and prices (verified 2026-10-10, https://docs.anthropic.com/en/docs/about-claude/pricing)
| Prompt size | Input | 5m cache write | Cache read | Output |
|---|---|---|---|---|
| ≤100k tokens | $0.10/M | $0.125/M | $0.01/M | $0.50/M |
| >100k tokens | $0.50/M | $0.625/M | $0.05/M | $2.50/M |

Prompt length counts cache reads and writes. Haiku 5.5 always uses extended thinking, and thinking tokens are billed as output (https://docs.anthropic.com/en/docs/claude-code/costs). All arms use automatic prompt caching.

## Tasks (19, all verified)
Hand-made refactors on 3 pinned pure-Python repos, each with a fast test suite (under 2s):
- tinydb, 7 tasks
- itsdangerous, 5 tasks
- marshmallow, 7 tasks; its full repo is about 135k tokens, which goes over the 100k price tier

The mix is class/function/method renames, a signature change, function moves to a new module, and a module rename. Every task has a reference diff. `python -m cshape verify` checks that each reference passes the grader and that the unmodified repo fails it.

**Grader** (all three must hold):
1. The repo's tests pass.
2. No leftover references match the task's `absent` regexes. Each leftover counts as a **missed caller**.
3. A task-specific Python check passes, e.g. the new name exists and the old one is gone.

## Arms, in priority order
1. **Naive baseline vs context layout (arm A)**, run first.
   - Single-shot, SEARCH/REPLACE output: `full` (whole repo, the naive baseline), `touched` (oracle files).
   - Skeleton ladder, two-step (the model picks files from the skeleton, then edits): `skel_L0` tree → `skel_L1` +imports/imported-by → `skel_L2` +signatures → `skel_L3` +docstrings.
   - Agentic loop with list/grep/read/edit/run_tests, 25 steps max: `agentic` (raw tools), `skel_retrieval` (L2 skeleton plus tools).
2. **Tool design (arm T):** raw grep/read/edit vs structured tools (`find_references` with AST/word-boundary matching split into definitions, imports, calls and strings; `rename_symbol` with a preview; `edit` that does replace-all with match counts). The context is the same in both.
3. **Compaction (arm B)** and **procedural context (arm C)**.
   - B: no compaction vs summarize at 50% vs summarize at 90% of an artificial 24k budget vs drop old tool outputs.
   - C: no skill vs a refactor skill file vs an AGENTS.md-style conventions doc.
4. **Placement (arm D), only if budget remains:** key file at the start vs the end of the full-repo prompt.

## Metrics
- Pass rate, with Wilson 95% CI.
- Missed callers.
- Diff size (files, lines added and removed).
- Tokens: input, cache write, cache read, output.
- Cost in USD from list prices, and **cost per solved task** = total cost / passes.
- Wall time, steps and tool calls.
- For skeleton arms, file-selection recall against the oracle.

## Budget
The pilot showed about **$0.002–0.007 per run** for the ≤100k-token arms. Full-repo marshmallow runs cost more, about $0.07, because they go over 100k tokens. Estimate:
- Arm A, 19 tasks × 8 strategies × 3 seeds = 456 runs, about $5.
- Arms T, B and C, each about 19 × 3–4 configurations × 3 seeds, about $5–10 total.

The whole study should land **under $20**, well inside the $50 cap. The harness refuses new API calls once the ledger reaches $50.

## SWE-bench Verified: feasibility note only (not run)
- Needs Docker and per-instance environment images from the official `swebench` harness. **Docker is not installed on the box** (8 CPU, 15 GB RAM, about 94 GB free disk). Images run to several GB each, so a 500-task run is heavy on this machine; a 50-task subset is realistic.
- Cost per task on Haiku 5.5 is a rough estimate from our agentic runs: 0.1–1M prompt tokens, mostly cached, comes to about $0.01–0.10 per task. That is about $5–50 for the full 500, or $1–5 for a 50-task subset.
- Verdict: feasible later as a validation step. It is out of scope for today's deadline.

## Write-up outline (bicrick.com)
1. **Headline number:** best harness vs naive baseline, as pass-rate lift and change in cost per solve, both on Haiku 5.5.
2. **Why the harness matters:** context rot, lost in the middle, and LongCodeBench, citing `PRIOR_WORK.md`.
3. **How today's tools shape context:** the table from `SUMMARY.md`.
4. **Setup:** tasks, grader, arms, threats to validity.
5. **Results:** arm A ladder chart, tool design, compaction and skills.
6. **Failure analysis:** missed callers, apply failures, wrong file selection.
7. **What I'd put in a harness.**
8. **Limits, the SWE-bench next step, reproduction.**

## FINAL COMBINED config: selection rule (fixed before the final run)
`python -m cshape.combine` reads the main-run results (all main + hard-tier runs). For each arm (layout, tools, compaction, procedural) it picks the option with the highest pass rate, breaking exact ties by the lower cost per solved task. It writes `results/combined_choice.json`, and the `combined` strategy stacks those choices. The final run is `combined` and `full` (the naive baseline) on all tasks (25 after the 2:50 AM hard-tier addition) × 5 seeds, written to `results/final.jsonl`. Its budget is ≤$10; most of it goes to `full`, because marshmallow full-repo prompts exceed 100k tokens.
