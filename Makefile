# Shortcuts for the things you actually run.

.PHONY: install seed api web test demo

install:
	cd api && python3 -m venv ../.venv && ../.venv/bin/pip install -r requirements.txt
	cd web && npm install

# Synthetic data plus the search index. Safe to re-run — it replaces both.
seed:
	cd api && ../.venv/bin/python -m app.seed
	cd api && ../.venv/bin/python -m app.rag

api:
	cd api && ../.venv/bin/uvicorn app.main:app --reload --port 8000

web:
	cd web && npm run dev

test:
	cd api && ../.venv/bin/python -m pytest

# Everything a fresh clone needs before the dashboard has anything to show.
demo: install seed
	@echo ""
	@echo "Seeded. Now run 'make api' and 'make web' in two terminals."
	@echo "For the AI features: ollama serve, then ollama pull llama3.1 and nomic-embed-text."
