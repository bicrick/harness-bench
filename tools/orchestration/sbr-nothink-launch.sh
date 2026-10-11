#!/bin/bash
# same-settings rerun: each runner loops until its run.py prints "done;" (resumable; claims prevent double runs)
name=$1; h=$2; inst=$3
for i in 1 2 3 4 5 6; do
  source ~/sbr-env.sh; cd ~/context-shaping
  SBR_TOOLS=/home/box/sbr-tools SBR_HARD_CAP=45 SBR_DOCKER="sudo docker" /home/box/sbr-tools/host/bin/python -m sbr.run --keep-images --harnesses $h ${inst:+--instances $inst} 2>&1 | tee -a ~/sbr-nt-$name.txt
  tail -3 ~/sbr-nt-$name.txt | grep -q "^done;" && break
  sleep 30
done
