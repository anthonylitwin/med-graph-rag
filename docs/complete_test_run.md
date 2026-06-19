# MedGraphRAG Complete Test Runbook

This runbook covers the current workspace end to end: model selection, smoke
tests, full UI startup, benchmark ingestion, annotation bootstrap, QA runs,
generated artifacts, and the main extension points for improving algorithms.

The primary app surfaces are:

| Area | Path | Role |
| --- | --- | --- |
| API | `apps/api/app` | FastAPI routes for health, chat, and graph sample views. |
| Web UI | `apps/web` | Vite/React app with Chat and Graph pages. |
| Shared LLM runtime | `packages/llm` | Model profiles plus OpenAI, Ollama, local HTTP, and noop providers. |
| Graph schema | `packages/graph/schema` | Ontology, Cypher schema, and frontier extraction prompt. |
| Ingestion | `pipelines/ingestion` | PMC fetch, chunk, extract, validate, and load pipeline. |
| Annotation | `pipelines/annotation` | Silver annotation bootstrap, Excel workbook export, and model-call audit artifacts. |
| QA | `pipelines/qa` | Graph evidence retrieval, answer generation, and artifact writing. |
| Evaluation | `eval` | Question sets and baseline runners. |

`apps/ui/react-app` is present in the tree, but the active Docker and Make
workflow uses `apps/web`.

## 1. One-Time Setup

From the repo root:

```powershell
cp .env.example .env
.\.venv\Scripts\python.exe -m pip install -r apps/api/requirements.txt
cd apps/web
npm install
cd ..\..
```

For local GLiNER extraction:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-local-models.txt
ollama pull qwen2.5:7b-instruct
ollama pull qwen3:8b
```

Required service defaults:

```text
NEO4J_LOCAL_URI=bolt://localhost:7687
NEO4J_URI=bolt://neo4j:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=medgraphrag-password
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.5
MODEL_PROFILE=frontier
OLLAMA_BASE_URL=http://localhost:11434
DOCKER_OLLAMA_BASE_URL=http://host.docker.internal:11434
```

## 2. Model Profiles

Model profiles are resolved in `packages/llm/profiles.py`.

| Profile | QA provider/model | Extraction provider/model | Use case |
| --- | --- | --- | --- |
| `frontier` | OpenAI, `OPENAI_MODEL` | OpenAI, `OPENAI_MODEL` | Best current extraction/QA path. |
| `local-qwen25` | Ollama, `qwen2.5:7b-instruct` | GLiNER-BioMed + Ollama | Local end-to-end development. |
| `local-qwen3` | Ollama, `qwen3:8b` | GLiNER-BioMed + Ollama | Alternate local Qwen runtime. |
| `noop` | Noop fixtures | Noop extractor | Fast plumbing tests without services. |

Select a profile with one of:

```powershell
# CLI
.\.venv\Scripts\python.exe pipelines/qa/answer_questions.py `
  --question-file eval/questions/qa_eval_v001.json `
  --model-profile local-qwen3

# Make
make qa-answer QUESTIONS=eval/questions/qa_eval_v001.json MODEL_PROFILE=local-qwen25

# API/UI default
$env:MODEL_PROFILE = "noop"
```

Override the concrete model for one run:

```powershell
.\.venv\Scripts\python.exe pipelines/qa/answer_questions.py `
  --question-file eval/questions/qa_eval_v001.json `
  --model-profile local-qwen25 `
  --model qwen3:8b
```

The Chat UI also has a profile selector. It sends `modelProfile` to `POST /chat`.

## 3. Fast Smoke Tests

Run these before spending tokens or running local models.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall packages pipelines scripts tests apps/api/app
cd apps/web
npm.cmd run build
cd ..\..
```

No-service QA smoke:

```powershell
.\.venv\Scripts\python.exe pipelines/qa/answer_questions.py `
  --question-file eval/questions/qa_eval_v001.json `
  --output-root data/qa/smoke_noop `
  --model-profile noop `
  --clean-output
```

No-model ingestion smoke:

```powershell
.\.venv\Scripts\python.exe pipelines/ingestion/ingest_pmc.py `
  --pmcid-file data/source_documents/benchmark_pmcids.txt `
  --limit 1 `
  --model-profile noop `
  --skip-load `
  --clean-output
```

Expected ingestion artifacts:

```text
data/source_documents/pmc_v001/raw/PMC3572442.json
data/source_documents/pmc_v001/text/PMC3572442.txt
data/source_documents/pmc_v001/processed/PMC3572442.json
data/source_documents/pmc_v001/manifest.csv
```

Expected QA artifacts:

```text
data/qa/smoke_noop/retrieved/*.json
data/qa/smoke_noop/answers/*.json
data/qa/smoke_noop/manifest.csv
```

Annotation workbook smoke:

```powershell
.\.venv\Scripts\python.exe pipelines/annotation/bootstrap_annotations.py `
  --pmcid-file data/source_documents/benchmark_pmcids.txt `
  --limit 1 `
  --model-profile noop
```

Expected annotation artifacts:

```text
data/annotations/bootstrap_v001/<run_id>/annotation_workbook.xlsx
data/annotations/bootstrap_v001/<run_id>/run_manifest.json
data/annotations/bootstrap_v001/<run_id>/manifest.csv
data/annotations/bootstrap_v001/<run_id>/source_documents/processed/*.json
```

## 4. Start Services And Full UI

### Docker path

Start the platform:

```powershell
make up MODEL_PROFILE=frontier
```

For local Ollama from Docker:

```powershell
make ollama-pull LOCAL_MODEL=qwen2.5:7b-instruct
make up MODEL_PROFILE=local-qwen25 DOCKER_OLLAMA_BASE_URL=http://host.docker.internal:11434
```

Open:

```text
Web UI: http://localhost:5173
API:    http://localhost:8000
Neo4j:  http://localhost:7474
MLflow: http://localhost:5000
MinIO:  http://localhost:9001
```

### Host-run API and web path

Use this when iterating on backend and frontend code:

```powershell
$env:MODEL_PROFILE = "noop"
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps/api --reload
```

In another shell:

```powershell
cd apps/web
npm.cmd run dev
```

Check API:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/chat/model-options
```

Use the UI:

1. Open `http://127.0.0.1:5173`.
2. On Chat, select `Noop`, `Frontier API`, `Local Qwen 2.5`, or `Local Qwen 3`.
3. Ask a question from `eval/questions/qa_eval_v001.json`.
4. On Graph, click Refresh Graph after seeding or loading Neo4j.

## 5. Graph Smoke Test

Start Neo4j:

```powershell
docker compose up neo4j
```

Apply schema and seed a sample graph:

```powershell
.\.venv\Scripts\python.exe scripts/apply_neo4j_schema.py
.\.venv\Scripts\python.exe pipelines/ingestion/seed_sample_graph.py
```

Check graph endpoint:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/graph/sample
```

The Graph UI currently reads `/graph/sample`, which filters for `sample=true`
nodes and relationships. Full ingested graph exploration is done in Neo4j
Browser until the UI graph query is expanded.

## 6. Ingest Benchmark Documents

The benchmark set is `data/source_documents/benchmark_pmcids.txt` and currently
contains 30 PMC IDs.

Run one document first:

```powershell
.\.venv\Scripts\python.exe pipelines/ingestion/ingest_pmc.py `
  --pmcid-file data/source_documents/benchmark_pmcids.txt `
  --limit 1 `
  --model-profile frontier `
  --skip-load `
  --fail-fast
```

Run all benchmark documents and load Neo4j:

```powershell
.\.venv\Scripts\python.exe pipelines/ingestion/ingest_pmc.py `
  --pmcid-file data/source_documents/benchmark_pmcids.txt `
  --model-profile frontier `
  --apply-schema `
  --fail-fast
```

Run all benchmark documents with local models:

```powershell
ollama pull qwen2.5:7b-instruct

.\.venv\Scripts\python.exe pipelines/ingestion/ingest_pmc.py `
  --pmcid-file data/source_documents/benchmark_pmcids.txt `
  --model-profile local-qwen25 `
  --apply-schema `
  --fail-fast
```

Artifact-only local run without Neo4j load:

```powershell
.\.venv\Scripts\python.exe pipelines/ingestion/ingest_pmc.py `
  --pmcid-file data/source_documents/benchmark_pmcids.txt `
  --model-profile local-qwen3 `
  --skip-load `
  --output-root data/source_documents/pmc_local_qwen3
```

Useful ingestion options:

| Option | Use |
| --- | --- |
| `--model-profile` | Select `frontier`, `local-qwen25`, `local-qwen3`, or `noop`. |
| `--model` | Override OpenAI or Ollama relation model. |
| `--entity-model` | Override the GLiNER entity model. |
| `--min-confidence` | Drop relationships below a confidence threshold. |
| `--limit` | Process only the first N benchmark IDs. |
| `--skip-load` | Write artifacts but do not write Neo4j. |
| `--apply-schema` | Apply Cypher schema before loading. |
| `--clean-output` | Clear the output root before writing new artifacts. |
| `--fail-fast` | Stop on first failed article or chunk. |

Ingestion by-products:

| Path | Contents |
| --- | --- |
| `raw/*.json` | PMC BioC payload fetched from NCBI. |
| `text/*.txt` | Parsed full text used for chunking. |
| `processed/*.json` | Run metadata, chunks, raw extractions, normalized entities, relationships, and rejected candidates. |
| `manifest.csv` | Per-article fetch, extract, load, count, and error summary. |
| Neo4j | `Paper`, ontology entity nodes, `MENTIONS`, and extracted ontology relationships. |

Useful Neo4j checks:

```cypher
MATCH (p:Paper)-[:MENTIONS]->(e)
RETURN p.pmcid, labels(e), e.name
LIMIT 25;
```

```cypher
MATCH (a)-[r]->(b)
WHERE type(r) <> "MENTIONS"
RETURN labels(a), a.name, type(r), labels(b), b.name, r.evidence, r.confidence
ORDER BY r.confidence DESC
LIMIT 25;
```

## 7. Bootstrap Annotation Workbooks

Use annotation bootstrap when you want a human-review workbook before promoting
model output to gold labels. This command reuses PMC ingestion and extraction,
writes processed source-document artifacts, records per-call model audit JSON,
and does not load Neo4j.

No-model workbook smoke:

```powershell
.\.venv\Scripts\python.exe pipelines/annotation/bootstrap_annotations.py `
  --pmcid PMC3572442 `
  --model-profile noop
```

Local silver bootstrap, the recommended confidence-building path:

```powershell
.\.venv\Scripts\python.exe pipelines/annotation/bootstrap_annotations.py `
  --pmcid-file data/source_documents/benchmark_pmcids.txt `
  --limit 1
```

Frontier silver bootstrap after local validation:

```powershell
.\.venv\Scripts\python.exe pipelines/annotation/bootstrap_annotations.py `
  --pmcid PMC3572442 `
  --model-profile frontier `
  --fail-fast
```

Makefile usage:

```powershell
make annotation-bootstrap PMCIDS="PMC3572442"
make annotation-bootstrap PMCIDS="PMC3572442" MODEL_PROFILE=frontier
```

Annotation by-products:

| Path | Contents |
| --- | --- |
| `annotation_workbook.xlsx` | v1.1 review workbook with silver rows in `gold_entities` and `gold_relationships`, marked `needs_review`. |
| `run_manifest.json` | Run settings, model profile, output paths, PMCID list, and per-article summary. |
| `manifest.csv` | Top-level copy of the per-article ingestion manifest. |
| `source_documents/*` | Raw, text, and processed PMC artifacts from the artifact-only run. |
| `model_calls/*/*.json` | Prompt, schema, request, parsed output, raw response where available, timing, status, provider, model, and prompt version. |

For workbook review details, see `pipelines/annotation/README.md`.

## 8. Run QA And Evaluation

Noop QA:

```powershell
.\.venv\Scripts\python.exe pipelines/qa/answer_questions.py `
  --question-file eval/questions/qa_eval_v001.json `
  --output-root data/qa/smoke_noop `
  --model-profile noop `
  --clean-output
```

GraphRAG QA after loading Neo4j:

```powershell
.\.venv\Scripts\python.exe pipelines/qa/answer_questions.py `
  --question-file eval/questions/qa_eval_v001.json `
  --output-root data/qa/graph_frontier `
  --model-profile frontier `
  --retriever graph `
  --clean-output
```

Local QA after loading Neo4j:

```powershell
.\.venv\Scripts\python.exe pipelines/qa/answer_questions.py `
  --question-file eval/questions/qa_eval_v001.json `
  --output-root data/qa/graph_local_qwen25 `
  --model-profile local-qwen25 `
  --retriever graph `
  --clean-output
```

Baseline eval runner:

```powershell
.\.venv\Scripts\python.exe eval/runners/run_graph_rag_baseline.py `
  --question-file eval/questions/qa_eval_v001.json `
  --output-root data/qa/eval_graph_rag_v001 `
  --model-profile noop
```

QA by-products:

| Path | Contents |
| --- | --- |
| `retrieved/*.json` | Question record and retrieved graph evidence. |
| `answers/*.json` | Answer JSON, sources, reasoning path, raw model response, and retrieved evidence. |
| `manifest.csv` | Per-question provider, model, profile, retrieval counts, confidence, abstention, status, and errors. |

## 9. Complete Full Run Checklist

Use this sequence for a full local validation pass:

1. Run unit, compile, and web build checks.
2. Start Neo4j.
3. Apply schema.
4. Run ingestion smoke with `noop --skip-load --limit 1`.
5. Run one real extraction with `frontier --skip-load --limit 1` or `local-qwen25 --skip-load --limit 1`.
6. Run annotation bootstrap with `noop`, then local, then `frontier` when ready.
7. Review `annotation_workbook.xlsx` and model-call audit JSON.
8. Run all benchmark ingestion with `--apply-schema --fail-fast`.
9. Seed sample graph if you want the current Graph UI sample page populated.
10. Run QA with `--retriever graph`.
11. Start API and web.
12. Use the Chat model selector and Graph page.
13. Inspect manifests and processed JSON artifacts.

## 10. Extension Points For Improving Algorithms

### Model runtime

- `packages/llm/profiles.py`: add new named profiles, default models, or profile aliases.
- `packages/llm/providers.py`: add new model providers or use `generate_json_record` when a workflow needs full call audit JSON. Current providers are OpenAI Responses, Ollama chat, generic local HTTP, and noop.
- `apps/api/app/services/qa_service.py`: controls profile resolution and answerer caching for UI/API chat.

### Extraction quality

- `packages/graph/schema/001_initial_prompt.md`: frontier extraction instructions.
- `packages/graph/schema/ontology.md`: ontology description for humans.
- `pipelines/ingestion/extractors.py`: OpenAI extractor and GLiNER + Ollama local extractor.
- `pipelines/ingestion/validation.py`: canonical entity types, relationship direction rules, evidence requirements, confidence filtering, deterministic IDs.
- `pipelines/ingestion/chunking.py`: chunk size, overlap, and text segmentation behavior.
- `pipelines/annotation/workbook.py`: workbook sheet contract, dropdown values, and silver-to-review row mapping.
- `pipelines/annotation/bootstrap_annotations.py`: artifact-only annotation orchestration and run manifest shape.

Good next improvements:

- Tune GLiNER labels, thresholds, and candidate deduplication.
- Add sentence-level evidence span selection before relation extraction.
- Split local relationship prompts by sentence or candidate pair to reduce noise.
- Add ontology types such as Gene, Protein, Procedure, Trial, or Population only after updating validation, schema, prompt, tests, and UI.
- Add reviewed-workbook import only after locking the accepted/rejected row semantics.

### Retrieval and QA

- `packages/qa/retrievers.py`: current graph retriever matches question text against source/target names. Improve here for embeddings, aliases, full-text evidence, graph expansion, and reranking.
- `packages/qa/prompts.py`: QA answer JSON schema and prompt.
- `packages/qa/answerers.py`: answer normalization, fallback behavior, noop answer generation, and evidence-to-source mapping.
- `eval/questions/*.json`: question sets and expected facts.
- `eval/runners/*.py`: baseline runners for comparing retrieval and answer quality.

Good next improvements:

- Add alias-aware or embedding-backed retrieval.
- Retrieve Paper and Chunk context along with relationship evidence.
- Add precision/recall metrics over expected entities and relationships.
- Add answer faithfulness checks against retrieved evidence.

### Graph and UI

- `packages/graph/schema/001_initial_schema.cypher`: constraints and indexes.
- `pipelines/ingestion/neo4j_loader.py`: graph write shape and idempotent MERGE behavior.
- `apps/api/app/routes/graph.py`: current graph endpoint returns only `sample=true` graph data.
- `apps/web/src/routes/GraphPage.tsx`: current graph view renders a simple list and raw JSON.

Good next improvements:

- Add a graph endpoint for PMCID, entity name, or relationship type filters.
- Add visual graph rendering and evidence side panels.
- Expose ingestion run manifests and processed artifacts in the UI.

## 11. Troubleshooting

| Symptom | Check |
| --- | --- |
| Ollama works on host but not Docker | Use `DOCKER_OLLAMA_BASE_URL=http://host.docker.internal:11434`. |
| `gliner_ollama` import error | Install `requirements-local-models.txt`. |
| OpenAI path fails | Check `OPENAI_API_KEY` and `OPENAI_MODEL`. |
| Annotation workbook export fails | Install `apps/api/requirements.txt`; the workbook exporter needs `openpyxl`. |
| Annotation run has no `model_calls` files | Use `pipelines/annotation/bootstrap_annotations.py`; regular ingestion only records calls when configured by annotation mode. |
| Graph QA retrieves nothing | Confirm Neo4j is loaded and the question contains an entity name present in the graph. |
| Graph UI empty | Seed sample graph or extend `/graph/sample`; current endpoint only returns `sample=true` nodes. |
| PowerShell blocks `npm` | Use `npm.cmd run build` or `npm.cmd run dev`. |
| Artifacts look stale | Use `--clean-output` with care on the specific output root for a fresh run. |
