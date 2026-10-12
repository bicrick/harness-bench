#!/usr/bin/env bash
# Waits for the main/B_tight, hard and hard2 runs to exit, re-runs each resume command once
# (fills errored/missing rows), then selects the combined config and starts the FINAL run.
# Started by the 3:16 AM CT build sprint. Log: results/chain_final.log
set -u
cd "$(dirname "$0")/.."
source /workspace/.venv/bin/activate
ALL=full,touched,skel_L0,skel_L1,skel_L2,skel_L3,skel_retrieval,agentic,agentic_tools,agentic_c50,agentic_c90,agentic_mask,agentic_skill,agentic_agentsmd,agentic_c50_tight,agentic_c90_tight,agentic_mask_tight
log(){ echo "$(date '+%F %T') $*"; }
log "waiting for running cshape jobs"
while pgrep -f "cshape run" >/dev/null; do sleep 60; done
log "all jobs exited; resume pass to fill gaps"
python -m cshape run --strategies agentic_c50_tight,agentic_c90_tight,agentic_mask_tight --seeds 2 --workers 3 --out results/main.jsonl >> results/btight.log 2>&1
python -m cshape run --tasks tinydb-h01-rename-table-search,marshmallow-h01-rename-utils-get-value,marshmallow-h02_rename_load_default --strategies $ALL --seeds 3 --workers 4 --out results/hard.jsonl >> results/hard.log 2>&1
python -m cshape run --tasks tinydb-h02-rename-table-insert,marshmallow-h03-rename-validationerror,itsdangerous-h01-rename-serializer-loads --strategies $ALL --seeds 2 --workers 4 --out results/hard2.jsonl >> results/hard2.log 2>&1
SPENT=$(python -m cshape spend | sed -E 's/spent \$([0-9.]+).*/\1/')
SEEDS=5; python - "$SPENT" <<'PY' || SEEDS=4
import sys; sys.exit(0 if 50-float(sys.argv[1]) >= 15 else 1)
PY
log "spent \$$SPENT; selecting combined config; final run with $SEEDS seeds"
python -m cshape.combine
python -m cshape run --strategies full,combined --seeds $SEEDS --workers 6 --out results/final.jsonl >> results/final.log 2>&1
log "final run exited; spend: $(python -m cshape spend)"
touch results/FINAL_DONE
