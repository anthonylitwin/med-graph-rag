# Initial Annotation Evaluation Runbook

This runbook starts from a clean local Neo4j and MLflow stack; runs the
configured extraction profiles against the gold annotation set; records every
run in DVC and MLflow; and then moves the selected local non-instruct
configuration into the Neo4j ingestion workflow.

Run all commands from the repository root in PowerShell:

```powershell
Set-Location C:\Users\antho\dev\med-graph-rag
```

## Evaluation Boundary

Annotation evaluation is artifact-only. It writes predictions, matches,
metrics, model-call audits, DVC outputs, and MLflow records. It never writes to
Neo4j. Neo4j is populated only in the final ingestion section after the local
non-instruct configuration has been selected and frozen.

The commands below use the complete current gold manifest:

```text
data/annotations/gold_v001/bootstrap_v001_full/gold_manifest.json
```

These `fullgold-*` runs are suitable for an initial engineering comparison, but
they expose the entire gold set. Do not call them protected holdout results.
For a defensible development/holdout experiment, first add PMCID split
selection to the evaluator and use the split in
[`annotation_evaluation_matrix.md`](annotation_evaluation_matrix.md). The
current `limit` parameter is not a document split and must not be used as one.

## 1. Protect Existing Data

The clean-slate procedure in the next section permanently deletes the local
Neo4j graph, MLflow database, MLflow artifacts, and all other Docker Compose
volumes for this project.

Before using it, inspect the current state:

```powershell
docker compose ps
docker volume ls
```

Back up anything that must survive. Skip the volume deletion if this stack
already contains valuable runs or graph data.

## 2. Create A Clean Service Stack

Use this destructive reset once, immediately before the initial formal runs:

```powershell
docker compose down --volumes --remove-orphans
docker compose up -d neo4j mlflow
docker compose ps
```

Wait until the services are ready:

```powershell
do {
  Start-Sleep -Seconds 2
  try { $mlflowReady = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5000/health).StatusCode -eq 200 } catch { $mlflowReady = $false }
} until ($mlflowReady)
```

Confirm Neo4j is empty:

```powershell
docker compose exec -T neo4j cypher-shell `
  -u neo4j -p medgraphrag-password `
  "MATCH (n) RETURN count(n) AS node_count"

docker compose exec -T neo4j cypher-shell `
  -u neo4j -p medgraphrag-password `
  "MATCH ()-[r]->() RETURN count(r) AS relationship_count"
```

Both counts must be `0`.

Confirm MLflow contains no active test or smoke experiments. Immediately after
the volume reset, only the built-in `Default` experiment should be listed:

```powershell
.\.venv\Scripts\python.exe -c "import mlflow; from mlflow import MlflowClient; from mlflow.entities import ViewType; mlflow.set_tracking_uri('http://127.0.0.1:5000'); experiments=MlflowClient().search_experiments(view_type=ViewType.ACTIVE_ONLY); print([(item.experiment_id, item.name) for item in experiments])"
```

Expected result:

```text
[('0', 'Default')]
```

### Preserve-Volumes Alternative

When the stack already contains valuable MLflow runs or artifacts, do not
run `docker compose down --volumes`. Start the services normally, clear only
the graph, and soft-delete active experiments whose names contain `test` or
`smoke`:

```powershell
docker compose up -d neo4j mlflow

docker compose exec -T neo4j cypher-shell `
  -u neo4j -p medgraphrag-password `
  "MATCH (n) DETACH DELETE n"

.\.venv\Scripts\python.exe -c "import mlflow; from mlflow import MlflowClient; from mlflow.entities import ViewType; mlflow.set_tracking_uri('http://127.0.0.1:5000'); client=MlflowClient(); active=client.search_experiments(view_type=ViewType.ACTIVE_ONLY); doomed=[item for item in active if item.name != 'Default' and ('test' in item.name.lower() or 'smoke' in item.name.lower())]; [client.delete_experiment(item.experiment_id) for item in doomed]; print('deleted:', [item.name for item in doomed])"
```

MLflow experiment deletion is soft deletion. Those experiments disappear from
the active experiment list, but their names may remain reserved until the
deleted records are permanently purged. Use a new versioned name for formal
experiments, such as `medgraphrag-annotation-eval-v001`, and rerun the active
experiment query above to verify the result.

Open the service UIs when useful:

| Service | URL |
| --- | --- |
| MLflow | http://localhost:5000 |
| Neo4j Browser | http://localhost:7474 |

## 3. Prepare The Repository

Create the virtual environment if it does not already exist, then install the
application, local-model, and experiment dependencies:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r apps/api/requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-local-models.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-experiments.txt
```

Verify that DVC is initialized and that the gold manifest exists:

```powershell
.\.venv\Scripts\python.exe -m dvc status
Test-Path data\annotations\gold_v001\bootstrap_v001_full\gold_manifest.json
```

Formal DVC experiments must start from tracked experiment code. Review and
commit the pipeline, DVC configuration, gold metadata, and this runbook before
running the models:

```powershell
git status --short
git diff --check
```

Do not blindly commit unrelated working-tree changes. The important condition
is that `experiments/run_annotation_eval.py`, `experiments/dvc.yaml`,
`experiments/params.yaml`, and their pipeline dependencies are tracked in the
baseline commit. DVC experiments run from a Git snapshot and cannot see
untracked pipeline files.

Run the regression suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall pipelines packages scripts tests experiments
```

## 4. Configure The Host Session

The evaluation runner executes on the host, not in Docker. Set the MLflow
tracking URI so the client can upload artifacts through the local MLflow server:

```powershell
$env:MLFLOW_TRACKING_URI = "http://127.0.0.1:5000"
$env:OLLAMA_BASE_URL = "http://localhost:11434"
$env:OLLAMA_TIMEOUT_SECONDS = "600"
$env:GLINER_RELATION_ENTITY_LIMIT = "20"
```

The local instruct evaluation profiles send long relationship-extraction
prompts to Ollama. Keep `OLLAMA_TIMEOUT_SECONDS` at 600 seconds or higher for
full-gold `local-qwen25` and `local-qwen3` runs on CPU-bound or memory-constrained
machines. `GLINER_RELATION_ENTITY_LIMIT` caps how many top-confidence entity
candidates are sent to Qwen for relationship extraction while preserving the
full GLiNER entity list for entity scoring; lower it to `12` or `16` if Qwen
still times out, or set it to `0` to disable the cap.

The current full-gold workbook uses fixed chunks that are close to 6000
characters. Reducing ingestion chunk size will not change this evaluation unless
the gold workbook is rebuilt. For the next gold set, prefer chunks around 3000
characters with 250 to 300 characters of overlap for local instruct extraction.

Use a rotated OpenAI key. Replace any revoked value in the local `.env` before
later API use, but do not paste a key into this runbook, Git, or a DVC parameter.
Load it into only the current PowerShell process without putting the value in
command history:

```powershell
$secureOpenAIKey = Read-Host "OpenAI API key" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", $secureOpenAIKey).Password
$env:OPENAI_MODEL = "gpt-5.5"
```

Start Ollama in another terminal if it is not already running, then pull the
exact local instruct model tags used by the configured profiles:

```powershell
ollama serve
```

In the experiment terminal:

```powershell
ollama pull qwen2.5:7b-instruct
ollama pull qwen3:8b
ollama list
```

The first GLiNER or sentence-transformer run may download model weights. Allow
that download to finish before interpreting timing metrics.

## 5. Define The Repeatable DVC Command

Paste this helper into the experiment PowerShell session. It applies explicit
DVC parameter overrides, enables MLflow, verifies the durable artifact hashes,
and pins successful local artifacts against pruning:

```powershell
$Python = ".\.venv\Scripts\python.exe"
$GoldManifest = "data/annotations/gold_v001/bootstrap_v001_full/gold_manifest.json"
$MlflowExperiment = "medgraphrag-annotation-eval-v001"
$MlflowTrackingUri = if ($env:MLFLOW_TRACKING_URI) { $env:MLFLOW_TRACKING_URI } else { "http://127.0.0.1:5000" }

function Invoke-AnnotationEvaluation {
  param(
    [Parameter(Mandatory)] [string] $RunId,
    [Parameter(Mandatory)] [string] $Profile,
    [Parameter(Mandatory)] [string] $Model,
    [string] $EntityModel = "",
    [string[]] $AdditionalOverrides = @()
  )

  $overrides = @(
    "experiments/params.yaml:annotation_eval.eval_id=$RunId",
    "experiments/params.yaml:annotation_eval.gold_manifest=$GoldManifest",
    "experiments/params.yaml:annotation_eval.model_profile=$Profile",
    "experiments/params.yaml:annotation_eval.model=$Model",
    "experiments/params.yaml:annotation_eval.limit=null",
    "experiments/params.yaml:annotation_eval.fail_fast=true",
    "experiments/params.yaml:annotation_eval.neo4j_load_mode=none",
    "experiments/params.yaml:annotation_eval.mlflow.enabled=true",
    "experiments/params.yaml:annotation_eval.mlflow.tracking_uri=$MlflowTrackingUri",
    "experiments/params.yaml:annotation_eval.mlflow.experiment=$MlflowExperiment",
    "experiments/params.yaml:annotation_eval.mlflow.run_name=$RunId",
    "experiments/params.yaml:annotation_eval.mlflow.log_artifacts=true"
  )

  if ($EntityModel) {
    $overrides += "experiments/params.yaml:annotation_eval.entity_model=$EntityModel"
  }
  $overrides += $AdditionalOverrides

  $dvcArgs = @("-m", "dvc", "exp", "run", "-n", $RunId)
  foreach ($override in $overrides) {
    $dvcArgs += @("-S", $override)
  }
  $dvcArgs += "experiments/dvc.yaml:annotation-eval"

  & $Python @dvcArgs
  if ($LASTEXITCODE -ne 0) { throw "DVC experiment failed: $RunId" }

  & $Python pipelines/annotation/manage_evaluation_artifacts.py verify $RunId
  if ($LASTEXITCODE -ne 0) { throw "Artifact verification failed: $RunId" }

  & $Python pipelines/annotation/manage_evaluation_artifacts.py pin $RunId
  if ($LASTEXITCODE -ne 0) { throw "Artifact pin failed: $RunId" }
}
```

Do not run model evaluations in parallel. Ollama memory pressure, model
downloads, provider rate limits, and shared workspace outputs make sequential
runs easier to diagnose and compare.

If you edit or pull changes to this helper, paste the full function into the
PowerShell session again before rerunning. PowerShell keeps the previous
function definition in memory, including any old hardcoded tracking URI.

## 6. Run The Plumbing Smoke Test

The no-op run validates DVC, MLflow, the evaluator, and artifact
management without calling a model:

```powershell
Invoke-AnnotationEvaluation `
  -RunId "smoke-noop-mlflow-v001" `
  -Profile "noop" `
  -Model "noop-extractor-v0" `
  -AdditionalOverrides @("experiments/params.yaml:annotation_eval.limit=1")
```

Confirm that the run appears in MLflow and DVC before spending model time:

```powershell
.\.venv\Scripts\python.exe -m dvc exp show
.\.venv\Scripts\python.exe pipelines/annotation/manage_evaluation_artifacts.py list
```

Inspect `http://localhost:5000`. The run must contain parameters, entity and
relationship metrics, and an artifact tree. Resolve any MLflow artifact upload
failure before continuing.

## 7. Run Each Initial Model Profile

Run the entity-only GLiNER baseline:

```powershell
Invoke-AnnotationEvaluation `
  -RunId "fullgold-local-gliner-initial-v001" `
  -Profile "local-gliner" `
  -Model "Ihor/gliner-biomed-small-v1.0" `
  -EntityModel "Ihor/gliner-biomed-small-v1.0"
```

Run the default local non-instruct pipeline. This is the candidate that will be
tuned and eventually used for graph population:

```powershell
Invoke-AnnotationEvaluation `
  -RunId "fullgold-local-noninst-initial-v001" `
  -Profile "local-non-instruct" `
  -Model "sentence-transformers/all-MiniLM-L6-v2" `
  -EntityModel "Ihor/gliner-biomed-small-v1.0" `
  -AdditionalOverrides @(
    "experiments/params.yaml:annotation_eval.non_instruct.entity_threshold=0.50",
    "experiments/params.yaml:annotation_eval.non_instruct.concept_threshold=0.84",
    "experiments/params.yaml:annotation_eval.non_instruct.relation_threshold=0.66",
    "experiments/params.yaml:annotation_eval.non_instruct.semantic_floor=0.52",
    "experiments/params.yaml:annotation_eval.non_instruct.semantic_weight=0.50",
    "experiments/params.yaml:annotation_eval.non_instruct.cue_weight=0.25",
    "experiments/params.yaml:annotation_eval.non_instruct.proximity_weight=0.10",
    "experiments/params.yaml:annotation_eval.non_instruct.entity_confidence_weight=0.15",
    "experiments/params.yaml:annotation_eval.non_instruct.max_pair_distance=300"
  )
```

Run the primary local instruct reference:

```powershell
Invoke-AnnotationEvaluation `
  -RunId "fullgold-qwen25-initial-v001" `
  -Profile "local-qwen25" `
  -Model "qwen2.5:7b-instruct" `
  -EntityModel "Ihor/gliner-biomed-small-v1.0"
```

Run the additional configured Qwen 3 reference. Skip this only if Qwen 3 is
not part of the comparison you intend to retain:

```powershell
Invoke-AnnotationEvaluation `
  -RunId "fullgold-qwen3-initial-v001" `
  -Profile "local-qwen3" `
  -Model "qwen3:8b" `
  -EntityModel "Ihor/gliner-biomed-small-v1.0"
```

Run the frontier reference last, after every local and tracking path has been
validated. This should be the single initial frontier run:

```powershell
Invoke-AnnotationEvaluation `
  -RunId "fullgold-frontier-initial-v001" `
  -Profile "frontier" `
  -Model "gpt-5.5"
```

If a run fails, keep its artifacts for diagnosis but use a new `RunId` for the
replacement. Never overwrite a result already used in a comparison.

## 8. Compare And Retain Results

List DVC experiments and compare metrics:

```powershell
.\.venv\Scripts\python.exe -m dvc exp show
.\.venv\Scripts\python.exe -m dvc metrics diff
```

Build the local artifact indexes and verify all completed runs:

```powershell
.\.venv\Scripts\python.exe pipelines/annotation/manage_evaluation_artifacts.py index
.\.venv\Scripts\python.exe pipelines/annotation/manage_evaluation_artifacts.py list --status complete
.\.venv\Scripts\python.exe pipelines/annotation/manage_evaluation_artifacts.py verify
```

In MLflow, compare entity and relationship precision, recall, and F1 separately.
Also inspect per-type metrics and the false-positive/false-negative match files;
do not select a model from only the aggregate score.

Generated run folders are under:

```text
data/annotations/eval_v001/<run-id>/
```

They are ignored by Git and protected locally by the pin markers created by the
helper. DVC metadata and cache are not a remote backup. Before relying on these
runs across machines, configure a DVC remote appropriate for the project and
push the cache:

```powershell
.\.venv\Scripts\python.exe -m dvc remote list
# One-time example; replace <REMOTE_URL> with the chosen storage location.
.\.venv\Scripts\python.exe -m dvc remote add -d experiment-storage <REMOTE_URL>
.\.venv\Scripts\python.exe -m dvc push
```

Do not run the placeholder `remote add` command until a real remote has been
chosen. MLflow artifacts remain in the local `mlflow_data` Docker volume unless
that volume is backed up or moved to durable storage.

## 9. Iterate Only The Non-Instruct Pipeline

After the initial comparison, keep the frontier and local instruct results
fixed. Use new DVC runs to change one non-instruct parameter family at a time,
following [`annotation_evaluation_matrix.md`](annotation_evaluation_matrix.md).

Example relationship-threshold run:

```powershell
Invoke-AnnotationEvaluation `
  -RunId "fullgold-noninst-relation062-v001" `
  -Profile "local-non-instruct" `
  -Model "sentence-transformers/all-MiniLM-L6-v2" `
  -EntityModel "Ihor/gliner-biomed-small-v1.0" `
  -AdditionalOverrides @(
    "experiments/params.yaml:annotation_eval.non_instruct.relation_threshold=0.62"
  )
```

Every run ID must identify the changed parameter. Freeze the complete winning
configuration, including model names, terminology file, thresholds, weights,
pair distance, validator confidence floor, and code commit before graph load.

For the protected development/holdout protocol, do this tuning only on the
development PMCIDs. Do not run or inspect the frontier, local instruct, or
candidate outputs on the holdout until the non-instruct configuration is
frozen.

## 10. Populate Neo4j With The Frozen Non-Instruct Pipeline

This is a separate production-data action. Confirm the selected thresholds in
DVC and MLflow first. Then clear Neo4j without deleting MLflow:

```powershell
docker compose exec -T neo4j cypher-shell `
  -u neo4j -p medgraphrag-password `
  "MATCH (n) DETACH DELETE n"

docker compose exec -T neo4j cypher-shell `
  -u neo4j -p medgraphrag-password `
  "MATCH (n) RETURN count(n) AS node_count"
```

Apply the graph schema:

```powershell
.\.venv\Scripts\python.exe scripts/apply_neo4j_schema.py
```

Load the benchmark PMC set using the frozen non-instruct configuration. Replace
the values below only with the recorded winner from DVC and MLflow:

```powershell
.\.venv\Scripts\python.exe pipelines/ingestion/ingest_pmc.py `
  --pmcid-file data/source_documents/benchmark_pmcids.txt `
  --output-root data/source_documents/pmc_noninst_v001 `
  --clean-output `
  --model-profile local-non-instruct `
  --model sentence-transformers/all-MiniLM-L6-v2 `
  --entity-model Ihor/gliner-biomed-small-v1.0 `
  --embedding-model sentence-transformers/all-MiniLM-L6-v2 `
  --terminology-path data/terminology/biomedical_aliases_v001.json `
  --entity-threshold 0.50 `
  --concept-threshold 0.84 `
  --relation-threshold 0.66 `
  --semantic-floor 0.52 `
  --semantic-weight 0.50 `
  --cue-weight 0.25 `
  --proximity-weight 0.10 `
  --entity-confidence-weight 0.15 `
  --max-pair-distance 300 `
  --min-confidence 0.50 `
  --apply-schema `
  --fail-fast
```

`--clean-output` deletes only the specified ingestion output directory before
the run. Use a new versioned output root when preserving a previous ingestion.

Verify graph contents:

```powershell
docker compose exec -T neo4j cypher-shell `
  -u neo4j -p medgraphrag-password `
  "MATCH (n) RETURN labels(n) AS labels, count(*) AS count ORDER BY count DESC"

docker compose exec -T neo4j cypher-shell `
  -u neo4j -p medgraphrag-password `
  "MATCH ()-[r]->() RETURN type(r) AS relationship_type, count(*) AS count ORDER BY count DESC"
```

The extraction path is non-instruct. The current `local-non-instruct` QA profile
still uses `qwen2.5:7b-instruct` to compose answers from Neo4j evidence. Run a
local graph QA batch with:

```powershell
.\.venv\Scripts\python.exe pipelines/qa/answer_questions.py `
  --question-file eval/questions/qa_eval_v001.json `
  --output-root data/qa/noninst_graph_v001 `
  --model-profile local-non-instruct
```

Inspect `data/qa/noninst_graph_v001/manifest.csv`, retrieved evidence, and answer
artifacts before using the graph through the API.

## 11. End-Of-Run Checklist

- Neo4j was empty during annotation evaluation.
- MLflow began with only the `Default` experiment.
- The no-op MLflow artifact smoke passed before model runs.
- Every scored run has a unique DVC experiment name and evaluation ID.
- Every scored run appears in MLflow with artifacts.
- Entity and relationship metrics were reviewed separately.
- Durable local artifacts passed SHA-256 verification and were pinned.
- The frontier and local instruct references were not repeatedly tuned.
- The non-instruct winner was frozen before Neo4j ingestion.
- Neo4j was populated only by the explicit non-instruct ingestion command.
- QA retrieval artifacts show that answers are grounded in the populated graph.
