PY = . /workspace/.venv/bin/activate 2>/dev/null;

figures:
	$(PY) python -m cshape.audit && python -m cshape.report && python -m cshape.article

article:
	$(PY) python -m cshape.article

reproduce:
	$(PY) bash scripts/reproduce.sh
