# Backlog: Same model, better harness (deadline 11:30 AM CT Sat Oct 10)

Haiku 5.5 only · $50 hard cap (`python -m cshape spend`) · priority order: A → T → B/C → D.
Routine pickup: start with the first unchecked item in the current clock phase.

## TOP PRIORITY (alongside the harness)
- [x] Every run logs to results/*.jsonl: config, task, seed, pass, missed callers, diff, tokens (input/cache/output), cost, wall time, tool calls, plus a full transcript in results/transcripts/. Cumulative spend goes to results/ledger.json.
- [x] `make figures` rebuilds results/summary.csv and figures/*.png from the raw logs.
- [ ] Automatic `failure_category` tag per run (missed_caller, broken_import, apply_failure, no_edit, context_overflow, test_failure_other, error).
- [ ] Excerpt extractor saves to results/excerpts/.
- [ ] `results/article_numbers.json` holds every number the article uses. Consistent figure style. Pareto chart. Per-arm figures.
- [x] docs/ARTICLE_SPEC.md and docs/HYPOTHESES.md (pre-registered before the main runs).

## Phase 1: build (until ~5:00 AM CT)
- [x] Verify pricing and the model id `claude-haiku-5-5`.
- [x] Harness: cost ledger plus hard cap, ast skeleton L0–L3, SEARCH/REPLACE applier, grader with missed callers, one-command CLI.
- [x] 19 verified tasks across tinydb, itsdangerous and marshmallow.
- [x] Arm A strategies: full, touched, skel_L0–L3, skel_retrieval, agentic.
- [ ] Pilot: 4 tasks × 8 strategies × 1 seed. Fix the bugs it turns up (the race in the base checkout is fixed; the src-layout skeleton is fixed).
- [ ] Arm T: structured tools (find_references, rename_symbol, replace-all edit) as the strategy `agentic_tools`.
- [ ] Arm B: compaction variants on agentic (24k budget; summary at 50%/90%, observation masking).
- [ ] Arm C: refactor skill file and AGENTS.md doc variants.
- [ ] `cshape report`: aggregate tables (pass, CI, missed, cost/solve) and charts written to results/.

## Phase 2: runs (~5:00–8:00 AM)
- [ ] **FINAL COMBINED** config: the best option from each arm stacked, 19 tasks × ≥5 seeds. Reserve ~$10 for it, and run it last.
- [ ] Arm A: 19 × 8 × 3 seeds.
- [ ] Arm T: 19 × 2 × 3.
- [ ] Arms B and C: 19 × (3 + 2) × 3.
- [ ] Arm D, only if budget and time allow.
- [ ] Commit results JSONL after each arm.

## Phase 3: write-up (~8:00–10:00 AM)
- [ ] Headline number, tables, charts, failure examples, following the outline in EXPERIMENT_PLAN.
- [ ] Draft at docs/CASE_STUDY.md.

## Phase 4: polish and publish (~10:00–11:30 AM)
- [ ] Check every number against results/.
- [ ] Publish on bicrick.com (needs Patrick: site access or approval) and decide on repo visibility.

## Later / notes
- SWE-bench Verified: feasibility note in EXPERIMENT_PLAN (needs Docker; not run).
- Resolve [verify] items in PRIOR_WORK.md.
