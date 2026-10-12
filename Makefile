# SWE-bench harness comparison. See swebench/README.md for VM setup.
PY ?= $(SBR_TOOLS)/host/bin/python

preflight:
	$(PY) -m sbr.preflight

run:
	$(PY) -m sbr.run --harnesses claude_code_nothink,cursor_nothink,opencode_nothink,swe_agent_nothink,mini_swe_agent_nothink

report:
	$(PY) -m sbr.report

figures:
	uv run --with matplotlib python3 scripts/swebench_figures.py

.PHONY: preflight run report figures
