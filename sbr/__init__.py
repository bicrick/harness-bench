"""SWE-bench harness comparison: one model (Claude Haiku 5.5), many real harnesses, the same SWE-bench Verified subset.

Layout:
  subset.py    pick a pinned, stratified random subset of SWE-bench Verified
  proxy.py     logging reverse proxy with a per-task dollar cap and a global hard cap
  harnesses.py one adapter per harness; each returns a patch for one instance
  run.py       the resumable loop: pull image -> run every harness -> grade -> delete image
  report.py    summary table and per-turn window sizes from the proxy logs
"""
