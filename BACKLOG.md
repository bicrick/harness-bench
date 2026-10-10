# Backlog

## Research follow-ups
- [ ] Verify [verify] items in PRIOR_WORK.md (SWE-bench retrieval ablation, Agentless skeleton, Complexity Trap, RefactorBench).
- [ ] Cursor docs pass: rules, summarization, @-context; Cline SDK compaction thresholds; Claude Code auto-compact %.

## Harness (phase 2)
- [ ] Pick 2–3 Python repos with good test suites (pin commits). Consider RefactorBench as task source.
- [ ] Write 20–30 refactor tasks: rename public API, move module, change signature used in ≥5 call sites, extract class. Each: instruction, base commit, grader.
- [ ] Grader: repo tests pass + static check that every pre-refactor reference is updated (AST/grep over old symbol) → **missed callers**.
- [ ] Context strategies (pluggable `build_context(task) -> messages`):
  - [ ] full repo (truncate to budget)
  - [ ] touched files only (oracle)
  - [ ] skeleton levels: L0 tree, L1 +imports/dep graph, L2 +signatures, L3 +docstrings (reuse Aider tree-sitter tags)
  - [ ] skeleton + retrieval tool (read_file, grep)
  - [ ] pure agentic (grep/read only) baseline
- [ ] Compaction ablations for agentic runs: trigger 50%/90%, LLM summary vs observation masking.
- [ ] Model adapter for a cheap Haiku-class model; enable prompt caching; log usage incl. cache reads.
- [ ] Metrics per run: pass, missed callers, diff size, input/output/cache tokens, $ cost, wall time, tool calls; cost per success.
- [ ] One command: `python -m cshape run --strategy X --tasks all`; results to JSONL + table + chart.
- [ ] Budget cap and dry-run mode.
