# Article spec

**Title:** Same model, better harness: how much can context and tools lift Haiku 5.5 on multi-file refactors?
**Venue:** bicrick.com. **Due:** 11:30 AM CT, Sat Oct 10, 2026.

## Structure
1. **Headline chart:** naive baseline (`full`, single-shot) vs the best combined harness, showing pass rate (with CI) and cost per solved task. Also state it as one sentence: "+X pp, $Y → $Z per solve".
2. **Setup and pre-registered hypotheses:** tasks, grader, model, prices. The hypotheses come from `docs/HYPOTHESES.md`, which is committed before the main runs.
3. **One finding per arm, each with one figure:**
   - Skeleton ladder: pass rate and cost by level L0 → L3 → full.
   - Tool design: raw grep/edit vs structured find_references/rename.
   - Compaction: none / summarize at 50% / summarize at 90% / drop old tool outputs.
   - Skills / AGENTS.md: none / skill file / conventions doc.
4. **Pareto frontier:** cost per solve vs pass rate for every config, with the frontier highlighted.
5. **Failure taxonomy:** each failed run gets an automatic tag (missed_caller, broken_import, wrong_edit/apply_failure, gave_up/no_edit, context_overflow, test_failure_other, error), with counts per config and 2–3 short real transcript excerpts.
6. **Comparison with real tools:** how this maps to what Claude Code, Cursor, Aider, Codex CLI and Gemini CLI do (from `docs/research/`).
7. **Limitations and what I'd do next:** SWE-bench Verified subset, task diversity, and the RL-environment angle (tasks plus graders as an environment).
8. **Reproduce:** one command.

## Requirements this puts on the harness and plan
- Each run gets a failure tag automatically (`failure_category` in the JSONL).
- An excerpt extractor saves short transcript snippets for the failure examples.
- **FINAL COMBINED config:** the best option from each arm stacked into one config, run with ≥5 seeds × 19 tasks so the CIs are tight. **Reserve ~$10 of the $50 for it.**
- One consistent figure style across all charts (shared palette and fonts in `cshape/report.py`).
- **Every number in the article comes from `results/`.** `make figures` writes `results/summary.csv`, `results/article_numbers.json`, and the figures. The article cites those files; no stats are typed by hand.
