# MedGraphRAG

MedGraphRAG is a modular healthcare knowledge graph and GraphRAG platform.

## Local development

### Prerequisites

- Docker Desktop
- Node.js 20+
- Python 3.11+
- Make

### Start the platform

```bash
cp .env.example .env
make bootstrap
make up
```

### Model Profiles

The app supports runtime profiles through `MODEL_PROFILE`:

| Profile | QA runtime | Extraction runtime |
| --- | --- | --- |
| `frontier` | OpenAI Responses API | OpenAI Responses API |
| `local-qwen25` | Ollama `qwen2.5:7b-instruct` | GLiNER-BioMed entities + Ollama relationships |
| `local-qwen3` | Ollama `qwen3:8b` | GLiNER-BioMed entities + Ollama relationships |
| `noop` | Deterministic smoke-test fixtures | No-op extractor |

For host-run Python, keep `OLLAMA_BASE_URL=http://localhost:11434`. For Docker, use
`DOCKER_OLLAMA_BASE_URL=http://host.docker.internal:11434`.

```bash
make ollama-pull LOCAL_MODEL=qwen2.5:7b-instruct
make up MODEL_PROFILE=local-qwen25
make qa-answer QUESTIONS=eval/questions/qa_eval_v001.json MODEL_PROFILE=noop
```

For a complete end-to-end test run, including model selection, smoke tests,
full UI startup, benchmark ingestion, QA artifacts, and extension points, see
[docs/complete_test_run.md](docs/complete_test_run.md).

### Annotation Bootstrap

Generate a silver annotation workbook for human review without loading Neo4j:

```bash
make annotation-bootstrap PMCIDS="PMC3572442" MODEL_PROFILE=noop
make annotation-bootstrap PMCIDS="PMC3572442" MODEL_PROFILE=local-qwen25
make annotation-bootstrap PMCIDS="PMC3572442" MODEL_PROFILE=frontier
```

Each run writes artifacts under `data/annotations/bootstrap_v001/<run_id>/`,
including `annotation_workbook.xlsx`, `run_manifest.json`, `manifest.csv`,
processed source-document JSON, and per-chunk model-call audit JSON.

For workbook review details, see
[pipelines/annotation/README.md](pipelines/annotation/README.md).
