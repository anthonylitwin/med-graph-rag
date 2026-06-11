# QA Pipeline Usage And Testing

The QA pipeline mirrors the ingestion pipeline: it reads questions from CLI arguments
or a dataset file, retrieves graph evidence, answers with a configured model provider,
and writes inspectable artifacts plus a manifest.

## Batch Question Answering

Cheap smoke test without OpenAI or Neo4j:

```powershell
.\.venv\Scripts\python.exe pipelines/qa/answer_questions.py `
  --question-file eval/questions/qa_eval_v001.json `
  --answerer noop `
  --retriever noop
```

GraphRAG run using the default frontier model:

```powershell
.\.venv\Scripts\python.exe pipelines/qa/answer_questions.py `
  --question-file eval/questions/qa_eval_v001.json `
  --output-root data/qa/qa_v001 `
  --answerer openai `
  --model gpt-5.5 `
  --retriever graph
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
QA_PROVIDER=openai
QA_MODEL=gpt-5.5
QA_RETRIEVER=graph
QA_MAX_EVIDENCE=12
```

Use `QA_PROVIDER=local` with `LOCAL_MODEL_URL` for a local model endpoint, or
`QA_PROVIDER=fine_tuned` with `QA_MODEL` set to a fine-tuned model id.
