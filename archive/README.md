# Archive

Earlier work that led up to the SWE-bench harness comparison. Kept for the record; nothing here is needed
to reproduce the current results.

- `cshape/`, `tasks/`: the first pilot, a homemade agent loop testing context-shaping strategies
  (skeletons, compaction, masking, skills) on small rename tasks in tinydb, marshmallow and itsdangerous.
- `scripts/`, `Makefile`: the runners and article builder for that pilot (`reproduce.sh`, `chain_*.sh`,
  `publish_bundle.py`). They assume `cshape/` and `tasks/` at the repo root, so run them from inside
  `archive/` (e.g. `cd archive && python -m cshape verify`).
- `figures/`: figures from the pilot (`arm_*`, `headline`, `pareto`, `failures`).
- `docs/`: the pilot's plan, hypotheses, case study and article drafts.
- `publish/`: the old publish bundle for that article.
- `logs/`: leftover status and install logs from the run sprint.

The pilot's raw results stay in `results/` (`main.jsonl`, `hard*.jsonl`, `final.jsonl`, `arm_e.jsonl`, ...)
and are unchanged.
