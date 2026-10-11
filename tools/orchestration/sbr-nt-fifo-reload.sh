#!/bin/bash
# Reload mid-pair runners onto FIFO slot code the instant they release a slot (never kill while holding).
HOLDERS_FILE=~/sbr-nt-fifo-holders.txt
LOG=~/sbr-nt-fifo-reload.log
echo "$(date +%H:%M:%S) re-armed (0.5s poll); watching:" >> "$LOG"
cat "$HOLDERS_FILE" >> "$LOG"
while [ -s "$HOLDERS_FILE" ]; do
  tmp=$(mktemp)
  while read -r pid name; do
    [ -z "$pid" ] && continue
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "$(date +%H:%M:%S) $name pid $pid already gone" >> "$LOG"
      continue
    fi
    holding=$(python3 -c "
import fcntl
from pathlib import Path
pid='$pid'
for k in range(3):
  with open(Path.home()/f'sbr-slots/slot{k}.lock') as f:
    c=f.read()
    try:
      fcntl.flock(f, fcntl.LOCK_EX|fcntl.LOCK_NB); fcntl.flock(f, fcntl.LOCK_UN); held=False
    except BlockingIOError:
      held=True
    if held and c.startswith(pid+' '):
      print('yes'); break
else:
  print('no')
")
    if [ "$holding" = "yes" ]; then
      echo "$pid $name" >> "$tmp"
    else
      echo "$(date +%H:%M:%S) $name pid $pid released — killing for FIFO reload" >> "$LOG"
      kill "$pid" 2>/dev/null || true
      # brief pause so it can't race back into LOCK_NB before death
      sleep 0.2
      kill -9 "$pid" 2>/dev/null || true
    fi
  done < "$HOLDERS_FILE"
  mv "$tmp" "$HOLDERS_FILE"
  sleep 0.5
done
echo "$(date +%H:%M:%S) all holders reloaded; exiting" >> "$LOG"
