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
