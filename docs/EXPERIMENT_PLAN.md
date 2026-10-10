# Experiment plan (3 days: Sat Oct 10 – Mon Oct 12, 2026)

**Core question:** with the model held fixed and cheap, how much does *harness-side context management* change outcomes on multi-file refactors?

Deliverable: a full case study published on bicrick.com on Mon Oct 12, with the repo, raw results, and charts.

## 1. Task set (~20 refactors)
- **Primary:** hand-made tasks on 2–3 small/medium pure-Python repos with fast, solid test suites (candidates: `attrs`, `click`, `rich`, or similar; pick at commits where `pytest` passes in under 60s). Hand-made is the default because we control the grader and can count callers exactly.
- **Optional:** if RefactorBench (https://arxiv.org/abs/2503.07832, **[verify]** license/format) can be loaded in under 2 hours, take 5–10 of its tasks as an external check.
- Mix (about 20 total): rename a public function/class used in ≥5 places (6); change a signature by adding, removing or reordering a parameter, then update the call sites (5); move a function or module and update imports (5); extract a helper or class from duplicated code (4).
- Each task is `tasks/<id>/task.yaml`: repo, base commit, instruction, `old_symbols` (for caller checks), and the tests that must pass. Also store a reference solution diff, used to compute the "touched files" oracle.

## 2. Arms (priority order; P0 must run, P2 only if time allows)
Single-shot means the model gets context and returns a unified diff. Agentic means a tool loop (read_file, grep, list_dir, edit, run_tests) capped at 30 steps.

| Arm | Conditions | Mode | Priority |
|---|---|---|---|
| **A. Layout** | A1 full repo (truncated to budget) · A2 touched files only (oracle) · A3 skeleton ladder: L0 tree → L1 +imports/dep graph → L2 +signatures → L3 +docstrings (L4 = full bodies = A1) · A4 L2 skeleton + on-demand read/grep · A5 agentic grep/read only | A1–A3 single-shot; A4–A5 agentic | **P0** |
| **B. Compaction** | B0 none · B1 LLM summary at 50% of budget (Gemini CLI default) · B2 summary at 90% (Codex CLI default) · B3 drop old tool outputs (observation masking) | agentic on A5, artificial 32k budget so compaction actually fires | **P1** |
| **C. Procedural context** | C0 no skill · C1 refactor skill file ("find all callers, update each, run tests, re-grep old name") · C2 repo conventions doc (AGENTS.md style) | agentic on A5 | **P1** |
| **D. Placement** | D1 key file at start of prompt · D2 key file at end, with the rest of the repo in between | single-shot on A1 | **P2** |

Total ≈ 15 configs (B0 and C0 reuse A5) × 20 tasks × **3 seeds** ≈ 900 runs.

## 3. Metrics (per run → `results/*.jsonl`)
- **Pass:** the patch applies and the specified tests pass.
- **Missed callers:** references to `old_symbols` still left after the patch (AST plus grep, ignoring strings and comments), and new call sites that break the tests.
- **Diff size:** lines added/removed, and files touched compared with the reference.
- **Tokens:** input, cache-write, cache-read and output tokens taken from API usage fields.
- **Cost:** computed from tokens at list price with caching applied. The headline metric is **cost per solved task** = total cost / passes.
- **Time:** wall time, plus the number of tool calls and steps for agentic runs.
- **Statistics:** pass rate with Wilson 95% CIs and paired comparisons per task (McNemar). Every claim is reported with n.

## 4. Model
- The cheapest *capable* current Anthropic Haiku-class model with prompt caching, used for all arms at temperature 0 (seeds vary only where sampling is non-deterministic; otherwise repeat runs measure API nondeterminism).
- An OpenAI mini-class model is an optional second model, run only if budget and time allow and only on the P0 arms.
- **Needs from Patrick:** an `ANTHROPIC_API_KEY` (and an `OPENAI_API_KEY` if we run the second model), stored in a box env file, never committed.
- Prices are an **assumption** to confirm on the pricing page before running: about $1/M input, $0.10/M cache read, $1.25/M cache write and $5/M output.

## 5. Budget estimate
| Bucket | Runs | Tokens/run (assumed) | ≈ $/run | ≈ Total |
|---|---|---|---|---|
| Single-shot (A1–A3, D) | ~480 | 30k in / 3k out (A1 up to 100k in) | $0.05–0.12 | ~$30 |
| Agentic (A4, A5, B, C) | ~420 | 300k in (~80% cached) / 10k out | ~$0.13 | ~$55 |
| Pilot + reruns + summarizer calls | — | — | — | ~$15 |
| **Total** | | | | **~$100** |

Set a **hard cap of $150** in the harness so it refuses to start new runs past the cap. Adding a second model roughly doubles the P0 cost (+$40).

## 6. Schedule
**Sat Oct 10: build**
- Choose the repos and pin their commits.
- Write the 20 tasks and reference diffs, and check that every reference solution passes the tests.
- Build the harness: the context builders (tree-sitter skeleton L0–L3, full, touched), the single-shot diff applier, the agentic loop with tools, the compaction strategies, the skill injection, the grader and missed-caller checker, and the cost logger.
- Pilot: 3 tasks × the P0 arms × 1 seed. Fix bugs.

**Sun Oct 11: run**
- Morning: P0, arm A, 3 seeds.
- Afternoon: P1 arms B and C.
- Evening: P2 arm D, plus the optional second model.
- Then aggregate the results into tables and charts, and read failed transcripts to build a failure taxonomy (missed caller, bad diff, wrong file, context overflow, compaction lost the goal).

**Mon Oct 12: write**
- Draft the case study and check every number against the results files.
- Make the repo public if Patrick agrees, then publish on bicrick.com and draft a LinkedIn post.

## 7. Case-study outline (bicrick.com)
1. **Hook:** "We held the model fixed and changed only the harness." Headline chart: pass rate vs cost per solved task for each strategy.
2. **Why context shaping matters:** context rot, lost in the middle, LongCodeBench (citing `docs/research/PRIOR_WORK.md`).
3. **How today's harnesses do it:** the comparison table from `SUMMARY.md` (Claude Code, Cursor, Aider, Codex CLI, Gemini CLI, Cline, OpenHands, SWE-agent).
4. **Setup:** the tasks, the model, the arms and metrics, and the threats to validity.
5. **Results:** the A ladder, the B compaction results, the C skills results, the D placement results, each with CIs.
6. **Failure analysis:** example transcripts, with missed callers as the signature refactor failure.
7. **What I'd build into a harness:** concrete recommendations.
8. **Limits and next steps**, including RL-environment framing: tasks plus graders as a reusable environment.
9. **Repo link and how to reproduce:** one command.
