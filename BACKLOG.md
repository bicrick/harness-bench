# Backlog: Same model, better harness (deadline 11:30 AM CT Sat Oct 10)

Haiku 5.5 only · $50 hard cap (`python -m cshape spend`) · priority order: A → T → B/C → D.
Routine pickup: start with the first unchecked item in the current clock phase.

## TOP PRIORITY (alongside the harness)
- [x] Every run logs to results/*.jsonl: config, task, seed, pass, missed callers, diff, tokens (input/cache/output), cost, wall time, tool calls, plus a full transcript in results/transcripts/. Cumulative spend goes to results/ledger.json.
- [x] `make figures` rebuilds results/summary.csv and figures/*.png from the raw logs.
- [x] Automatic `failure_category` tag per run (missed_caller, broken_import, apply_failure, no_edit, context_overflow, test_failure_other, error).
- [x] Excerpt extractor saves to results/excerpts/.
- [x] `results/article_numbers.json` holds every number the article uses. Consistent figure style. Pareto chart. Per-arm figures.
- [x] docs/ARTICLE_SPEC.md and docs/HYPOTHESES.md (pre-registered before the main runs).

## Phase 1: build (until ~5:00 AM CT)
- [x] Verify pricing and the model id `claude-haiku-5-5`.
- [x] Harness: cost ledger plus hard cap, ast skeleton L0–L3, SEARCH/REPLACE applier, grader with missed callers, one-command CLI.
- [x] 19 verified tasks across tinydb, itsdangerous and marshmallow.
- [x] Arm A strategies: full, touched, skel_L0–L3, skel_retrieval, agentic.
- [x] Pilot: 4 tasks × 8 strategies × 1 seed. Fix the bugs it turns up (the race in the base checkout is fixed; the src-layout skeleton is fixed).
- [x] Arm T: structured tools (find_references, rename_symbol, replace-all edit) as the strategy `agentic_tools`.
- [x] Arm B: compaction variants on agentic (24k budget; summary at 50%/90%, observation masking).
- [x] Arm C: refactor skill file and AGENTS.md doc variants.
- [x] `cshape report`: aggregate tables (pass, CI, missed, cost/solve) and charts written to results/.

## Phase 2: runs (started early, ~1:45 AM)
- [ ] **IN PROGRESS** main run: all 14 strategies (arms A/T/B/C) × 19 tasks × 3 seeds → results/main.jsonl. To resume, rerun the same command; it skips finished runs and re-runs errored ones:
  `python -m cshape run --strategies full,touched,skel_L0,skel_L1,skel_L2,skel_L3,skel_retrieval,agentic,agentic_tools,agentic_c50,agentic_c90,agentic_mask,agentic_skill,agentic_agentsmd --seeds 3 --workers 6 --out results/main.jsonl`
- Note: the org rate limit is 500k input tokens/min on Haiku 5.5, and marshmallow full-repo prompts are about 135k. llm.call retries with backoff on 429.
- [ ] If agentic configs hit the ceiling (~100%), add a hard tier of tasks (signature changes with many call sites) so the configs can be told apart.
- [ ] **FINAL COMBINED** config (rule in EXPERIMENT_PLAN; `python -m cshape.combine` then `python -m cshape run --strategies full,combined --seeds 5 --workers 6 --out results/final.jsonl`): the best option from each arm stacked, 19 tasks × ≥5 seeds. Reserve ~$10 for it, and run it last.
- [ ] Arm A: 19 × 8 × 3 seeds.
- [x] Arm T: 19 × 2 × 3.
- [ ] Arms B and C: 19 × (3 + 2) × 3.
- [ ] Arm D, only if budget and time allow.
- [ ] Commit results JSONL after each arm.

- [x] Arm E (real harnesses), 88 runs done: `python -m cshape run --strategies ext_claude_code,ext_aider,ext_mini_swe_agent,ext_opencode --seeds 1 --workers 4 --out results/arm_e.jsonl`. It is resumable, about $0.01/run, and costs are captured by cshape/proxy.py.
- [x] 3 hard tasks added (tinydb-h01 ambiguous `search`, marshmallow-h01 ambiguous `get_value`, marshmallow-h02 `load_default`), for 22 tasks total. After main finishes, re-run the main command to add the hard tasks (resume adds only the missing runs).
- [x] Add an arm E figure to report.py (real harnesses vs naive vs best).
- Budget plan: main run about $8, arm E about $1–3, final combined config ≤$10 (reserved), with the rest as slack under the $50 cap.

- [ ] **IN PROGRESS** Arm B_tight: the 24k budget rarely triggered compaction (0.1–0.3 compactions/run), so the variants are re-run at a 12k budget: `--strategies agentic_c50_tight,agentic_c90_tight,agentic_mask_tight --seeds 3 --out results/main.jsonl`. Do NOT start two resumable runs on the same file at once; the resume step rewrites the file.
- Early read (n≈25/config): agentic configs are near the ceiling (92–100%); full single-shot is 88% at about $0.056/solve vs agentic+structured tools at 96% and about $0.001/solve. The hard tasks are needed to separate the configs.

- [ ] **IN PROGRESS** Hard-tier tasks × all main strategies × 3 seeds → results/hard.jsonl (report merges it into main).

## Phase 3: write-up (~8:00–10:00 AM)
- [ ] Headline number, tables, charts, failure examples, following the outline in EXPERIMENT_PLAN.
- [ ] Draft at docs/CASE_STUDY.md.

## Phase 4: polish and publish (~10:00–11:30 AM)
- [ ] Check every number against results/.
- [ ] Publish on bicrick.com (needs Patrick: site access or approval) and decide on repo visibility.

## Later / notes
- SWE-bench Verified: feasibility note in EXPERIMENT_PLAN (needs Docker; not run).
- Resolve [verify] items in PRIOR_WORK.md.
