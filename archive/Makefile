PY = . /workspace/.venv/bin/activate 2>/dev/null;

figures:
	$(PY) python -m cshape.audit && python -m cshape.report && python -m cshape.article && python scripts/publish_bundle.py

article:
	$(PY) python -m cshape.article && python scripts/publish_bundle.py

reproduce:
	$(PY) bash scripts/reproduce.sh
