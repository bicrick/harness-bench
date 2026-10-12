#!/usr/bin/env bash
# 7:15 AM CT build sprint. Arm E seed 0 ran at 2 AM alongside the main run and hit the 500k ITPM org
# limit: 17/22 Aider runs and 18/22 mini-swe-agent runs logged 429s, and several Aider runs gave up
# after backoff (no_edit / partial edits). This waits for the hard2 seed-2 run to finish, then adds
# seed 1 for all 25 tasks (and seed 0 for the 3 hard2 tasks) with nothing else competing for the
# rate limit. New rows carry notes.rate_limit_events counted by the proxy. Log: results/arm_e.log
set -u
cd "$(dirname "$0")/.."
source /workspace/.venv/bin/activate
log(){ echo "$(date '+%F %T') $*"; }
log "chain_arm_e: waiting for running cshape jobs" >> results/arm_e.log
while pgrep -f "cshape run" >/dev/null; do sleep 30; done
log "chain_arm_e: starting arm E seed 1 (+ hard2 tasks seed 0), 3 workers" >> results/arm_e.log
python -m cshape run --strategies ext_claude_code,ext_aider,ext_mini_swe_agent,ext_opencode --seeds 2 --workers 3 --out results/arm_e.jsonl >> results/arm_e.log 2>&1
log "chain_arm_e: done" >> results/arm_e.log
touch results/ARM_E2_DONE
