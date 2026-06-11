.PHONY: bootstrap up down logs test smoke-test web api

# Override at runtime, e.g. `make schema PYTHON=.venv-wsl/bin/python`
PYTHON ?= .venv/Scripts/python.exe

bootstrap:
	cp -n .env.example .env || true
	docker compose build

up:
	docker compose up

down:
	docker compose down

logs:
	docker compose logs -f

test:
	PYTHONPATH=. $(PYTHON) -m unittest discover -s tests
	cd apps/web && npm test -- --run || true
	cd apps/api && $(PYTHON) -m pytest || true

web:
	cd apps/web && npm run dev

api:
	cd apps/api && $(PYTHON) -m uvicorn app.main:app --reload

schema:
	PYTHONPATH=. $(PYTHON) scripts/apply_neo4j_schema.py

seed:
	PYTHONPATH=. $(PYTHON) pipelines/ingestion/seed_sample_graph.py

smoke-test:
	curl -f http://localhost:8000/health
	curl -f -X POST http://localhost:8000/chat \
		-H "Content-Type: application/json" \
		-d '{"message":"Hello MedGraphRAG"}'

graph-smoke-test:
	curl -f http://localhost:8000/graph/sample

ingest-pmc:
	PYTHONPATH=. $(PYTHON) pipelines/ingestion/ingest_pmc.py --pmcid $(PMCIDS) $(ARGS)
