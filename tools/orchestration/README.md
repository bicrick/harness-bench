# Out-of-repo orchestration (checked in for reproducibility)

Scripts that normally live in `$HOME` next to the runners. Secrets stay out of git: copy `sbr-env.example.sh` to `sbr-env.sh` (gitignored) and fill in keys locally.

| File | Role |
|------|------|
| `sbr-full-manager.py` | Spawns/restarts per-harness shards, cleans images, respects hard cap |
| `sbr-nt-watchdog.sh` | Keeps same-settings (`*_nothink`) tmux runners alive; prunes disk |
| `sbr-nothink-launch.sh` | Initial launch of the thinking-off rerun set |
| `sbr-nt-fifo-reload.sh` | Fair FIFO slot handout across multi-shard runners |
| `sbr-nothink-finalize.md` | Checklist once all 6×50 same-settings rows are in |
| `sbr-env.example.sh` | Env template (no secrets) |

See also `docs/DEVIATIONS.md` for run-time decisions and confounds.
