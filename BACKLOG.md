<!-- last session: 4:15 AM CT build sprint -->
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
- [x] (done 3:0x AM, 880 runs, 0 errors) main run: all 14 strategies (arms A/T/B/C) × 19 tasks × 3 seeds → results/main.jsonl. To resume, rerun the same command; it skips finished runs and re-runs errored ones:
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
- [x] (2:50 AM) Hard tier batch 1 early read: agentic configs still ~100% on h01/h02, so 3 more hard tasks were added and verified (reference passes, unmodified repo fails): tinydb-h02 `Table.insert`→`insert_document` (80 call sites, 8 files), marshmallow-h03 `ValidationError`→`SchemaValidationError` (468 refs, 19 files incl. examples/), itsdangerous-h01 `Serializer.loads`→`verify_and_load` (ambiguity trap: payload-serializer `loads` must survive). 25 tasks total.
- [ ] **IN PROGRESS** Hard tier batch 2: those 3 tasks × 17 strategies × 3 seeds → results/hard2.jsonl (separate file so no two resumable runs share one; resume with the same command):
  `python -m cshape run --tasks tinydb-h02-rename-table-insert,marshmallow-h03-rename-validationerror,itsdangerous-h01-rename-serializer-loads --strategies full,touched,skel_L0,skel_L1,skel_L2,skel_L3,skel_retrieval,agentic,agentic_tools,agentic_c50,agentic_c90,agentic_mask,agentic_skill,agentic_agentsmd,agentic_c50_tight,agentic_c90_tight,agentic_mask_tight --seeds 3 --workers 3 --out results/hard2.jsonl`
- [x] report.load() now merges hard.jsonl and hard2.jsonl into main and dedupes (task, strategy, seed) per group, preferring non-error rows. Needed because the B_tight run (main.jsonl) and the hard run (hard.jsonl) both cover tight strategies on the hard tasks.
- Note for FINAL COMBINED: run it only after main, B_tight, hard and hard2 finish, so combine.py sees all 25 tasks. With 25 tasks × 5 seeds, `full` costs roughly $8–10 (marshmallow full-repo prompts plus 468-edit output on h03); drop to 4 seeds if spend at that point leaves less than $12 of headroom.

- [ ] **AUTO-CHAINED (3:18 AM)** `scripts/chain_final.sh` (log: results/chain_final.log) waits until no `cshape run` process is left, does one resume pass on main/B_tight, hard and hard2, then runs `python -m cshape.combine` and the FINAL run (full vs combined, all 25 tasks, 5 seeds; 4 if headroom < $15) into results/final.jsonl, and touches results/FINAL_DONE when finished. Do NOT start the final run by hand; check `pgrep -af chain_final` first. ETA: hard2 ~4:40 AM, final ~6 AM.
- (3:16 AM) Read at $10.63 spent: on the 19 base tasks, agentic configs are 93–96%, full 82% ($0.065/solve), agentic_tools 96% ($0.0010/solve, ~65x cheaper than full). skel_L0 47%, skel_L1–L3 67–74%, skel_retrieval 95%, touched 79%. Hard batch 1 still doesn't separate the agentic configs; tinydb-h01 (ambiguous `search`) breaks every single-shot layout except skel_retrieval. The hard2 tasks (80 / 468 call sites) are the last chance to separate the agentic arms on pass rate. If they don't, the article's arm T/B/C findings should be framed on cost per solve and tokens rather than pass rate.

## Build sprint 3:41 AM CT: stall fix
- [x] **Stall found and fixed.** From ~3:31 to 3:43 AM, all 10 workers (B_tight, hard, hard2) sat on open API sockets with no ledger writes. The anthropic client had no explicit timeout (SDK default 600s × 4 retries), which is also why a few earlier rows show 1500–2100s wall times. `llm.py` now uses timeout=300s (connect 15s) and max_retries=2; the outer backoff loop retries timeouts (APITimeoutError is an APIConnectionError). Killed all three runs plus chain_final at 3:43 and restarted them in parallel (resumable; in-flight rows were lost, and their spend is in the ledger but not in the logs, so expect the ledger to run a little ahead of logged cost in integrity.json). chain_final.sh was restarted too and still auto-runs combine + FINAL once no `cshape run` is left.
- [x] **Sandbox escape fixed.** `read_file` and `edit_all` built paths as `root / path`, so a model-supplied absolute path (one B_tight run used `/root/tinydb/tinydb/table.py`) escaped the task checkout. It crashed with PermissionError (an `error` row, re-run on resume), but it could have touched files outside the sandbox. Both tools now go through `_inside()` and return "bad path: use a path relative to the repository root" to the model, as a real harness would. Only runs that used absolute paths are affected, and before the fix those were error rows.
- [x] **`output_truncated` is now tagged at the source.** run_one stores `notes.last_stop_reason` from the transcript, and categorize() tags zero-diff runs whose last stop_reason is max_tokens as `output_truncated`. report.retag() reads the note first and falls back to the transcript for older rows.
- [x] `base_checkout` is file-locked, because parallel `cshape run` starts raced on `git checkout` (the hard run died at its first restart with exit 128).
- Early hard2 read: agentic_tools solved marshmallow-h03 (468 references, 19 files) for $0.0018 in 10s, while every single-shot layout misses all 468 (output cap). Expected ETA: B_tight/hard/hard2 by ~5:00 AM, then FINAL (~$8–10) by ~6:15 AM.

## Build sprint 4:15 AM CT: API hang fix #2 (streaming)
- [x] **Stalls were still happening after the 300s timeout.** Per-row `api_s` ≈ `wall_s`, e.g. 6 calls taking 1837s and a single `full` call taking 1949s, so the time is spent inside API calls (300s timeout × SDK retries × outer retries), not in tools. At 4:15, hard2 had only 28/153 rows done and B_tight/hard2 hadn't written a row in 25 min.
- [x] `llm.call` now **streams** (`messages.stream(...).get_final_message()`) with `read=90s` (max gap between chunks) and SDK retries off. The outer loop retries 429/5xx and any transport error mid-stream, and still raises other 4xx and BudgetExceeded. Smoke-tested with a tool call through the proxy. Results don't change (same request, same parsed Message); only wall time does.
- [x] Killed B_tight, hard, hard2 and chain_final at ~4:24 and restarted them with the same commands (resumable). In-flight rows were lost, and their spend is in the ledger only.
- **Analysis note:** `wall_s`/`api_s` on rows written before ~4:25 AM include proxy/API hangs. Don't quote wall-clock time per config from those rows; use tokens, steps and cost. If time-to-solve matters for the article, use rows written after the fix or the FINAL run.

## Phase 3: write-up (~8:00–10:00 AM)
- [ ] Headline number, tables, charts, failure examples, following the outline in EXPERIMENT_PLAN.
- [ ] Draft at docs/CASE_STUDY.md.

## Phase 4: polish and publish (~10:00–11:30 AM)
- [ ] Check every number against results/.
- [ ] Publish on bicrick.com (needs Patrick: site access or approval) and decide on repo visibility.

## Later / notes
- SWE-bench Verified: feasibility note in EXPERIMENT_PLAN (needs Docker; not run).
- Resolve [verify] items in PRIOR_WORK.md.

## Data/figures check, Oct 10 03:30 CT
- Added `python -m cshape.audit` (runs first in `make figures`): checks required fields, transcripts, duplicates, and ledger reconciliation; writes `results/integrity.json`. Status OK: ledger $11.93 vs logged $11.79; the $0.14 gap is consistent with 3 runs in flight.
- Found: single-shot strategies on `marshmallow-h03-rename-validationerror` (468 references) hit the 16k output cap (`stop_reason=max_tokens`) and were tagged `no_edit`. The report now retags these as `output_truncated` from the transcript, and summary.csv has `median_missed_callers` because those 468-miss rows inflate the means (~7-9) for single-shot configs. **Build sprint:** fix `categorize()` in `cshape/__main__.py` to log `output_truncated` at the source (store the last stop_reason in notes), and the article should note this ceiling is part of why single-shot loses on high-fan-out tasks; do not quote mean missed callers for single-shot configs.
- Headline figure: fixed overlapping x labels, added value labels and an n footnote.
