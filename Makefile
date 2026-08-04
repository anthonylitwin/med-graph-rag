.PHONY: bootstrap up down logs test smoke-test web api qa-answer qa-dataset qa-eval annotation-bootstrap annotation-review annotation-eval annotation-eval-artifacts annotation-eval-index annotation-eval-verify annotation-eval-prune ollama-pull

# Override at runtime, e.g. `make schema PYTHON=.venv-wsl/bin/python`
PYTHON ?= .venv/Scripts/python.exe
MODEL_PROFILE ?= frontier
APP_MODEL_PROFILE ?= local-non-instruct
LOCAL_MODEL ?= qwen2.5:7b-instruct
OLLAMA_BASE_URL ?= http://localhost:11434
DOCKER_OLLAMA_BASE_URL ?= http://host.docker.internal:11434
EXTRACTOR_ENTITY_MODEL ?= Ihor/gliner-biomed-small-v1.0

bootstrap:
	cp -n .env.example .env || true
	APP_MODEL_PROFILE=$(APP_MODEL_PROFILE) LOCAL_MODEL=$(LOCAL_MODEL) DOCKER_OLLAMA_BASE_URL=$(DOCKER_OLLAMA_BASE_URL) EXTRACTOR_ENTITY_MODEL=$(EXTRACTOR_ENTITY_MODEL) docker compose build

up:
	APP_MODEL_PROFILE=$(APP_MODEL_PROFILE) LOCAL_MODEL=$(LOCAL_MODEL) DOCKER_OLLAMA_BASE_URL=$(DOCKER_OLLAMA_BASE_URL) EXTRACTOR_ENTITY_MODEL=$(EXTRACTOR_ENTITY_MODEL) docker compose up

down:
	docker compose down

logs:
	docker compose logs -f

test:
	PYTHONPATH=. $(PYTHON) -m unittest discover -s tests
	cd apps/web && npm run lint
	cd apps/api && $(PYTHON) -m pytest || true

web:
	cd apps/web && npm run dev

api:
	APP_MODEL_PROFILE=$(APP_MODEL_PROFILE) LOCAL_MODEL=$(LOCAL_MODEL) OLLAMA_BASE_URL=$(OLLAMA_BASE_URL) EXTRACTOR_ENTITY_MODEL=$(EXTRACTOR_ENTITY_MODEL) PYTHONPATH=. $(PYTHON) -m uvicorn app.main:app --app-dir apps/api --reload

ollama-pull:
	ollama pull $(LOCAL_MODEL)

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
	MODEL_PROFILE=$(MODEL_PROFILE) LOCAL_MODEL=$(LOCAL_MODEL) OLLAMA_BASE_URL=$(OLLAMA_BASE_URL) EXTRACTOR_ENTITY_MODEL=$(EXTRACTOR_ENTITY_MODEL) PYTHONPATH=. $(PYTHON) pipelines/ingestion/ingest_pmc.py --pmcid $(PMCIDS) $(ARGS)

qa-answer:
	MODEL_PROFILE=$(MODEL_PROFILE) LOCAL_MODEL=$(LOCAL_MODEL) OLLAMA_BASE_URL=$(OLLAMA_BASE_URL) EXTRACTOR_ENTITY_MODEL=$(EXTRACTOR_ENTITY_MODEL) PYTHONPATH=. $(PYTHON) pipelines/qa/answer_questions.py --question-file $(QUESTIONS) $(ARGS)

qa-dataset:
	PYTHONPATH=. $(PYTHON) pipelines/qa/process_training_dataset.py --dataset $(DATASET) $(ARGS)

qa-eval:
	MODEL_PROFILE=$(MODEL_PROFILE) LOCAL_MODEL=$(LOCAL_MODEL) OLLAMA_BASE_URL=$(OLLAMA_BASE_URL) EXTRACTOR_ENTITY_MODEL=$(EXTRACTOR_ENTITY_MODEL) PYTHONPATH=. $(PYTHON) eval/runners/run_graph_rag_baseline.py $(ARGS)

annotation-bootstrap: MODEL_PROFILE = local-qwen25
annotation-bootstrap:
	MODEL_PROFILE=$(MODEL_PROFILE) LOCAL_MODEL=$(LOCAL_MODEL) OLLAMA_BASE_URL=$(OLLAMA_BASE_URL) EXTRACTOR_ENTITY_MODEL=$(EXTRACTOR_ENTITY_MODEL) PYTHONPATH=. $(PYTHON) pipelines/annotation/bootstrap_annotations.py --pmcid $(PMCIDS) --model-profile $(MODEL_PROFILE) $(ARGS)

annotation-review:
	PYTHONPATH=. $(PYTHON) pipelines/annotation/adjudicate_annotations.py --workbook "$(WORKBOOK)" $(ARGS)

annotation-eval:
	MODEL_PROFILE=$(MODEL_PROFILE) LOCAL_MODEL=$(LOCAL_MODEL) OLLAMA_BASE_URL=$(OLLAMA_BASE_URL) EXTRACTOR_ENTITY_MODEL=$(EXTRACTOR_ENTITY_MODEL) PYTHONPATH=. $(PYTHON) pipelines/annotation/evaluate_annotations.py $(ARGS)

annotation-eval-artifacts:
	PYTHONPATH=. $(PYTHON) pipelines/annotation/manage_evaluation_artifacts.py list $(ARGS)

annotation-eval-index:
	PYTHONPATH=. $(PYTHON) pipelines/annotation/manage_evaluation_artifacts.py index $(ARGS)

annotation-eval-verify:
	PYTHONPATH=. $(PYTHON) pipelines/annotation/manage_evaluation_artifacts.py verify $(ARGS)

annotation-eval-prune:
	PYTHONPATH=. $(PYTHON) pipelines/annotation/manage_evaluation_artifacts.py prune $(ARGS)
