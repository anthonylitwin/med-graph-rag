# Annotation Bootstrap Pipeline

This pipeline creates silver MedGraphRAG annotations for human review. It fetches
PMC BioC documents, chunks and extracts with the selected model profile, records
full model-call audit JSON, and exports an Excel workbook in the v1.1 annotation
format.

Annotation bootstrap is artifact-only. It does not load annotations into Neo4j.

## Quick Start

No-model plumbing check:

```powershell
.\.venv\Scripts\python.exe pipelines/annotation/bootstrap_annotations.py `
  --pmcid PMC3572442 `
  --model-profile noop
```

Local silver bootstrap, the default validation path:

```powershell
.\.venv\Scripts\python.exe pipelines/annotation/bootstrap_annotations.py `
  --pmcid PMC3572442
```

Frontier silver bootstrap after local validation:

```powershell
.\.venv\Scripts\python.exe pipelines/annotation/bootstrap_annotations.py `
  --pmcid PMC3572442 `
  --model-profile frontier
```

Use `make` for PMCID lists passed on the command line:

```powershell
make annotation-bootstrap PMCIDS="PMC3572442 PMC3234107"
make annotation-bootstrap PMCIDS="PMC3572442" MODEL_PROFILE=frontier
```

## Inputs

Pass PMC IDs directly:

```powershell
.\.venv\Scripts\python.exe pipelines/annotation/bootstrap_annotations.py `
  --pmcid PMC3572442 PMC3234107
```

Or use a plain text PMCID file:

```powershell
.\.venv\Scripts\python.exe pipelines/annotation/bootstrap_annotations.py `
  --pmcid-file data/source_documents/benchmark_pmcids.txt `
  --limit 2
```

Useful options:

| Option | Purpose |
| --- | --- |
| `--model-profile` | Select `local-qwen25` by default, or `local-gliner`, `local-non-instruct`, `noop`, `local-qwen3`, `frontier`. |
| `--model` | Override the OpenAI or Ollama extraction model. |
| `--entity-model` | Override the GLiNER entity model for local extraction. |
| `--entity-threshold` | Minimum GLiNER confidence for local entity candidates. |
| `--min-confidence` | Final validation floor for emitted relationship confidence. |
| `--output-root` | Override the root for annotation runs. Default is `data/annotations/bootstrap_v001`. |
| `--clean-output` | Delete the annotation output root before creating a new run. |
| `--fail-fast` | Stop on the first failed article or chunk. |

## Outputs

Each run writes:

```text
data/annotations/bootstrap_v001/<run_id>/
  annotation_workbook.xlsx
  run_manifest.json
  manifest.csv
  source_documents/raw/*.json
  source_documents/text/*.txt
  source_documents/processed/*.json
  model_calls/<pmcid>/<chunk_id>.<stage>.json
```

`annotation_workbook.xlsx` contains:

| Sheet | Contents |
| --- | --- |
| `documents` | One row per source paper. |
| `chunks` | One row per extraction chunk with source text and offsets. |
| `gold_entities` | Silver entity suggestions marked `needs_review`. |
| `gold_relationships` | Silver relationship suggestions marked `needs_review`. |
| `rejected_candidates` | Model or validation rejections for error analysis. |
| `annotation_notes` | Blank reviewer note sheet. |
| `allowed_values` | Dropdown source values. |

The workbook intentionally writes silver suggestions into the existing
`gold_entities` and `gold_relationships` sheets so reviewers can accept, reject,
or edit rows in place.

## Review Workflow

1. Open `annotation_workbook.xlsx`.
2. Review `documents` and `chunks` for source provenance.
3. Edit `gold_entities` and `gold_relationships`.
4. Change accepted rows from `needs_review` to `accepted`.
5. Mark bad suggestions as `rejected` or set `annotation_decision=exclude`.
6. Use `rejected_candidates` and `annotation_notes` for ontology or prompt issues.

Every accepted relationship should keep concise `evidence_text` copied from the
source chunk, and directionality should be checked before promotion to gold.

## Adjudication To Gold

Adjudication is a separate second-phase command. Bootstrap creates silver
workbooks; adjudication validates a reviewed workbook and exports gold CSV files.
It does not mutate the original silver workbook.

```powershell
.\.venv\Scripts\python.exe pipelines/annotation/adjudicate_annotations.py `
  --workbook data/annotations/bootstrap_v001/<run_id>/annotation_workbook.xlsx
```

Run frontier LLM-assisted adjudication before validation/export:

```powershell
.\.venv\Scripts\python.exe pipelines/annotation/adjudicate_annotations.py `
  --workbook data/annotations/bootstrap_v001/<run_id>/annotation_workbook.xlsx `
  --llm-review
```

Or use make:

```powershell
make annotation-review WORKBOOK="data/annotations/bootstrap_v001/<run_id>/annotation_workbook.xlsx"
make annotation-review WORKBOOK="data/annotations/bootstrap_v001/<run_id>/annotation_workbook.xlsx" ARGS="--llm-review"
```

Outputs are written under `data/annotations/gold_v001/<review_id>/`:

| File | Purpose |
| --- | --- |
| `reviewed_annotation_workbook.xlsx` | Copy of the workbook being adjudicated. |
| `adjudication_report.json` | Validation summary, blocking errors, and export metadata. |
| `gold_entities.csv` | Accepted entity rows, written only when validation passes. |
| `gold_relationships.csv` | Accepted relationship rows, written only when validation passes. |

Gold export is blocked while chunks, entity rows, or relationship rows remain
`needs_review`, while accepted relationships have unresolved direction,
negation, or speculation flags, or when relationship endpoints do not map to
accepted entities in the same chunk.

`--llm-review` always uses the `frontier` OpenAI model profile. It reviews each
chunk entities-first and relationships-second, updates only the copied
`reviewed_annotation_workbook.xlsx`, and writes audit JSON under
`model_calls/<pmcid>/<chunk_id>.*_adjudication.json`.

## Gold Evaluation

Annotation evaluation runs a model against the canonical chunks in a gold
manifest and scores extracted entities and relationships against the exported
gold CSV files. It is artifact-only and does not load Neo4j, apply the Neo4j
schema, or mutate graph state.

Smoke-test the plumbing with the deterministic no-op extractor:

```powershell
.\.venv\Scripts\python.exe pipelines/annotation/evaluate_annotations.py `
  --gold-manifest data/annotations/gold_v001/bootstrap_v001_full/gold_manifest.json `
  --model-profile noop `
  --limit 2
```

Run a local extraction experiment:

```powershell
.\.venv\Scripts\python.exe pipelines/annotation/evaluate_annotations.py `
  --gold-manifest data/annotations/gold_v001/bootstrap_v001_full/gold_manifest.json `
  --model-profile local-qwen25 `
  --eval-id local-qwen25-bootstrap-v001
```

Run the non-instruct entity-only baseline without Ollama relationship calls:

```powershell
.\.venv\Scripts\python.exe pipelines/annotation/evaluate_annotations.py `
  --gold-manifest data/annotations/gold_v001/bootstrap_v001_full/gold_manifest.json `
  --model-profile local-gliner `
  --eval-id local-gliner-bootstrap-v001
```

Run the composed non-instruct pipeline with terminology normalization and
cosine-scored relationship candidates:

```powershell
.\.venv\Scripts\python.exe pipelines/annotation/evaluate_annotations.py `
  --gold-manifest data/annotations/gold_v001/bootstrap_v001_full/gold_manifest.json `
  --model-profile local-non-instruct `
  --eval-id local-non-instruct-bootstrap-v001 `
  --relation-threshold 0.66 `
  --concept-threshold 0.84
```

Or use make:

```powershell
make annotation-eval MODEL_PROFILE=noop ARGS="--gold-manifest data/annotations/gold_v001/bootstrap_v001_full/gold_manifest.json --limit 2"
make annotation-eval MODEL_PROFILE=local-qwen25 ARGS="--gold-manifest data/annotations/gold_v001/bootstrap_v001_full/gold_manifest.json --eval-id local-qwen25-bootstrap-v001"
```

Each evaluation writes:

| File | Purpose |
| --- | --- |
| `eval_manifest.json` | Run config, source gold set, output paths, and summary metrics. |
| `artifact_manifest.json` | SHA-256 hashes for durable experiment artifacts. |
| `summary.md` | Human-readable run summary and key artifact paths. |
| `metrics.json` / `metrics.csv` | Overall, separate entity/relationship, per-entity-type, and per-relationship-type precision/recall/F1. |
| `chunk_results.csv` | Per-chunk extraction status and counts. |
| `errors.csv` | Extraction errors with chunk/document provenance; header-only when no errors occur. |
| `matches/entity_matches.csv` | Entity TP/FP/FN rows with chunk, type, normalized name, and stable match key. |
| `matches/relationship_matches.csv` | Relationship TP/FP/FN rows with chunk, relationship type, source endpoint, target endpoint, and stable match key. |
| `gold_snapshot/*` | Copied gold manifest, workbook, gold CSVs, and snapshot manifest used for this exact run. |
| `predictions/processed/*.json` | Per-document prediction records using the ingestion processed-record shape. |
| `model_calls/<pmcid>/*.json` | Provider/model audit JSON when the extractor supports audit logging. |
| `neo4j_load_report.json` | Artifact-only report confirming no Neo4j writes were attempted. |

The CLI exposes reserved Neo4j boundary flags so accidental graph writes fail
clearly:

```powershell
--neo4j-load-mode none
--apply-schema
--neo4j-run-label <label>
```

Only `--neo4j-load-mode none` is accepted in the evaluation runner. Gold or
prediction ingestion should be handled by a separate explicit Neo4j ingestion
step.

### MLflow Logging

MLflow logging is optional and disabled by default. Start the local MLflow stack
with Docker Compose, then pass `--mlflow`:

```powershell
docker compose up mlflow minio

.\.venv\Scripts\python.exe pipelines/annotation/evaluate_annotations.py `
  --gold-manifest data/annotations/gold_v001/bootstrap_v001_full/gold_manifest.json `
  --model-profile noop `
  --limit 2 `
  --eval-id noop-mlflow-smoke `
  --mlflow
```

Use custom tracking metadata when needed:

```powershell
.\.venv\Scripts\python.exe pipelines/annotation/evaluate_annotations.py `
  --gold-manifest data/annotations/gold_v001/bootstrap_v001_full/gold_manifest.json `
  --model-profile local-qwen25 `
  --eval-id local-qwen25-bootstrap-v001 `
  --mlflow `
  --mlflow-tracking-uri http://localhost:5000 `
  --mlflow-experiment medgraphrag-annotation-eval `
  --mlflow-run-name local-qwen25-bootstrap-v001
```

The MLflow run logs gold/model parameters, overall/entity/relationship metrics,
per-entity-type and per-relationship-type metrics, and the full durable eval
artifact folder unless `--no-mlflow-artifacts` is passed. The local
`eval_manifest.json` records the MLflow run ID and logging status.

### DVC Experiments

The annotation evaluation stage is defined in `experiments/dvc.yaml`, with its
model, gold-set, threshold, run-id, and MLflow settings in
`experiments/params.yaml`. The checked-in default uses the no-op profile and is
safe for validating the experiment plumbing.

The approved document split, sequential parameter sweeps, selection rules, and
final comparison policy are defined in
[`docs/annotation_evaluation_matrix.md`](../../docs/annotation_evaluation_matrix.md).

Install and initialize DVC once, then reproduce the configured evaluation from
the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-experiments.txt
.\.venv\Scripts\python.exe -m dvc init
.\.venv\Scripts\python.exe -m dvc repro experiments/dvc.yaml:annotation-eval
```

Change `annotation_eval.model_profile`, `eval_id`, model overrides, thresholds,
or MLflow settings in `experiments/params.yaml` for each experiment. The
`annotation_eval.python` default targets the Windows virtual environment; set it
to `../.venv-wsl/bin/python` when running the stage from WSL. Run and compare
DVC experiments with:

```powershell
.\.venv\Scripts\python.exe -m dvc exp run experiments/dvc.yaml:annotation-eval
.\.venv\Scripts\python.exe -m dvc exp show
.\.venv\Scripts\python.exe -m dvc metrics diff
```

DVC tracks the durable evaluation artifacts and the nested `metrics.json` used
for comparisons. The stage fixes `neo4j_load_mode` to `none`; Neo4j ingestion
remains a separate explicit workflow.

Use `model_profile: local-gliner` for the entity-only baseline. Use
`model_profile: local-non-instruct` for the composed pipeline, then tune the
`non_instruct` thresholds and score weights in `experiments/params.yaml`. Both
profiles avoid generative extraction calls.

The composed pipeline applies these stages in order:

1. GLiNER-BioMed detects typed entity mentions and confidence scores.
2. Unicode/whitespace cleanup and exact aliases normalize known terminology.
3. Type-constrained semantic search resolves remaining mentions above
   `concept_threshold` using cosine similarity.
4. Same-sentence entity pairs are filtered by ontology type and direction.
5. Relationship candidates combine semantic similarity, lexical cues, entity
   proximity, and NER confidence.
6. Negated candidates are rejected and candidates below `relation_threshold`
   remain in the audit artifact for analysis.

The `non_instruct` DVC parameters are:

| Parameter | Purpose |
| --- | --- |
| `embedding_model` | Local sentence-transformer used for concept search and relation prototypes. |
| `terminology_path` | Non-gold canonical concept and alias JSON. |
| `entity_threshold` | Minimum GLiNER confidence for entity candidates. |
| `concept_threshold` | Minimum cosine score for semantic concept normalization. |
| `relation_threshold` | Minimum combined score for an emitted relationship. |
| `semantic_floor` | Minimum semantic score when no lexical cue is present. |
| `semantic_weight` | Contribution from sentence-to-relationship cosine similarity. |
| `cue_weight` | Contribution from deterministic relationship cue matching. |
| `proximity_weight` | Contribution from mention distance within a sentence. |
| `entity_confidence_weight` | Contribution from the two GLiNER confidence scores. |
| `max_pair_distance` | Maximum character distance between candidate endpoints. |

Each chunk writes a `non_instruct_pipeline` audit JSON containing normalized
mentions, every accepted/rejected relation candidate, component scores, and the
effective configuration. The terminology file must remain independent of the
gold evaluation exports to avoid leaking expected answers into extraction.

### Artifact Management

Evaluation runs are generated under `data/annotations/eval_v001/` and ignored
by Git. Use the artifact manager instead of manually deleting run directories.

List runs with profiles, completion status, metrics, size, and protection flags:

```powershell
.\.venv\Scripts\python.exe pipelines/annotation/manage_evaluation_artifacts.py list
make annotation-eval-artifacts
make annotation-eval-artifacts ARGS="--profile local-non-instruct"
make annotation-eval-artifacts ARGS="--match 'dev-*' --status complete"
```

Write machine-readable JSON and CSV indexes for reporting or spreadsheet use:

```powershell
make annotation-eval-index
```

Verify durable artifacts against `artifact_manifest.json` SHA-256 hashes. Paths
are resolved relative to the run when a repository has moved:

```powershell
make annotation-eval-verify
make annotation-eval-verify ARGS="local-non-instruct-smoke"
```

Pin important runs so retention commands cannot remove them:

```powershell
.\.venv\Scripts\python.exe pipelines/annotation/manage_evaluation_artifacts.py pin holdout-frontier-final-v001
.\.venv\Scripts\python.exe pipelines/annotation/manage_evaluation_artifacts.py unpin holdout-frontier-final-v001
```

Pruning is a dry-run unless `--execute` is explicitly supplied. The active DVC
run from `experiments/params.yaml` and all pinned runs are always protected:

```powershell
make annotation-eval-prune ARGS="--smoke --older-than-days 7"
make annotation-eval-prune ARGS="--smoke --older-than-days 7 --execute"
make annotation-eval-prune ARGS="--incomplete --older-than-days 1"
make annotation-eval-prune ARGS="--match 'dev-*' --keep-latest 3"
```

Recommended retention policy:

1. Pin final holdout runs and any run cited in a report.
2. Keep the active DVC output and the latest development winner for each phase.
3. Remove old smoke runs after seven days.
4. Remove incomplete runs after one day once their errors have been inspected.
5. Use `dvc push` before pruning reproducible DVC outputs that must survive
   beyond the local cache.
6. Manage the DVC cache separately with DVC commands; the artifact manager only
   removes generated workspace run directories.

## Audit JSON

Model-call audit files record request payloads, prompts, JSON schemas, parsed
outputs, raw provider responses where available, response text, timing, status,
provider, model, and prompt version.

For local extraction, GLiNER candidate entity detection is also recorded, along
with Ollama relationship extraction calls.

## Tests

Run the annotation and shared pipeline tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall packages pipelines scripts tests
```
