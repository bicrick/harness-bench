#!/usr/bin/env bash
# One-command reproduction of every run in the case study (needs ANTHROPIC_API_KEY; about $28 at
# Haiku 5.5 list prices, capped at $50 by cshape/llm.py). Every step is resumable: re-running skips
# finished (task, strategy, seed) rows. Arm E also needs the external harnesses installed
# (see docs/research/HARNESS_PANEL.md). `make figures` alone rebuilds the article from the committed logs for $0.
set -euo pipefail
cd "$(dirname "$0")/.."
MAIN=full,touched,skel_L0,skel_L1,skel_L2,skel_L3,skel_retrieval,agentic,agentic_tools,agentic_c50,agentic_c90,agentic_mask,agentic_skill,agentic_agentsmd
TIGHT=agentic_c50_tight,agentic_c90_tight,agentic_mask_tight
HARD=tinydb-h01-rename-table-search,marshmallow-h01-rename-utils-get-value,marshmallow-h02_rename_load_default
HARD2=tinydb-h02-rename-table-insert,marshmallow-h03-rename-validationerror,itsdangerous-h01-rename-serializer-loads
python -m cshape verify
python -m cshape run --strategies $MAIN --seeds 3 --out results/main.jsonl
python -m cshape run --strategies $TIGHT --seeds 2 --workers 3 --out results/main.jsonl
python -m cshape run --tasks $HARD --strategies $MAIN,$TIGHT --seeds 3 --workers 4 --out results/hard.jsonl
python -m cshape run --tasks $HARD2 --strategies $MAIN,$TIGHT --seeds 3 --workers 3 --out results/hard2.jsonl
python -m cshape.combine
python -m cshape run --strategies full,combined --seeds 5 --out results/final.jsonl
python -m cshape run --strategies ext_claude_code,ext_aider,ext_mini_swe_agent,ext_opencode --seeds 2 --workers 3 --out results/arm_e.jsonl
make figures
