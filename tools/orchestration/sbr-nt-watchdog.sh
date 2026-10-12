#!/bin/bash
# disk/stall watchdog for the *_nothink rerun: prune build cache under 40 GB free; remove sbr/minisweagent containers > 60 min old (WALL_S is 30 min)
while true; do
  free=$(df --output=avail -BG / | tail -1 | tr -dc 0-9)
  [ "$free" -lt 40 ] && sudo docker builder prune -af --filter until=30m >/dev/null && echo "$(date +%H:%M) pruned (free ${free}G)"
  sudo docker ps --format '{{.ID}} {{.Names}} {{.RunningFor}}' | awk '$2 ~ /^(sbr-|minisweagent-)/ && $3 ~ /hour/ {print $1}' | while read c; do sudo docker rm -f $c >/dev/null; echo "$(date +%H:%M) removed stale $c"; done
  if ! tmux ls 2>/dev/null | grep -q '^nt_'; then echo "all runners gone; exiting"; exit; fi
  sleep 120
done
