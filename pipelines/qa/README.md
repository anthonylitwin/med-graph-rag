# QA Pipeline Usage And Testing

The QA pipeline mirrors the ingestion pipeline: it reads questions from CLI arguments
or a dataset file, retrieves graph evidence, answers with a configured model provider,
and writes inspectable artifacts plus a manifest.
For the full repo runbook, including UI, ingestion, benchmark runs, artifacts,
and algorithm extension points, see `docs/complete_test_run.md`.

## Batch Question Answering

Cheap smoke test without OpenAI or Neo4j:

```powershell
.\.venv\Scripts\python.exe pipelines/qa/answer_questions.py `
  --question-file eval/questions/qa_eval_v001.json `
  --model-profile noop
```

GraphRAG run using the default frontier model:

```powershell
.\.venv\Scripts\python.exe pipelines/qa/answer_questions.py `
  --question-file eval/questions/qa_eval_v001.json `
  --output-root data/qa/qa_v001 `
  --model-profile frontier
```

Local GraphRAG run with Ollama:

```powershell
ollama pull qwen2.5:7b-instruct

.\.venv\Scripts\python.exe pipelines/qa/answer_questions.py `
  --question-file eval/questions/qa_eval_v001.json `
  --output-root data/qa/local_qwen25 `
  --model-profile local-qwen25
```

Expected artifacts:

```text
data/qa/qa_v001/retrieved/
data/qa/qa_v001/answers/
data/qa/qa_v001/manifest.csv
```

## Training Dataset Processing

The training processor accepts JSON or JSONL records with `question` plus `answer`,
`expected_answer`, or `expected_facts`.

```powershell
.\.venv\Scripts\python.exe pipelines/qa/process_training_dataset.py `
  --dataset eval/questions/qa_eval_v001.json `
  --output-root data/training/qa_v001 `
  --export-format openai-jsonl
```

Supported export formats:

| Format | Output |
| --- | --- |
| `openai-jsonl` | OpenAI chat fine-tuning messages |
| `local-jsonl` | Local SFT instruction/input/output records |
| `internal-jsonl` | Canonical MedGraphRAG training examples |

## Runtime Configuration

The API uses the same QA core as the CLI.

```text
MODEL_PROFILE=frontier
LOCAL_MODEL=qwen2.5:7b-instruct
OLLAMA_BASE_URL=http://localhost:11434
QA_MAX_EVIDENCE=12
```

Supported profiles are `frontier`, `local-qwen25`, `local-qwen3`, and `noop`.
You can still override the profile with `--answerer`, `--model`, and `--retriever`
for one-off runs.
