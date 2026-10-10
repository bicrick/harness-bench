# Backlog (3-day plan; see docs/EXPERIMENT_PLAN.md)

## Blockers (need Patrick)
- [ ] ANTHROPIC_API_KEY (and optionally OPENAI_API_KEY) in a box env file. Budget cap $150.
- [ ] Decide whether the repo goes public at publish time (Mon).

## Sat Oct 10: build
- [ ] Pick 2–3 small Python repos with fast tests and pin their commits. Check the RefactorBench license and format; it is optional.
- [ ] Write ~20 tasks (6 rename, 5 signature, 5 move, 4 extract), each with task.yaml and a reference diff, and verify each reference passes.
- [ ] Grader: apply the patch, run the tests, and count missed callers (AST + grep on old_symbols).
- [ ] Context builders: full (budget-truncated), touched files (oracle), skeleton L0–L3 (tree-sitter; reuse Aider-style tags).
- [ ] Single-shot runner (unified diff output) and agentic loop (read_file, grep, list_dir, edit, run_tests; 30-step cap).
- [ ] Compaction: none, summarize at 50%, summarize at 90%, observation masking (32k artificial budget).
- [ ] Skill injection: refactor skill file and AGENTS.md conventions doc.
- [ ] Placement variants: key file at start vs end.
- [ ] Usage/cost logger (including cache read/write), wall time, and a $ hard cap. JSONL output.
- [ ] Pilot: 3 tasks × P0 arms × 1 seed.

## Sun Oct 11: run
- [ ] P0, arm A × 20 tasks × 3 seeds.
- [ ] P1, arms B and C.
- [ ] P2, arm D. Optional second model on P0.
- [ ] Aggregate: tables, Wilson CIs, McNemar tests, charts (pass rate vs cost per solve, the skeleton ladder curve).
- [ ] Failure taxonomy from transcripts.

## Mon Oct 12: write and publish
- [ ] Draft the case study following the outline in EXPERIMENT_PLAN §7, and check numbers against results.
- [ ] Clean up the README so reproduction is one command.
- [ ] Publish on bicrick.com and draft a LinkedIn post.

## Research follow-ups (if time)
- [ ] Resolve [verify] items in PRIOR_WORK.md (SWE-bench retrieval ablation, Agentless, Complexity Trap, RefactorBench).
- [ ] Confirm Claude Code's auto-compact %, Cursor internals, and Cline thresholds.
